"""PostgreSQL claims and lifecycle transitions for ordinary Telegram replies."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.ordinary_chat_reply_operation import (
    OrdinaryChatReplyOperation, OrdinaryChatReplyState,
)


class OrdinaryChatReplyRepository:
    # Telegram message IDs are monotonically increasing within a private chat.
    # Once a burst has incorporated an inbound, no later lifecycle write may
    # reduce this durable authority watermark.
    STRANDED_GENERATED_GRACE_SECONDS = 30
    PENDING_RECLAMATION_LEASE_SECONDS = 60
    DURABLE_DELIVERY_AUDIT_KEYS = frozenset({
        "qualityFailureRecoveryHistory",
        "controlledFreshResponse",
        "current_turn_visual_context",
        "optionalActiveOfferSuppressionRecovery",
        "preGenerationCommercialDecision",
        "marketResourcePolicy",
        "postNudgeConversationPolicy",
        "approvedHistoricalCorrection",
        "interruptedGenerationRecovery",
        "strandedGeneratedRecovery",
        "attestedNotDeliveredRecovery",
        "sendUncertainReconciliation",
    })

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_or_create(self, *, account_scope, chat_id, inbound_message_id,
                      sender_user_id, correlation_id, inbound_message_text,
                      inbound_received_at=None, turn_obligations=()):
        operation_id = uuid4()
        obligations = list(dict.fromkeys(
            str(item) for item in turn_obligations if str(item).strip()
        ))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,
                inbound_telegram_message_id,inbound_sender_telegram_user_id,correlation_id,
                inbound_message_text,inbound_received_at,
                conversation_burst_id,burst_role,burst_survivor_operation_id,
                burst_freshness_telegram_message_id,burst_member_obligations,
                burst_obligations)
                VALUES (%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()),
                        %s,'SURVIVOR',%s,%s,%s::jsonb,%s::jsonb)
                ON CONFLICT(telegram_account_scope,telegram_chat_id,inbound_telegram_message_id)
                WHERE operation_kind='PRIMARY'
                DO NOTHING RETURNING *""", (operation_id, account_scope, chat_id,
                inbound_message_id, sender_user_id, correlation_id,
                inbound_message_text, inbound_received_at, operation_id, operation_id,
                inbound_message_id, json.dumps(obligations), json.dumps(obligations)))
            row = cursor.fetchone(); created = row is not None
            if created:
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    state='SUPPRESSED',next_retry_at=NULL,
                    last_error='superseded_by_newer_inbound_after_preparation',
                    claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                    updated_at=NOW()
                    WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                      AND inbound_telegram_message_id<%s
                      AND state IN ('GENERATED','RETRYABLE')
                      AND response_payload IS NOT NULL
                      AND send_attempt_count=0
                      AND outbound_telegram_message_id IS NULL""", (
                    account_scope, chat_id, inbound_message_id,
                ))
            if row is None:
                cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                    WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                      AND inbound_telegram_message_id=%s
                      AND operation_kind='PRIMARY'""",
                    (account_scope, chat_id, inbound_message_id))
                row = cursor.fetchone()
                if row is not None and (
                    int(row["inbound_sender_telegram_user_id"]) != int(sender_user_id)
                    or row.get("inbound_message_text") != inbound_message_text
                ):
                    raise ValueError(
                        "Telegram inbound identity was reused with conflicting content."
                    )
        return self._item(row), created

    @staticmethod
    def controlled_contract_followup_parent(parent, budget):
        """Only the never-sent V1 controlled contract failure can have one follow-up."""
        authority = (parent.get('delivery_payload') or {}).get('controlledFreshResponse') or {}
        result = parent.get('response_payload') or {}
        return bool(budget and authority.get('version') == 'ZERO_CANDIDATE_SNAPSHOT_REPAIR_V1'
            and parent.get('state') == 'SUPPRESSED'
            and parent.get('last_error') == 'recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY'
            and parent.get('operation_kind') == 'HISTORICAL_CORRECTIVE'
            and parent.get('telegram_account_scope') == 'AVA_TELETHON_PRIVATE'
            and not parent.get('send_attempt_count') and not parent.get('outbound_telegram_message_id')
            and not parent.get('sent_confirmed_at') and not parent.get('uncertain_at')
            and budget.get('candidate_count') == 1 and budget.get('provider_attempt_count') == 1
            and not budget.get('correction_started') and budget.get('context_snapshot')
            and 'ACKNOWLEDGE_SELF_PHOTO' in (budget.get('obligation') or {}).get('obligations', [])
            and result.get('delivery_type') == 'text' and not result.get('offer_authorized')
            and not result.get('delivery_requires_payment'))

    def create_controlled_fresh_response(self, *, failed_operation_id, creator_profile_id,
            fanvue_account_id, telegram_user_id, occurrence_id, approved_by, approval_reference):
        """One approved fresh turn after a snapshot failure or its unsent text-contract failure.

        Keep the failed operation immutable. The canonical scheduler owns generation
        and delivery; this entry point only creates a prospective budgeted operation.
        """
        from app.services.recovery_execution_constraint_service import RecoveryExecutionConstraintService
        with self.connection_factory() as c:
            parent = c.execute("SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE",
                               (failed_operation_id,)).fetchone()
            if not parent or parent['inbound_sender_telegram_user_id'] != telegram_user_id:
                raise ValueError('CONTROLLED_FRESH_IDENTITY_MISMATCH')
            key = 'controlled-fresh-snapshot:' + str(failed_operation_id)
            existing = c.execute("SELECT * FROM ordinary_chat_reply_operations WHERE recovery_idempotency_key=%s", (key,)).fetchone()
            if existing:
                return self._item(existing)
            budget = c.execute("SELECT * FROM ordinary_generation_budgets WHERE operation_id=%s", (failed_operation_id,)).fetchone()
            followup = self.controlled_contract_followup_parent(parent, budget)
            if not followup and (parent['state'] != 'TERMINAL_FAILED' or parent['operation_kind'] != 'PRIMARY'
                    or parent['telegram_account_scope'] != 'AVA_TELETHON_PRIVATE'
                    or not str(parent['last_error']).startswith('DECISION_ENGINE_EXCEPTION:')
                    or parent['response_text'] or parent['response_payload'] or parent['send_attempt_count']
                    or parent['outbound_telegram_message_id'] or not budget or budget['candidate_count']
                    or budget['provider_attempt_count'] or budget['correction_started']
                    or budget['context_snapshot']
                    or (budget['result_snapshot'].get('diagnostic_metadata') or {}).get('exception_type') != 'TypeError'):
                raise ValueError('CONTROLLED_FRESH_ZERO_CANDIDATE_FAILURE_REQUIRED')
            ack = c.execute("""SELECT 1 FROM conversation_attention_acknowledgements
                WHERE occurrence_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND causal_operation_id=%s AND revoked_at IS NULL""",
                (occurrence_id,creator_profile_id,fanvue_account_id,telegram_user_id,failed_operation_id)).fetchone()
            if (not followup and not ack) or not approved_by:
                raise ValueError('CONTROLLED_FRESH_ACKNOWLEDGEMENT_REQUIRED')
            latest = c.execute("""SELECT telegram_message_id FROM telegram_private_inbound_messages
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s
                  AND telegram_chat_id=%s ORDER BY telegram_message_id DESC LIMIT 1""",
                (creator_profile_id,fanvue_account_id,telegram_user_id,parent['telegram_chat_id'])).fetchone()
            if not latest or latest['telegram_message_id'] != parent['inbound_telegram_message_id']:
                raise ValueError('CONTROLLED_FRESH_NEWER_INBOUND')
            if c.execute("""SELECT 1 FROM ordinary_chat_reply_operations WHERE
                recovery_parent_operation_id=%s OR (telegram_chat_id=%s AND operation_id<>ALL(%s::uuid[])
                AND (inbound_telegram_message_id>=%s OR state IN ('GENERATING','GENERATED','SENDING')))
                LIMIT 1""", (failed_operation_id,parent['telegram_chat_id'],
                              [failed_operation_id, parent['causal_operation_id']] if followup else [failed_operation_id],
                              parent['inbound_telegram_message_id'])).fetchone():
                raise ValueError('CONTROLLED_FRESH_COMPETING_OPERATION')
            rows = c.execute("""SELECT o.*,a.attachment_id,a.normalized_path
                FROM telegram_inbound_media_operations o JOIN telegram_inbound_media_attachments a USING(operation_id)
                WHERE o.creator_profile_id=%s AND o.fanvue_account_id=%s AND o.telegram_user_id=%s
                  AND o.telegram_chat_id=%s AND a.telegram_message_id=%s
                  AND o.safety_state='NORMAL_NON_EXPLICIT' AND o.retention_expires_at>now()
                  AND a.state='READY_FOR_ANALYSIS'""", (creator_profile_id,fanvue_account_id,telegram_user_id,
                    parent['telegram_chat_id'],parent['inbound_telegram_message_id'])).fetchall()
            if len(rows) != 1:
                raise ValueError('CONTROLLED_FRESH_CURRENT_SAFE_MEDIA_REQUIRED')
            media = rows[0]
            from pathlib import Path
            if not Path(media['normalized_path']).is_file():
                raise ValueError('CONTROLLED_FRESH_MEDIA_UNAVAILABLE')
            visual = {k: media[k] for k in ('safety_state','response_policy','solicitation_state',
                                           'creator_profile_id','fanvue_account_id','telegram_user_id')}
            visual.update(operation_id=str(media['operation_id']), attachment_ids=[str(media['attachment_id'])],
                          attachment_paths=[media['normalized_path']], partial_failure=False)
            if followup:
                prior_visual = ((parent.get('response_payload') or {}).get('diagnostic_metadata') or {}).get('current_turn_visual_context') or {}
                from app.services.customer_visual_evidence_policy import CustomerVisualEvidencePolicy
                if not CustomerVisualEvidencePolicy.self_photo_established(prior_visual):
                    raise ValueError('CONTROLLED_FRESH_SELF_PHOTO_EVIDENCE_REQUIRED')
                visual['self_photo_evidence'] = dict(prior_visual['self_photo_evidence'])
            audit = {'controlledFreshResponse': {'version':('TEXT_CONTRACT_FOLLOWUP_V2' if followup else 'ZERO_CANDIDATE_SNAPSHOT_REPAIR_V1'),
                'failedOperationId':str(failed_operation_id),'approvedBy':approved_by,'occurrenceId':occurrence_id,
                'approvalReference':str(UUID(str(approval_reference)))},
                'current_turn_visual_context':visual,
                'recoveryExecutionConstraint':RecoveryExecutionConstraintService.authority()}
            operation_id = uuid4()
            row = c.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,inbound_telegram_message_id,
                inbound_sender_telegram_user_id,inbound_message_text,inbound_received_at,correlation_id,
                delivery_payload,state,max_generation_attempts,max_send_attempts,next_retry_at,last_error,
                scheduled_delivery_at,preparation_eligible_at,operation_kind,causal_operation_id,
                recovery_parent_operation_id,recovery_attention_occurrence_id,recovery_idempotency_key,recovery_resolution_plan_id)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'RETRYABLE',2,1,now()+interval '8 seconds',
                'availability_deferred',now()+interval '8 seconds',now(),'HISTORICAL_CORRECTIVE',%s,%s,%s,%s,%s)
                RETURNING *""", (operation_id,parent['telegram_account_scope'],parent['telegram_chat_id'],
                parent['inbound_telegram_message_id'],telegram_user_id,parent['inbound_message_text'],
                parent['inbound_received_at'],key,json.dumps(audit),failed_operation_id,failed_operation_id,occurrence_id,key,UUID(str(approval_reference)))).fetchone()
            c.execute("INSERT INTO ordinary_generation_budgets(operation_id) VALUES (%s)", (operation_id,))
            return self._item(row)

    def get(self, operation_id):
        return self._one("SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s",
                         (operation_id,))

    @classmethod
    def merge_current_delivery_with_durable_audit(cls, existing, current):
        """Replace current delivery data while retaining bounded provenance namespaces."""
        merged = dict(current or {})
        previous = dict(existing or {})
        for key in cls.DURABLE_DELIVERY_AUDIT_KEYS:
            if key in previous:
                merged[key] = previous[key]
        return merged

    def record_generation_attempt(self, operation, *, provider, candidate_text,
                                  quality_disposition, quality_reasons,
                                  turn_obligations, satisfied_obligations,
                                  unsatisfied_obligations, repair_outcome,
                                  creator_profile_id=None, fanvue_account_id=None):
        """Persist bounded immutable evidence for one claimed generation attempt."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ordinary_reply_generation_attempts(
              attempt_id,operation_id,attempt_number,creator_profile_id,fanvue_account_id,
              telegram_account_scope,telegram_chat_id,telegram_user_id,provider,
              candidate_text,quality_disposition,quality_reasons,turn_obligations,
              satisfied_obligations,unsatisfied_obligations,repair_outcome)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,
                     %s::jsonb,%s::jsonb,%s)
              ON CONFLICT(operation_id,attempt_number) DO NOTHING RETURNING *""", (
                uuid4(), operation.operation_id, operation.generation_attempt_count,
                creator_profile_id, fanvue_account_id, operation.telegram_account_scope,
                operation.telegram_chat_id, operation.inbound_sender_telegram_user_id,
                str(provider or "")[:80] or None, str(candidate_text or "")[:2000],
                quality_disposition, json.dumps(list(quality_reasons or ())),
                json.dumps(list(turn_obligations or ())),
                json.dumps(list(satisfied_obligations or ())),
                json.dumps(list(unsatisfied_obligations or ())),
                str(repair_outcome or "")[:160] or None,
            ))
            row = cursor.fetchone()
            if row is None:
                cursor.execute("""SELECT * FROM ordinary_reply_generation_attempts
                  WHERE operation_id=%s AND attempt_number=%s""", (
                    operation.operation_id, operation.generation_attempt_count,
                ))
                row = cursor.fetchone()
            return dict(row) if row else None

    def generation_attempts(self, operation_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_reply_generation_attempts
              WHERE operation_id=%s ORDER BY attempt_number""", (operation_id,))
            return [dict(row) for row in cursor.fetchall()]

    def confirm_generation_attempt(self, operation_id, *, attempt_number,
                                   telegram_message_id):
        return self._one("""UPDATE ordinary_reply_generation_attempts SET
          sent_confirmed=TRUE,outbound_telegram_message_id=%s,sent_confirmed_at=NOW()
          WHERE operation_id=%s AND attempt_number=%s
            AND quality_disposition='ALLOWED_BEFORE_DELIVERY'
            AND sent_confirmed=FALSE RETURNING *""", (
              telegram_message_id, operation_id, attempt_number,
          ))

    def post_presentation_turn_candidates(self, *, account_scope, chat_id,
                                          sender_user_id, presented_at):
        """Return unique, non-suppressed durable inbounds in one offer window."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT operation_id,inbound_telegram_message_id,
                       inbound_message_text,inbound_received_at,state,last_error
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s
                  AND inbound_received_at>%s AND state<>'SUPPRESSED'
                ORDER BY inbound_received_at,inbound_telegram_message_id""",
                (account_scope, chat_id, sender_user_id, presented_at))
            return [dict(row) for row in cursor.fetchall()]

    def customer_behavior_evidence(self, *, account_scope, chat_id,
                                   sender_user_id):
        """Aggregate existing durable inbound evidence without persisting risk."""
        from app.services.commercial_nonpayment_evidence_service import (
            CommercialNonpaymentEvidenceService,
        )
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT
                COUNT(*)::BIGINT AS inbound_message_count,
                COUNT(*) FILTER (WHERE COALESCE(inbound_message_text,'') ~* %s)::BIGINT
                    AS rejection_count,
                COUNT(*) FILTER (WHERE COALESCE(inbound_message_text,'') ~* %s)::BIGINT
                    AS idle_browsing_signal_count,
                COUNT(*) FILTER (WHERE COALESCE(inbound_message_text,'') ~* %s)::BIGINT
                    AS commercial_movement_count,
                COUNT(*) FILTER (WHERE COALESCE(inbound_message_text,'') ~* %s)::BIGINT
                    AS sexual_engagement_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED' AND
                    COALESCE(response_payload#>>'{diagnostic_metadata,proactive_tease_delivered}','false')='true')::BIGINT
                    AS proactive_tease_delivered_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED' AND
                    COALESCE(response_payload#>>'{diagnostic_metadata,commercial_tease_exposure_recorded}','false')='true')::BIGINT
                    AS commercial_tease_exposure_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED' AND
                    COALESCE(response_payload#>>'{diagnostic_metadata,build_interest_exposure}','false')='true')::BIGINT
                    AS build_interest_exposure_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED' AND
                    COALESCE(response_payload#>>'{diagnostic_metadata,offer_exposure}','false')='true')::BIGINT
                    AS offer_exposure_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED' AND
                    COALESCE(response_payload#>>'{diagnostic_metadata,customer_commercial_response}','false')='true')::BIGINT
                    AS customer_commercial_response_count,
                COUNT(*) FILTER (WHERE state='SENT_CONFIRMED'
                    AND sent_confirmed_at >= NOW() - INTERVAL '24 hours'
                    AND COALESCE(
                        response_payload#>>'{diagnostic_metadata,customer_value_attention,lowCostNurtureActive}',
                        response_payload#>>'{diagnostic_metadata,commercial_summary,customerValueAttention,lowCostNurtureActive}',
                        'false'
                    )='true')::BIGINT
                    AS nurture_response_count_rolling_day,
                MAX(sent_confirmed_at) FILTER (WHERE state='SENT_CONFIRMED'
                    AND COALESCE(
                        response_payload#>>'{diagnostic_metadata,customer_value_attention,lowCostNurtureActive}',
                        response_payload#>>'{diagnostic_metadata,commercial_summary,customerValueAttention,lowCostNurtureActive}',
                        'false'
                    )='true')
                    AS last_nurture_response_at
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s""", (
                    CommercialNonpaymentEvidenceService.REJECTION_PATTERN,
                    CommercialNonpaymentEvidenceService.BROWSING_PATTERN,
                    r"(^|\W)(buy|buying|purchase|price|how much|unlock|show me|offer)(\W|$)",
                    r"(^|\W)(horny|sexy|naked|turned on)(\W|$)",
                    account_scope, chat_id, sender_user_id,
                ))
            row = dict(cursor.fetchone() or {})
        inbound = int(row.get("inbound_message_count") or 0)
        commercial = int(row.get("commercial_movement_count") or 0)
        sexual = int(row.get("sexual_engagement_count") or 0)
        proactive = int(row.get("proactive_tease_delivered_count") or 0)
        commercial_teases = int(row.get("commercial_tease_exposure_count") or 0)
        build = int(row.get("build_interest_exposure_count") or 0)
        offers = int(row.get("offer_exposure_count") or 0)
        return {
            "source": "ORDINARY_CHAT_REPLY_OPERATIONS",
            "behaviorEvidenceLoaded": True,
            "inbound_message_count": inbound,
            "rejection_count": int(row.get("rejection_count") or 0),
            "idle_browsing_signal_count": int(
                row.get("idle_browsing_signal_count") or 0
            ),
            "commercial_movement": commercial > 0,
            "commercial_movement_count": commercial,
            "sexual_engagement_history": sexual > 0,
            "sexual_engagement_count": sexual,
            "sexual_engagement_only": sexual > 0 and commercial == 0,
            "proactive_tease_delivered_count": proactive,
            "commercial_tease_exposure_count": commercial_teases,
            "build_interest_exposure_count": build,
            "offer_exposure_count": offers,
            "commercial_opportunity_exposure_count": commercial_teases + build + offers,
            "customer_commercial_response_count": int(
                row.get("customer_commercial_response_count") or 0
            ),
            "nurture_response_count_rolling_day": int(
                row.get("nurture_response_count_rolling_day") or 0
            ),
            "last_nurture_response_at": row.get("last_nurture_response_at"),
        }

    def list_confirmed_recent_for_prospect(
        self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
        telegram_chat_id, account_scope, exclude_inbound_message_id=None,
        limit=4,
    ):
        """Read confirmed paired private-chat exchanges for one scoped prospect."""
        exclusion = (
            "AND o.inbound_telegram_message_id<>%s"
            if exclude_inbound_message_id is not None else ""
        )
        params = [
            account_scope, telegram_chat_id, telegram_user_id,
            creator_profile_id, fanvue_account_id, telegram_user_id,
            telegram_chat_id,
        ]
        if exclude_inbound_message_id is not None:
            params.append(exclude_inbound_message_id)
        params.append(max(1, int(limit)))
        query = f"""SELECT o.* FROM public.ordinary_chat_reply_operations o
            WHERE o.telegram_account_scope=%s AND o.telegram_chat_id=%s
              AND o.inbound_sender_telegram_user_id=%s
              AND o.state='SENT_CONFIRMED'
              AND NULLIF(BTRIM(COALESCE(o.inbound_message_text,'')),'') IS NOT NULL
              AND NULLIF(BTRIM(COALESCE(o.response_text,'')),'') IS NOT NULL
              AND o.outbound_telegram_message_id IS NOT NULL
              AND EXISTS (
                  SELECT 1 FROM public.telegram_sales_prospects p
                  WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s
                    AND p.telegram_user_id=%s AND p.telegram_chat_id=%s
              )
              {exclusion}
            ORDER BY o.inbound_received_at DESC,
                     o.inbound_telegram_message_id DESC
            LIMIT %s"""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, tuple(params))
            rows = cursor.fetchall()
        return [self._item(row) for row in reversed(rows)]

    def claim_generation(self, operation_id, *, owner, lease_seconds=300):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT telegram_chat_id FROM ordinary_chat_reply_operations
                WHERE operation_id=%s""", (operation_id,))
            target = cursor.fetchone()
            if target is None:
                return None
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                           (f"telegram-turn:{target['telegram_chat_id']}",))
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
            state='GENERATING',claim_owner=%s,claimed_at=NOW(),
            lease_expires_at=NOW()+(%s*INTERVAL '1 second'),
            generation_attempt_count=generation_attempt_count+1,updated_at=NOW()
            WHERE operation_id=%s AND (
              state='PENDING_GENERATION'
              OR (state='RETRYABLE' AND response_payload IS NULL
                  AND COALESCE(next_retry_at,NOW())<=NOW())
              OR (state='GENERATING' AND lease_expires_at<NOW()))
              AND generation_attempt_count<max_generation_attempts
              AND (EXISTS(SELECT 1 FROM ordinary_generation_budgets b
                    WHERE b.operation_id=ordinary_chat_reply_operations.operation_id)
                   OR created_at >= (SELECT installed_at FROM ordinary_generation_policy WHERE singleton))
              AND NOT EXISTS(
                SELECT 1 FROM telegram_conversation_turn_reservations reservation
                JOIN telegram_private_inbound_messages member
                  ON member.inbound_id=ANY(reservation.member_inbound_ids)
                WHERE member.telegram_account_scope=ordinary_chat_reply_operations.telegram_account_scope
                  AND member.telegram_chat_id=ordinary_chat_reply_operations.telegram_chat_id
                  AND member.telegram_message_id=ordinary_chat_reply_operations.inbound_telegram_message_id
                  AND reservation.state='OPEN' AND reservation.closes_at>NOW())
            RETURNING *""", (owner, max(1, int(lease_seconds)), operation_id))
            row = cursor.fetchone()
            if row and row['generation_attempt_count'] == 1 and row.get('causal_operation_id') is None and row.get('recovery_parent_operation_id') is None:
                cursor.execute("""INSERT INTO ordinary_generation_budgets(operation_id)
                    SELECT %s WHERE NOT (%s::jsonb ?| ARRAY['approvedHistoricalCorrection',
                        'canonicalNotDeliveredCorrection','historicalSurvivorReconciliation'])
                    ON CONFLICT DO NOTHING""", (row['operation_id'], json.dumps(row.get('delivery_payload') or {})))
        return self._item(row) if row else None

    def defer_for_sleep(self, operation_id, *, wake_time, cycle_id):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',next_retry_at=%s,
            last_error=%s,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            updated_at=NOW()
            WHERE operation_id=%s AND state='PENDING_GENERATION'
              AND response_payload IS NULL AND send_attempt_count=0
            RETURNING *""", (
                wake_time, f"sleep_deferred:{cycle_id}", operation_id,
            ))

    def defer_for_availability(self, operation_id, *, available_at, diagnostics):
        """Durably schedule an inbound before generation; safe across restart."""
        quiet_seconds=max(8.0,float(diagnostics.get("quietPeriodSeconds") or 8.0))
        return self._one("""WITH target AS (
            SELECT telegram_account_scope,telegram_chat_id,
                   scheduled_delivery_at,preparation_eligible_at
              FROM ordinary_chat_reply_operations WHERE operation_id=%s
          ), delivery AS (
            SELECT COALESCE(target.scheduled_delivery_at,
                     MIN(existing.scheduled_delivery_at),%s) AS delivery_at,
                   target.preparation_eligible_at AS preparation_at
              FROM target
              LEFT JOIN ordinary_chat_reply_operations existing
                ON existing.telegram_account_scope=target.telegram_account_scope
               AND existing.telegram_chat_id=target.telegram_chat_id
               AND existing.state='RETRYABLE'
               AND existing.response_payload IS NULL
               AND existing.last_error IN (
                 'availability_deferred','quality_corrective_retry_scheduled'
               )
             GROUP BY target.scheduled_delivery_at,target.preparation_eligible_at
          ), schedule AS (
            SELECT delivery_at,COALESCE(preparation_at,GREATEST(
              delivery_at-(300*INTERVAL '1 second'),
              NOW()+(%s*INTERVAL '1 second'))) AS preparation_at
              FROM delivery
          ) UPDATE ordinary_chat_reply_operations current SET
            state='RETRYABLE',scheduled_delivery_at=schedule.delivery_at,
            preparation_eligible_at=schedule.preparation_at,
            next_retry_at=schedule.preparation_at,
            last_error=%s,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            FROM schedule
            WHERE operation_id=%s AND state='PENDING_GENERATION'
              AND response_payload IS NULL AND send_attempt_count=0 RETURNING current.*""", (
            operation_id, available_at, quiet_seconds,
            "availability_deferred",
            json.dumps({"availability": dict(diagnostics)}), operation_id,
        ))

    def get_by_inbound(self, *, account_scope, chat_id, message_id):
        return self._one("""SELECT * FROM ordinary_chat_reply_operations
            WHERE telegram_account_scope=%s AND telegram_chat_id=%s
              AND inbound_telegram_message_id=%s""",(account_scope,chat_id,message_id))

    def record_attention(self, operation_id, diagnostics):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            updated_at=NOW() WHERE operation_id=%s RETURNING *""",
            (json.dumps({"attentionInvestment":dict(diagnostics)}),operation_id))

    def defer_for_global_readiness(self, operation_id, *, reason, retry_seconds=30):
        """Keep definitively-ungenerated work scheduled behind a global readiness gate."""
        evidence = {"globalDeliveryReadiness": {
            "allowed": False, "reason": str(reason),
            "providerGenerationPerformed": False,
        }}
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',next_retry_at=NOW()+(%s*INTERVAL '1 second'),
            last_error='global_delivery_readiness_deferred',
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='PENDING_GENERATION'
              AND response_payload IS NULL AND generation_attempt_count=0
              AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
            RETURNING *""", (max(5,int(retry_seconds)),json.dumps(evidence),operation_id))

    def record_pre_generation_commercial_decision(self, operation_id, projection):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            updated_at=NOW() WHERE operation_id=%s
              AND state='PENDING_GENERATION' AND response_payload IS NULL
            RETURNING *""", (json.dumps({
                "preGenerationCommercialDecision": dict(projection)}), operation_id))

    def record_post_nudge_conversation_policy(self, operation_id, projection):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            updated_at=NOW() WHERE operation_id=%s
              AND state='PENDING_GENERATION' AND response_payload IS NULL RETURNING *""",
            (json.dumps({'postNudgeConversationPolicy':dict(projection)}),operation_id))

    def post_nudge_policy_history(self, *, creator_profile_id,
                                  fanvue_account_id, telegram_user_id,
                                  telegram_chat_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""WITH boundary AS (
              SELECT operation.sent_confirmed_at FROM ordinary_chat_reply_operations operation
              JOIN telegram_private_inbound_messages inbound
                ON inbound.telegram_account_scope=operation.telegram_account_scope
               AND inbound.telegram_chat_id=operation.telegram_chat_id
               AND inbound.telegram_message_id=operation.inbound_telegram_message_id
              WHERE operation.telegram_account_scope='AVA_TELETHON_PRIVATE'
                AND inbound.creator_profile_id=%s AND inbound.fanvue_account_id=%s
                AND operation.inbound_sender_telegram_user_id=%s AND operation.telegram_chat_id=%s
                AND state='SENT_CONFIRMED'
                AND response_payload->'diagnostic_metadata'->'post_nudge_conversation_policy'->>'responsePurpose'='SUPPORTER_BOUNDARY'
              ORDER BY sent_confirmed_at DESC LIMIT 1)
              SELECT EXISTS(SELECT 1 FROM boundary) supporter_boundary_confirmed,
                COUNT(*) FILTER (WHERE operation.delivery_payload->'postNudgeConversationPolicy'->>'sexualInbound'='true'
                  AND operation.inbound_received_at>(SELECT sent_confirmed_at FROM boundary))::int sexual_attempts_after_boundary
              FROM ordinary_chat_reply_operations operation
              JOIN telegram_private_inbound_messages inbound
                ON inbound.telegram_account_scope=operation.telegram_account_scope
               AND inbound.telegram_chat_id=operation.telegram_chat_id
               AND inbound.telegram_message_id=operation.inbound_telegram_message_id
              WHERE operation.telegram_account_scope='AVA_TELETHON_PRIVATE'
                AND inbound.creator_profile_id=%s AND inbound.fanvue_account_id=%s
                AND operation.inbound_sender_telegram_user_id=%s AND operation.telegram_chat_id=%s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
                 creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id))
            return dict(cursor.fetchone() or {})

    def buyer_attention_context(self, *, telegram_user_id,
                                creator_profile_id=None,
                                fanvue_account_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT
                COUNT(transaction.customer_commerce_transaction_id)::int AS purchase_count,
                COALESCE(SUM(transaction.gross_minor),0)::bigint AS lifetime_gross_minor
                FROM telegram_identity_map mapping
                JOIN customer_commerce_profiles profile
                  ON profile.fanvue_account_id=mapping.fanvue_account_id
                 AND profile.external_fanvue_user_uuid=mapping.external_fanvue_user_uuid
                JOIN customer_commerce_transactions transaction
                  ON transaction.customer_commerce_profile_id=profile.customer_commerce_profile_id
                 AND LOWER(transaction.payment_status) IN
                     ('succeeded','successful','paid','completed')
                LEFT JOIN purchase_intents intent
                  ON intent.provider_transaction_order_id=transaction.transaction_order_id
                 AND intent.fanvue_account_id=transaction.fanvue_account_id
                LEFT JOIN commercial_publications publication
                  ON publication.publication_id=intent.commercial_publication_id
                WHERE mapping.telegram_user_id=%s AND mapping.is_active
                  AND mapping.verification_status='VERIFIED'
                  AND (%s::BIGINT IS NULL OR profile.creator_profile_id=%s)
                  AND (%s::BIGINT IS NULL OR profile.fanvue_account_id=%s)
                  AND NOT (
                    COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                    OR COALESCE(publication.publication_metadata->>'purpose','')
                         ILIKE 'controlled_smoke_test%%'
                    OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','')
                         ILIKE 'CONTROLLED_TEST%%'
                  )""",(
                    telegram_user_id, creator_profile_id, creator_profile_id,
                    fanvue_account_id, fanvue_account_id,
                  ))
            row=cursor.fetchone()
        purchases=int((row or {}).get("purchase_count") or 0)
        gross=int((row or {}).get("lifetime_gross_minor") or 0)
        return {"verified_buyer":purchases>0,"repeat_buyer":purchases>1,
                "high_value_buyer":gross>=50000}

    def release_due_availability(self, *, account_scope, now,
                                 creator_profile_id=None,
                                 fanvue_account_id=None):
        """Atomically collapse each quiet burst to its latest authoritative turn."""
        from app.services.ordinary_reply_retry_policy import OrdinaryReplyRetryPolicy
        retry_reason = OrdinaryReplyRetryPolicy.sql_reason_predicate("last_error")
        retry_reason_o = OrdinaryReplyRetryPolicy.sql_reason_predicate("o.last_error")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""UPDATE ordinary_chat_reply_operations current SET
                state='TERMINAL_FAILED',next_retry_at=NULL,failed_at=COALESCE(failed_at,%s),
                last_error='GENERATION_RETRY_BUDGET_EXHAUSTED',updated_at=%s
              WHERE current.telegram_account_scope=%s AND current.state='RETRYABLE'
                AND current.response_payload IS NULL AND current.send_attempt_count=0
                AND current.generation_attempt_count>=current.max_generation_attempts
                AND {OrdinaryReplyRetryPolicy.sql_reason_predicate('current.last_error')}""",
                (now, now, account_scope))
            cursor.execute(f"""UPDATE ordinary_chat_reply_operations current SET
                state='SUPPRESSED',next_retry_at=NULL,
                last_error='retry_invalidated_before_generation',updated_at=%s
              WHERE current.telegram_account_scope=%s AND current.state='RETRYABLE'
                AND current.response_payload IS NULL AND current.send_attempt_count=0
                AND current.last_error<>'availability_deferred'
                AND current.outbound_telegram_message_id IS NULL
                AND current.sent_confirmed_at IS NULL
                AND current.next_retry_at<=%s
                AND current.generation_attempt_count<current.max_generation_attempts
                AND {OrdinaryReplyRetryPolicy.sql_reason_predicate('current.last_error')}
                AND (EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                      WHERE newer.telegram_account_scope=current.telegram_account_scope
                        AND newer.telegram_chat_id=current.telegram_chat_id
                        AND newer.telegram_message_id>COALESCE(
                            current.burst_freshness_telegram_message_id,
                            current.inbound_telegram_message_id))
                  OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer_operation
                      WHERE newer_operation.telegram_account_scope=current.telegram_account_scope
                        AND newer_operation.telegram_chat_id=current.telegram_chat_id
                        AND newer_operation.inbound_telegram_message_id>COALESCE(
                            current.burst_freshness_telegram_message_id,
                            current.inbound_telegram_message_id)
                        AND (current.conversation_burst_id IS NULL OR
                             newer_operation.conversation_burst_id IS DISTINCT FROM
                                 current.conversation_burst_id))
                  OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                      WHERE answered.telegram_account_scope=current.telegram_account_scope
                        AND answered.telegram_chat_id=current.telegram_chat_id
                        AND answered.state='SENT_CONFIRMED'
                        AND answered.sent_confirmed_at>current.inbound_received_at))""",
                (now, account_scope, now))
            cursor.execute("""SELECT pg_advisory_xact_lock(
                    hashtextextended(%s||':'||due.telegram_chat_id::text,0))
                FROM (SELECT DISTINCT telegram_chat_id
                    FROM ordinary_chat_reply_operations
                    WHERE telegram_account_scope=%s AND state='RETRYABLE'
                      AND response_payload IS NULL AND send_attempt_count=0
                      AND next_retry_at<=%s) due
                ORDER BY due.telegram_chat_id""", (account_scope, account_scope, now))
            cursor.execute(f"""WITH candidates AS (
                SELECT operation_id,telegram_chat_id,next_retry_at,
                       MAX(inbound_telegram_message_id) OVER(
                         PARTITION BY telegram_chat_id) AS latest_message_id,
                       CASE
                         WHEN COALESCE(inbound_message_text,'') ~* %s THEN 2
                         WHEN COALESCE(inbound_message_text,'') ~* %s THEN 1
                         ELSE 0 END AS obligation_priority,
                       inbound_telegram_message_id,
                       COALESCE(burst_member_obligations,'[]'::jsonb) member_obligations
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NULL AND send_attempt_count=0
                  AND {retry_reason}
                  AND generation_attempt_count<max_generation_attempts
            ), ranked AS (
                SELECT *,ROW_NUMBER() OVER(PARTITION BY telegram_chat_id
                    ORDER BY obligation_priority DESC,
                             inbound_telegram_message_id DESC) AS rank,
                    FIRST_VALUE(operation_id) OVER(PARTITION BY telegram_chat_id
                      ORDER BY obligation_priority DESC,
                               inbound_telegram_message_id DESC) AS survivor_id,
                    MAX(inbound_telegram_message_id) OVER(
                      PARTITION BY telegram_chat_id) AS freshness_message_id
                FROM candidates
            ), due_chats AS (
                SELECT telegram_chat_id FROM candidates
                WHERE inbound_telegram_message_id=latest_message_id
                  AND next_retry_at<=%s
            ), obligation_union AS (
                SELECT candidate.telegram_chat_id,
                       COALESCE(jsonb_agg(DISTINCT obligation.value
                           ORDER BY obligation.value) FILTER (
                             WHERE obligation.value IS NOT NULL), '[]'::jsonb) obligations
                  FROM candidates candidate
                  LEFT JOIN LATERAL jsonb_array_elements_text(
                    candidate.member_obligations) obligation(value) ON TRUE
                 GROUP BY candidate.telegram_chat_id
            ) UPDATE ordinary_chat_reply_operations o SET
                conversation_burst_id=r.survivor_id,
                burst_survivor_operation_id=r.survivor_id,
                burst_role=CASE WHEN r.rank=1 THEN 'SURVIVOR' ELSE 'MEMBER' END,
                burst_freshness_telegram_message_id=GREATEST(
                    COALESCE(o.burst_freshness_telegram_message_id,
                             r.freshness_message_id),
                    r.freshness_message_id),
                burst_obligations=obligation_union.obligations,
                state=CASE WHEN r.rank=1 THEN o.state ELSE 'SUPPRESSED' END,
                next_retry_at=CASE WHEN r.rank=1 THEN o.next_retry_at ELSE NULL END,
                last_error=CASE WHEN r.rank=1 THEN o.last_error
                                ELSE 'availability_burst_coalesced' END,
                delivery_payload=COALESCE(o.delivery_payload,'{{}}'::jsonb)||
                  jsonb_build_object('conversationBurst',jsonb_build_object(
                    'burstId',r.survivor_id::text,
                    'survivorOperationId',r.survivor_id::text,
                    'role',CASE WHEN r.rank=1 THEN 'SURVIVOR' ELSE 'MEMBER' END,
                    'freshnessMessageId',GREATEST(
                        COALESCE(o.burst_freshness_telegram_message_id,
                                 r.freshness_message_id),
                        r.freshness_message_id),
                    'obligations',obligation_union.obligations)),
                updated_at=NOW()
            FROM ranked r JOIN due_chats d USING (telegram_chat_id)
              JOIN obligation_union USING (telegram_chat_id)
            WHERE o.operation_id=r.operation_id""", (
                r"\?|(^|\W)(who|what|when|where|why|how|can|could|would|do|does|did|are|is|will)(\W|$)",
                r"(^|\W)(buy|price|purchase|unlock|offer|available|content|photo|video|set)(\W|$)",
                account_scope, now,
            ))
            cursor.execute(f"""WITH ready AS (
                SELECT o.operation_id FROM ordinary_chat_reply_operations o
                WHERE o.telegram_account_scope=%s AND o.state='RETRYABLE'
                  AND o.response_payload IS NULL AND o.send_attempt_count=0
                  AND {retry_reason_o} AND o.next_retry_at<=%s
                  AND o.generation_attempt_count<o.max_generation_attempts
                  AND o.outbound_telegram_message_id IS NULL
                  AND o.sent_confirmed_at IS NULL
                  AND (o.claim_owner IS NULL OR o.lease_expires_at<=%s)
                  AND (%s::bigint IS NULL OR EXISTS(
                    SELECT 1 FROM telegram_sales_prospects prospect
                    WHERE prospect.creator_profile_id=%s
                      AND prospect.fanvue_account_id=%s
                      AND prospect.telegram_user_id=o.inbound_sender_telegram_user_id
                      AND prospect.telegram_chat_id=o.telegram_chat_id))
                  AND (%s::bigint IS NULL OR COALESCE((SELECT control.mode
                    FROM telegram_relationship_controls control
                    WHERE control.creator_profile_id=%s
                      AND control.fanvue_account_id=%s
                      AND control.telegram_user_id=o.inbound_sender_telegram_user_id
                      AND control.telegram_chat_id=o.telegram_chat_id LIMIT 1),
                    'AVA_AUTO')='AVA_AUTO')
                  AND (%s::bigint IS NULL OR COALESCE((SELECT control.communication_disposition
                    FROM telegram_relationship_controls control
                    WHERE control.creator_profile_id=%s
                      AND control.fanvue_account_id=%s
                      AND control.telegram_user_id=o.inbound_sender_telegram_user_id
                      AND control.telegram_chat_id=o.telegram_chat_id LIMIT 1),
                    'ACTIVE')='ACTIVE')
                  AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                    WHERE newer.telegram_account_scope=o.telegram_account_scope
                      AND newer.telegram_chat_id=o.telegram_chat_id
                      AND newer.state='RETRYABLE' AND newer.response_payload IS NULL
                      AND {OrdinaryReplyRetryPolicy.sql_reason_predicate('newer.last_error')}
                      AND newer.inbound_telegram_message_id>o.inbound_telegram_message_id)
            ) UPDATE ordinary_chat_reply_operations o SET
                state='PENDING_GENERATION',next_retry_at=NULL,last_error=NULL,
                updated_at=NOW() FROM ready WHERE o.operation_id=ready.operation_id
                  AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations answered
                    WHERE answered.telegram_account_scope=o.telegram_account_scope
                      AND answered.telegram_chat_id=o.telegram_chat_id
                      AND answered.state='SENT_CONFIRMED'
                      AND answered.sent_confirmed_at>o.inbound_received_at)
                  AND (%s::bigint IS NULL OR NOT EXISTS(
                    SELECT 1 FROM telegram_operator_message_operations manual
                    WHERE manual.creator_profile_id=%s
                      AND manual.fanvue_account_id=%s
                      AND manual.telegram_user_id=o.inbound_sender_telegram_user_id
                      AND manual.telegram_chat_id=o.telegram_chat_id
                      AND manual.state='CONFIRMED'
                      AND manual.confirmed_at>o.inbound_received_at))
                RETURNING o.*""", (
                    account_scope, now, now,
                    creator_profile_id, creator_profile_id, fanvue_account_id,
                    creator_profile_id, creator_profile_id, fanvue_account_id,
                    creator_profile_id, creator_profile_id, fanvue_account_id,
                    creator_profile_id, creator_profile_id, fanvue_account_id,
                ))
            rows = cursor.fetchall()
            connection.commit()
        return [self._item(row) for row in rows]

    def high_value_priority_keys(self, operations):
        """Return active HVP relationship keys for an already-eligible batch."""
        keys = {(int(item.inbound_sender_telegram_user_id), int(item.telegram_chat_id))
                for item in operations}
        if not keys:
            return set()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT telegram_user_id,telegram_chat_id
                FROM telegram_relationship_value_overrides
                WHERE removed_at IS NULL AND classification='HIGH_VALUE_PROSPECT'""")
            return ({(int(row["telegram_user_id"]), int(row["telegram_chat_id"]))
                     for row in cursor.fetchall()} & keys)

    def market_tier_priority_buckets(self, operations, *, creator_profile_id,
                                     fanvue_account_id):
        """Rank an already-due batch without changing eligibility or dropping work."""
        keys = {(int(item.inbound_sender_telegram_user_id), int(item.telegram_chat_id))
                for item in operations}
        if not keys:
            return {}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT telegram_user_id,telegram_chat_id,market_tier
                FROM telegram_relationship_market_tiers
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND removed_at IS NULL""", (creator_profile_id, fanvue_account_id))
            tiers = {(int(row["telegram_user_id"]), int(row["telegram_chat_id"])):
                     row["market_tier"] for row in cursor.fetchall()}
            cursor.execute("""SELECT telegram_user_id,telegram_chat_id
                FROM telegram_relationship_value_overrides
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND removed_at IS NULL AND classification='HIGH_VALUE_PROSPECT'""",
                (creator_profile_id, fanvue_account_id))
            hvp = {(int(row["telegram_user_id"]), int(row["telegram_chat_id"]))
                   for row in cursor.fetchall()}
        result = {}
        for key in keys:
            tier = tiers.get(key, "UNCLASSIFIED")
            result[key] = (0 if tier == "HIGH" and key in hvp else
                           1 if tier == "HIGH" else
                           2 if key in hvp and tier in {"MEDIUM", "UNCLASSIFIED"} else
                           4 if tier == "LOW" else 3)
        return result

    def pending_backlog(self, *, account_scope, limit=100):
        """Read dormant reconciled obligations; activation authority is enforced by runtime."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='PENDING_GENERATION'
                  AND correlation_id LIKE 'backlog:%%' AND response_payload IS NULL
                  AND generation_attempt_count=0 AND send_attempt_count=0
                ORDER BY inbound_received_at,inbound_telegram_message_id LIMIT %s""",
                (account_scope, max(1, int(limit))))
            return [self._item(row) for row in cursor.fetchall()]

    def reclaim_stranded_pending_generation(
        self, *, account_scope, creator_profile_id, fanvue_account_id,
        owner, now, limit=25,
    ):
        """Reserve current, definitively untouched live operations for normal scheduling.

        This is deliberately narrower than a generic PENDING_GENERATION scan.  The
        lease is a recovery reservation only: the caller must route the returned
        inbound through the ordinary availability decision, which clears it when
        scheduling is persisted.  Expiry makes a crash before that transition
        restart-safe; ``SKIP LOCKED`` plus the lease makes competing scans
        single-winner.
        """
        lease_seconds = self.PENDING_RECLAMATION_LEASE_SECONDS
        evidence = json.dumps({"pendingGenerationReclamation": {
            "authority": "OrdinaryChatReplyRepository",
            "claimedAt": now.isoformat(),
            "directGeneration": False,
            "directSend": False,
        }})
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""WITH candidates AS (
              SELECT candidate.operation_id
                FROM ordinary_chat_reply_operations candidate
               WHERE candidate.telegram_account_scope=%s
                 AND candidate.state='PENDING_GENERATION'
                 AND candidate.generation_attempt_count=0
                 AND candidate.send_attempt_count=0
                 AND candidate.response_payload IS NULL
                 AND candidate.response_text IS NULL
                 AND candidate.outbound_telegram_message_id IS NULL
                 AND candidate.sent_confirmed_at IS NULL
                 AND candidate.sending_at IS NULL
                 AND (candidate.claim_owner IS NULL
                      OR candidate.lease_expires_at<=%s)
                 AND EXISTS (SELECT 1 FROM telegram_sales_prospects prospect
                   WHERE prospect.creator_profile_id=%s
                     AND prospect.fanvue_account_id=%s
                     AND prospect.telegram_user_id=candidate.inbound_sender_telegram_user_id
                     AND prospect.telegram_chat_id=candidate.telegram_chat_id)
                 AND COALESCE((SELECT control.mode
                   FROM telegram_relationship_controls control
                  WHERE control.creator_profile_id=%s
                    AND control.fanvue_account_id=%s
                    AND control.telegram_user_id=candidate.inbound_sender_telegram_user_id
                    AND control.telegram_chat_id=candidate.telegram_chat_id
                  LIMIT 1),'AVA_AUTO')='AVA_AUTO'
                 AND COALESCE((SELECT control.communication_disposition
                   FROM telegram_relationship_controls control
                  WHERE control.creator_profile_id=%s
                    AND control.fanvue_account_id=%s
                    AND control.telegram_user_id=candidate.inbound_sender_telegram_user_id
                    AND control.telegram_chat_id=candidate.telegram_chat_id
                  LIMIT 1),'ACTIVE')<>'IGNORED'
                 AND NOT EXISTS (SELECT 1 FROM telegram_private_inbound_messages newer
                   WHERE newer.telegram_account_scope=candidate.telegram_account_scope
                     AND newer.telegram_chat_id=candidate.telegram_chat_id
                     AND newer.telegram_message_id>COALESCE(
                         candidate.burst_freshness_telegram_message_id,
                         candidate.inbound_telegram_message_id))
                 AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                   WHERE newer.telegram_account_scope=candidate.telegram_account_scope
                     AND newer.telegram_chat_id=candidate.telegram_chat_id
                     AND newer.inbound_telegram_message_id>COALESCE(
                         candidate.burst_freshness_telegram_message_id,
                         candidate.inbound_telegram_message_id)
                     AND (candidate.conversation_burst_id IS NULL OR
                          newer.conversation_burst_id IS DISTINCT FROM
                              candidate.conversation_burst_id))
                 AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations answered
                   WHERE answered.telegram_account_scope=candidate.telegram_account_scope
                     AND answered.telegram_chat_id=candidate.telegram_chat_id
                     AND answered.state='SENT_CONFIRMED'
                     AND answered.sent_confirmed_at>candidate.inbound_received_at)
                 AND NOT EXISTS (SELECT 1 FROM telegram_operator_message_operations manual
                   WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                     AND manual.telegram_user_id=candidate.inbound_sender_telegram_user_id
                     AND manual.telegram_chat_id=candidate.telegram_chat_id
                     AND manual.state='CONFIRMED'
                     AND manual.confirmed_at>candidate.inbound_received_at)
               ORDER BY candidate.inbound_received_at,candidate.operation_id
               FOR UPDATE OF candidate SKIP LOCKED LIMIT %s
            ) UPDATE ordinary_chat_reply_operations operation SET
                claim_owner=%s,claimed_at=%s,
                lease_expires_at=%s+(%s*INTERVAL '1 second'),
                delivery_payload=COALESCE(operation.delivery_payload,'{}'::jsonb)||%s::jsonb,
                updated_at=NOW()
              FROM candidates
             WHERE operation.operation_id=candidates.operation_id
             RETURNING operation.*""", (
                account_scope, now, creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                max(1, int(limit)), owner, now, now, lease_seconds, evidence,
            ))
            rows = cursor.fetchall()
            connection.commit()
        return [self._item(row) for row in rows]

    def maintain_stranded_lifecycle(
        self, *, account_scope, creator_profile_id, fanvue_account_id,
        now, limit=25,
    ):
        """Converge definitively stale ordinary work without weakening claims.

        Current expired GENERATING rows are only discovered here.  The caller
        routes them through the normal inbound path, where ``claim_generation``
        remains the single-winner generation authority.  Superseded work and
        generated replies invalidated by a relationship-control epoch are
        terminalized under row locks and can never re-enter provider/send work.
        SEND_UNCERTAIN is intentionally outside this maintenance authority.
        """
        bounded = max(1, min(int(limit), 100))
        result = {
            "expiredGeneratingFound": 0,
            "expiredGeneratingReclaimed": 0,
            "expiredGeneratingSuperseded": 0,
            "pendingSupersededFinalized": 0,
            "unscheduledRetryableFound": 0,
            "unscheduledRetryableFinalizedOrRescheduled": 0,
            "reclaimable": [],
        }
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT candidate.*,
                    EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                      WHERE newer.telegram_account_scope=candidate.telegram_account_scope
                        AND newer.telegram_chat_id=candidate.telegram_chat_id
                        AND newer.telegram_message_id>COALESCE(
                            candidate.burst_freshness_telegram_message_id,
                            candidate.inbound_telegram_message_id)
                        AND (BTRIM(COALESCE(newer.customer_text,''))<>'' OR
                             (newer.has_media IS TRUE AND
                              newer.reconciliation_state<>'NO_RESPONSE_REQUIRED'))) newer_inbound,
                    EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                      WHERE newer.telegram_account_scope=candidate.telegram_account_scope
                        AND newer.telegram_chat_id=candidate.telegram_chat_id
                        AND newer.inbound_telegram_message_id>COALESCE(
                            candidate.burst_freshness_telegram_message_id,
                            candidate.inbound_telegram_message_id)
                        AND (candidate.conversation_burst_id IS NULL OR
                             newer.conversation_burst_id IS DISTINCT FROM
                                 candidate.conversation_burst_id)) newer_operation,
                    EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                      WHERE answered.telegram_account_scope=candidate.telegram_account_scope
                        AND answered.telegram_chat_id=candidate.telegram_chat_id
                        AND answered.state='SENT_CONFIRMED'
                        AND answered.sent_confirmed_at>candidate.inbound_received_at) later_auto,
                    EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                      WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                        AND manual.telegram_user_id=candidate.inbound_sender_telegram_user_id
                        AND manual.telegram_chat_id=candidate.telegram_chat_id
                        AND manual.state='CONFIRMED'
                        AND manual.confirmed_at>candidate.inbound_received_at) later_manual
                FROM ordinary_chat_reply_operations candidate
                WHERE candidate.telegram_account_scope=%s
                  AND candidate.state='GENERATING'
                  AND (candidate.claim_owner IS NULL OR candidate.lease_expires_at IS NULL
                       OR candidate.lease_expires_at<=%s)
                  AND candidate.response_payload IS NULL
                  AND candidate.response_text IS NULL
                  AND candidate.outbound_telegram_message_id IS NULL
                  AND candidate.sent_confirmed_at IS NULL
                  AND candidate.generation_attempt_count<candidate.max_generation_attempts
                ORDER BY candidate.updated_at,candidate.operation_id
                FOR UPDATE OF candidate SKIP LOCKED LIMIT %s""", (
                    creator_profile_id, fanvue_account_id, account_scope, now, bounded,
                ))
            expired = [dict(row) for row in cursor.fetchall()]
            result["expiredGeneratingFound"] = len(expired)
            for candidate in expired:
                superseded = any(candidate[key] for key in (
                    "newer_inbound", "newer_operation", "later_auto", "later_manual"
                ))
                if not superseded:
                    cursor.execute("""SELECT COALESCE((SELECT control.mode
                          FROM telegram_relationship_controls control
                         WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                           AND control.telegram_user_id=%s AND control.telegram_chat_id=%s
                         LIMIT 1),'AVA_AUTO') mode,
                        COALESCE((SELECT control.communication_disposition
                          FROM telegram_relationship_controls control
                         WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                           AND control.telegram_user_id=%s AND control.telegram_chat_id=%s
                         LIMIT 1),'ACTIVE') disposition""", (
                            creator_profile_id, fanvue_account_id,
                            candidate["inbound_sender_telegram_user_id"], candidate["telegram_chat_id"],
                            creator_profile_id, fanvue_account_id,
                            candidate["inbound_sender_telegram_user_id"], candidate["telegram_chat_id"],
                        ))
                    control = cursor.fetchone()
                    if control["mode"] == "AVA_AUTO" and control["disposition"] == "ACTIVE":
                        operation_values = {key: value for key, value in candidate.items()
                            if key not in {"newer_inbound", "newer_operation",
                                           "later_auto", "later_manual"}}
                        result["reclaimable"].append(self._item(operation_values))
                    continue
                evidence = {"expiredGenerationSupersession": {
                    "authority": "OrdinaryChatReplyRepository",
                    "terminalizedAt": now.isoformat(),
                    "reason": "SUPERSEDED_AFTER_EXPIRED_GENERATION_CLAIM",
                    "originalState": "GENERATING",
                    "originalClaimOwner": candidate.get("claim_owner"),
                    "originalClaimedAt": candidate.get("claimed_at").isoformat()
                        if candidate.get("claimed_at") else None,
                    "originalLeaseExpiresAt": candidate.get("lease_expires_at").isoformat()
                        if candidate.get("lease_expires_at") else None,
                    "originalGenerationAttempts": candidate.get("generation_attempt_count"),
                    "newerInbound": bool(candidate["newer_inbound"]),
                    "newerOperation": bool(candidate["newer_operation"]),
                    "laterAutomaticResponse": bool(candidate["later_auto"]),
                    "laterManualResponse": bool(candidate["later_manual"]),
                }}
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    state='SUPPRESSED',last_error='SUPERSEDED_AFTER_EXPIRED_GENERATION_CLAIM',
                    next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                    delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                    updated_at=NOW()
                    WHERE operation_id=%s AND state='GENERATING'
                      AND (claim_owner IS NULL OR lease_expires_at IS NULL
                           OR lease_expires_at<=%s)
                    RETURNING operation_id""", (
                        json.dumps(evidence), candidate["operation_id"], now,
                    ))
                result["expiredGeneratingSuperseded"] += int(cursor.fetchone() is not None)

            cursor.execute("""WITH candidates AS (
                SELECT pending.operation_id,pending.claim_owner,pending.claimed_at,
                       pending.lease_expires_at,pending.generation_attempt_count,
                       pending.inbound_telegram_message_id,
                       GREATEST(
                         (SELECT MAX(archived.telegram_message_id)
                            FROM telegram_private_inbound_messages archived
                           WHERE archived.telegram_account_scope=pending.telegram_account_scope
                             AND archived.telegram_chat_id=pending.telegram_chat_id
                             AND archived.telegram_message_id>COALESCE(
                                 pending.burst_freshness_telegram_message_id,
                                 pending.inbound_telegram_message_id)
                             AND (BTRIM(COALESCE(archived.customer_text,''))<>'' OR
                                  (archived.has_media IS TRUE AND
                                   archived.reconciliation_state<>'NO_RESPONSE_REQUIRED'))),
                         (SELECT MAX(newer_operation.inbound_telegram_message_id)
                            FROM ordinary_chat_reply_operations newer_operation
                           WHERE newer_operation.telegram_account_scope=pending.telegram_account_scope
                             AND newer_operation.telegram_chat_id=pending.telegram_chat_id
                             AND newer_operation.inbound_telegram_message_id>COALESCE(
                                 pending.burst_freshness_telegram_message_id,
                                 pending.inbound_telegram_message_id)
                             AND (pending.conversation_burst_id IS NULL OR
                                  newer_operation.conversation_burst_id IS DISTINCT FROM
                                      pending.conversation_burst_id))
                       ) superseding_inbound_id
                  FROM ordinary_chat_reply_operations pending
                 WHERE pending.telegram_account_scope=%s
                   AND pending.state='PENDING_GENERATION'
                   AND (pending.claim_owner IS NULL OR pending.lease_expires_at IS NULL
                        OR pending.lease_expires_at<=%s)
                   AND pending.response_payload IS NULL AND pending.response_text IS NULL
                   AND pending.outbound_telegram_message_id IS NULL
                   AND EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer_operation
                         WHERE newer_operation.telegram_account_scope=pending.telegram_account_scope
                           AND newer_operation.telegram_chat_id=pending.telegram_chat_id
                           AND newer_operation.inbound_telegram_message_id>COALESCE(
                               pending.burst_freshness_telegram_message_id,
                               pending.inbound_telegram_message_id)
                           AND (pending.conversation_burst_id IS NULL OR
                                newer_operation.conversation_burst_id IS DISTINCT FROM
                                    pending.conversation_burst_id))
                 ORDER BY pending.updated_at,pending.operation_id
                 FOR UPDATE OF pending SKIP LOCKED LIMIT %s
            ) UPDATE ordinary_chat_reply_operations pending SET
                state='SUPPRESSED',last_error='SUPERSEDED_PENDING_GENERATION',
                next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                delivery_payload=COALESCE(pending.delivery_payload,'{}'::jsonb)||
                  jsonb_build_object('pendingGenerationSupersession',jsonb_build_object(
                    'authority','OrdinaryChatReplyRepository',
                    'terminalizedAt',%s::text,
                    'reason','SUPERSEDED_PENDING_GENERATION',
                    'originalState','PENDING_GENERATION',
                    'originalGenerationAttempts',candidates.generation_attempt_count,
                    'supersedingInboundId',candidates.superseding_inbound_id)),
                updated_at=NOW()
              FROM candidates WHERE pending.operation_id=candidates.operation_id
              RETURNING pending.operation_id""", (
                account_scope, now, bounded, now.isoformat(),
            ))
            result["pendingSupersededFinalized"] = len(cursor.fetchall())

            cursor.execute("""SELECT operation_id,last_error FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NOT NULL AND next_retry_at IS NULL
                  AND outbound_telegram_message_id IS NULL
                  AND (claim_owner IS NULL OR lease_expires_at IS NULL OR lease_expires_at<=%s)
                ORDER BY updated_at,operation_id
                FOR UPDATE SKIP LOCKED LIMIT %s""", (account_scope, now, bounded))
            unscheduled = [dict(row) for row in cursor.fetchall()]
            result["unscheduledRetryableFound"] = len(unscheduled)
            for candidate in unscheduled:
                reason = str(candidate.get("last_error") or "")
                if reason not in {
                    "deterministic_delivery_block:RELATIONSHIP_HUMAN_OPERATOR_ACTIVE",
                    "deterministic_delivery_block:RELATIONSHIP_IGNORED",
                }:
                    continue
                evidence = {"relationshipControlInvalidation": {
                    "authority": "OrdinaryChatReplyRepository",
                    "terminalizedAt": now.isoformat(),
                    "originalState": "RETRYABLE",
                    "originalError": reason,
                    "generatedPayloadPreservedForAudit": True,
                    "automaticResumptionAllowed": False,
                }}
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    state='SUPPRESSED',last_error='AUTOMATIC_REPLY_INVALIDATED_BY_RELATIONSHIP_CONTROL',
                    next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                    delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                    updated_at=NOW()
                    WHERE operation_id=%s AND state='RETRYABLE'
                      AND response_payload IS NOT NULL AND next_retry_at IS NULL
                    RETURNING operation_id""", (json.dumps(evidence), candidate["operation_id"]))
                result["unscheduledRetryableFinalizedOrRescheduled"] += int(
                    cursor.fetchone() is not None
                )
            connection.commit()
        return result

    def due_generated_send_retries(self, *, account_scope, now, limit=100):
        """Read definitively-unsent generated work due for the normal send claim.

        This does not claim or mutate rows. ``claim_send`` remains the single
        atomic concurrency boundary, so competing runtimes cannot both send.
        SEND_UNCERTAIN is deliberately outside this query.
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NOT NULL
                  AND outbound_telegram_message_id IS NULL
                  AND send_attempt_count<max_send_attempts
                  AND next_retry_at IS NOT NULL AND next_retry_at<=%s
                  AND claim_owner IS NULL
                ORDER BY next_retry_at,inbound_received_at
                LIMIT %s""", (account_scope, now, max(1, int(limit))))
            return [self._item(row) for row in cursor.fetchall()]

    def recover_stranded_generated(
        self, *, account_scope, creator_profile_id, fanvue_account_id,
        now, limit=25,
    ):
        """Atomically settle definitively-unsent GENERATED work.

        A short grace period excludes the normal generated -> pacing -> send
        window. Error/corrective fallbacks are discarded for fresh generation;
        other current payloads retain their bytes and re-enter the existing
        durable send-claim path. ``FOR UPDATE SKIP LOCKED`` makes concurrent
        recovery scans single-winner without weakening ``claim_send``.
        """
        recovery_reason = "stranded_generated_recovery"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT candidate.*,
                COALESCE(candidate.response_payload#>>'{diagnostic_metadata,generation_fallback,applied}','false')='true'
                  OR COALESCE(candidate.response_payload->>'error_code','')='decision_engine_exception'
                  OR COALESCE(candidate.delivery_payload#>>'{qualityCorrectiveRetry,required}','false')='true'
                  AS fresh_generation_required
              FROM ordinary_chat_reply_operations candidate
             WHERE candidate.telegram_account_scope=%s
               AND candidate.state='GENERATED'
               AND candidate.response_payload IS NOT NULL
               AND candidate.sending_at IS NULL
               AND candidate.outbound_telegram_message_id IS NULL
               AND candidate.sent_confirmed_at IS NULL
               AND candidate.send_attempt_count=0
               AND candidate.next_retry_at IS NULL
               AND (candidate.claim_owner IS NULL OR candidate.lease_expires_at<=%s)
               AND candidate.updated_at<=%s-(%s*INTERVAL '1 second')
               AND EXISTS (SELECT 1 FROM telegram_sales_prospects prospect
                 WHERE prospect.creator_profile_id=%s
                   AND prospect.fanvue_account_id=%s
                   AND prospect.telegram_user_id=candidate.inbound_sender_telegram_user_id
                   AND prospect.telegram_chat_id=candidate.telegram_chat_id)
               AND COALESCE((SELECT control.mode FROM telegram_relationship_controls control
                 WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                   AND control.telegram_user_id=candidate.inbound_sender_telegram_user_id
                   AND control.telegram_chat_id=candidate.telegram_chat_id LIMIT 1),'AVA_AUTO')='AVA_AUTO'
               AND COALESCE((SELECT control.communication_disposition
                 FROM telegram_relationship_controls control
                 WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                   AND control.telegram_user_id=candidate.inbound_sender_telegram_user_id
                   AND control.telegram_chat_id=candidate.telegram_chat_id LIMIT 1),'ACTIVE')<>'IGNORED'
               AND NOT EXISTS (SELECT 1 FROM telegram_private_inbound_messages newer
                 WHERE newer.telegram_chat_id=candidate.telegram_chat_id
                   AND newer.telegram_message_id>COALESCE(
                       candidate.burst_freshness_telegram_message_id,
                       candidate.inbound_telegram_message_id))
               AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                 WHERE newer.telegram_account_scope=candidate.telegram_account_scope
                   AND newer.telegram_chat_id=candidate.telegram_chat_id
                   AND newer.inbound_telegram_message_id>COALESCE(
                       candidate.burst_freshness_telegram_message_id,
                       candidate.inbound_telegram_message_id)
                   AND (candidate.conversation_burst_id IS NULL OR
                        newer.conversation_burst_id IS DISTINCT FROM
                            candidate.conversation_burst_id))
               AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations answered
                 WHERE answered.telegram_account_scope=candidate.telegram_account_scope
                   AND answered.telegram_chat_id=candidate.telegram_chat_id
                   AND answered.state='SENT_CONFIRMED'
                   AND answered.sent_confirmed_at>candidate.inbound_received_at)
               AND NOT EXISTS (SELECT 1 FROM telegram_operator_message_operations manual
                 WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                   AND manual.telegram_user_id=candidate.inbound_sender_telegram_user_id
                   AND manual.telegram_chat_id=candidate.telegram_chat_id
                   AND manual.state='CONFIRMED'
                   AND manual.confirmed_at>candidate.inbound_received_at)
             ORDER BY candidate.updated_at,candidate.operation_id
             FOR UPDATE OF candidate SKIP LOCKED LIMIT %s""", (
                account_scope, now, now, self.STRANDED_GENERATED_GRACE_SECONDS,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id, max(1, int(limit)),
            ))
            candidates = cursor.fetchall()
            recovered = []
            for candidate in candidates:
                fresh = bool(candidate.pop("fresh_generation_required", False))
                fallback = dict(
                    dict(candidate.get("response_payload") or {}).get(
                        "diagnostic_metadata") or {}
                ).get("generation_fallback")
                evidence = {"strandedGeneratedRecovery": {
                    "authority": "OrdinaryChatReplyRepository",
                    "reason": recovery_reason,
                    "recoveredAt": now.isoformat(),
                    "freshGenerationRequired": fresh,
                    "previousCandidateReused": not fresh,
                    "previousGenerationFallback": fallback if fresh else None,
                }}
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    state='RETRYABLE',
                    response_payload=CASE WHEN %s THEN NULL ELSE response_payload END,
                    response_text=CASE WHEN %s THEN NULL ELSE response_text END,
                    response_content_sha256=CASE WHEN %s THEN NULL ELSE response_content_sha256 END,
                    generated_at=CASE WHEN %s THEN NULL ELSE generated_at END,
                    delivery_payload=(CASE WHEN %s
                      THEN COALESCE(delivery_payload,'{}'::jsonb)-'message_text'-'type'
                      ELSE COALESCE(delivery_payload,'{}'::jsonb) END)||%s::jsonb,
                    next_retry_at=%s,last_error=%s,
                    claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
                  WHERE operation_id=%s AND state='GENERATED'
                    AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
                    AND sent_confirmed_at IS NULL AND sending_at IS NULL
                  RETURNING *""", (
                    fresh, fresh, fresh, fresh, fresh, json.dumps(evidence), now,
                    "availability_deferred" if fresh else recovery_reason,
                    candidate["operation_id"],
                ))
                row = cursor.fetchone()
                if row is not None:
                    recovered.append(self._item(row))
            connection.commit()
        return recovered

    def scrub_recovered_stale_delivery_payload(self, operation_id):
        """Remove inert stale send bytes from an already-recovered fallback."""
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)-'message_text'-'type',
            updated_at=NOW()
          WHERE operation_id=%s AND state='RETRYABLE'
            AND response_payload IS NULL AND response_text IS NULL
            AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
            AND sent_confirmed_at IS NULL
            AND COALESCE(delivery_payload#>>'{strandedGeneratedRecovery,freshGenerationRequired}','false')='true'
          RETURNING *""", (operation_id,))

    def coalesced_burst_messages(self, operation, *, now):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT operation_id,inbound_telegram_message_id,inbound_message_text
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND (operation_id=%s OR (
                    %s::uuid IS NOT NULL AND conversation_burst_id=%s::uuid) OR (
                    %s::uuid IS NULL AND state='SUPPRESSED'
                    AND last_error='availability_burst_coalesced'
                    AND updated_at>=%s-INTERVAL '2 minutes'))
                ORDER BY inbound_telegram_message_id""", (
                operation.telegram_account_scope, operation.telegram_chat_id,
                operation.operation_id, operation.conversation_burst_id,
                operation.conversation_burst_id, operation.conversation_burst_id, now,
            ))
            rows = cursor.fetchall()
        return [{"operation_id": str(row["operation_id"]),
                 "message_id": int(row["inbound_telegram_message_id"]),
                 "text": str(row["inbound_message_text"] or "").strip()}
                for row in rows if str(row["inbound_message_text"] or "").strip()]

    def immediately_preceding_unresolved_semantics(self, operation):
        """Read terminal unresolved meaning without reviving its operation."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT operation_id,inbound_message_text,inbound_received_at,
                       response_payload#>'{diagnostic_metadata,conversationStyle,unsatisfiedTurnObligations}'
                         AS unsatisfied_obligations
                  FROM ordinary_chat_reply_operations
                 WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                   AND inbound_telegram_message_id<%s
                 ORDER BY inbound_telegram_message_id DESC LIMIT 1""", (
                operation.telegram_account_scope, operation.telegram_chat_id,
                operation.inbound_telegram_message_id,
            ))
            row = cursor.fetchone()
        if not row:
            return None
        values = dict(row)
        obligations = values.get("unsatisfied_obligations") or []
        if isinstance(obligations, str):
            try:
                obligations = json.loads(obligations)
            except ValueError:
                obligations = []
        values["unsatisfied_obligations"] = list(obligations)
        prior = self.get(values["operation_id"])
        if (prior is None or prior.state.value != "SUPPRESSED"
                or not str(prior.last_error or "").startswith(
                    ("quality_corrective_retry_exhausted:",
                     "quality_blocked_before_delivery:"))):
            return None
        return values

    def recent_attention_messages(self, operation, *, limit=12):
        """Return bounded inbound evidence for operational attention only."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT inbound_message_text
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND COALESCE(inbound_message_text,'')<>''
                ORDER BY inbound_telegram_message_id DESC LIMIT %s""", (
                operation.telegram_account_scope, operation.telegram_chat_id,
                max(1, int(limit)),
            ))
            rows = cursor.fetchall()
        return [str(row["inbound_message_text"]).strip() for row in reversed(rows)]

    def recent_ava_responses(self, operation, *, limit=6):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT response_text
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND state='SENT_CONFIRMED' AND response_text IS NOT NULL
                  AND operation_id<>%s
                ORDER BY sent_confirmed_at DESC LIMIT %s""", (
                operation.telegram_account_scope, operation.telegram_chat_id,
                operation.operation_id, max(1, int(limit)),
            ))
            rows = cursor.fetchall()
        return [str(row["response_text"]).strip() for row in reversed(rows)]

    def has_recent_confirmed_conversation(self, *, account_scope, chat_id,
                                          sender_user_id, since):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(SELECT 1
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s
                  AND state='SENT_CONFIRMED' AND sent_confirmed_at>=%s
                  AND COALESCE(response_payload->'diagnostic_metadata'->'sleep_context'->>'signoffRequired','false')<>'true'
            ) AS present""", (account_scope, chat_id, sender_user_id, since))
            row = cursor.fetchone()
        return bool(row and row["present"])

    def latest_confirmed_exchange_at(self, *, account_scope, chat_id,
                                     sender_user_id):
        """Return bounded active-conversation evidence without creating state."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT MAX(sent_confirmed_at) AS confirmed_at
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s
                  AND state='SENT_CONFIRMED'
                  AND outbound_telegram_message_id IS NOT NULL""",(
                account_scope,chat_id,sender_user_id))
            row=cursor.fetchone()
        return row.get("confirmed_at") if row else None

    def has_confirmed_sleep_signoff(self, *, account_scope, chat_id, cycle_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(SELECT 1
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND state='SENT_CONFIRMED'
                  AND response_payload->'diagnostic_metadata'->'sleep_context'->>'cycleId'=%s
                  AND response_payload->'diagnostic_metadata'->'sleep_context'->>'signoffRequired'='true'
            ) AS present""", (account_scope, chat_id, cycle_id))
            row = cursor.fetchone()
        return bool(row and row["present"])

    def release_due_sleep_deferred(self, *, account_scope, now):
        """Keep the latest due inbound per chat and suppress the older burst."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""WITH due AS (
                SELECT operation_id,ROW_NUMBER() OVER(
                    PARTITION BY telegram_chat_id ORDER BY inbound_telegram_message_id DESC
                ) AS rank
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NULL AND next_retry_at<=%s
                  AND last_error LIKE 'sleep_deferred:%%'
            ) UPDATE ordinary_chat_reply_operations o SET
                state='SUPPRESSED',last_error='sleep_deferred_consolidated_at_wake',
                next_retry_at=NULL,updated_at=NOW()
                FROM due WHERE o.operation_id=due.operation_id AND due.rank>1""",
                (account_scope, now))
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NULL AND next_retry_at<=%s
                  AND last_error LIKE 'sleep_deferred:%%'
                ORDER BY inbound_received_at""", (account_scope, now))
            rows = cursor.fetchall()
            connection.commit()
        return [self._item(row) for row in rows]

    def store_generated(self, operation_id, *, owner, response_payload,
                        response_text, content_sha256, delivery_payload,
                        conversation_thread_id=None):
        return self._one("""UPDATE ordinary_chat_reply_operations current SET
            state=CASE
              WHEN EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                WHERE newer.telegram_account_scope=current.telegram_account_scope
                  AND newer.telegram_chat_id=current.telegram_chat_id
                  AND newer.inbound_telegram_message_id>COALESCE(
                      current.burst_freshness_telegram_message_id,
                      current.inbound_telegram_message_id)
                  AND (current.conversation_burst_id IS NULL OR
                       newer.conversation_burst_id IS DISTINCT FROM
                           current.conversation_burst_id)
                  AND newer.state NOT IN ('TERMINAL_FAILED','SUPPRESSED'))
                THEN 'SUPPRESSED'
              WHEN current.scheduled_delivery_at IS NOT NULL
                   AND current.scheduled_delivery_at>NOW() THEN 'RETRYABLE'
              ELSE 'GENERATED' END,
            response_payload=%s::jsonb,response_text=%s,
            response_content_sha256=%s,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            conversation_thread_id=COALESCE(conversation_thread_id,%s),
            generated_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=CASE
              WHEN EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                WHERE newer.telegram_account_scope=current.telegram_account_scope
                  AND newer.telegram_chat_id=current.telegram_chat_id
                  AND newer.inbound_telegram_message_id>COALESCE(
                      current.burst_freshness_telegram_message_id,
                      current.inbound_telegram_message_id)
                  AND (current.conversation_burst_id IS NULL OR
                       newer.conversation_burst_id IS DISTINCT FROM
                           current.conversation_burst_id)
                  AND newer.state NOT IN ('TERMINAL_FAILED','SUPPRESSED')) THEN NULL
              WHEN current.scheduled_delivery_at IS NOT NULL
                   AND current.scheduled_delivery_at>NOW()
                THEN current.scheduled_delivery_at ELSE NULL END,
            last_error=CASE
              WHEN EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                WHERE newer.telegram_account_scope=current.telegram_account_scope
                  AND newer.telegram_chat_id=current.telegram_chat_id
                  AND newer.inbound_telegram_message_id>COALESCE(
                      current.burst_freshness_telegram_message_id,
                      current.inbound_telegram_message_id)
                  AND (current.conversation_burst_id IS NULL OR
                       newer.conversation_burst_id IS DISTINCT FROM
                           current.conversation_burst_id)
                  AND newer.state NOT IN ('TERMINAL_FAILED','SUPPRESSED'))
                THEN 'stale_response_suppressed_after_preparation'
              WHEN current.scheduled_delivery_at IS NOT NULL
                   AND current.scheduled_delivery_at>NOW()
                THEN 'prepared_for_scheduled_delivery' ELSE NULL END,
            updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING current.*""",
            (json.dumps(response_payload), response_text, content_sha256,
            json.dumps(delivery_payload), conversation_thread_id, operation_id, owner))

    def store_suppressed_generation(
        self, operation_id, *, owner, response_payload, response_text,
        content_sha256, delivery_payload, reason, conversation_thread_id=None,
    ):
        """Persist an intentional fail-closed generation as terminal/non-sendable."""
        current = self.get(operation_id)
        merged_delivery = self.merge_current_delivery_with_durable_audit(
            getattr(current, "delivery_payload", None), delivery_payload,
        )
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='SUPPRESSED',response_payload=%s::jsonb,response_text=%s,
            response_content_sha256=%s,delivery_payload=%s::jsonb,
            conversation_thread_id=COALESCE(conversation_thread_id,%s),
            generated_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=NULL,last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING *""",
            (json.dumps(response_payload), response_text, content_sha256,
             json.dumps(merged_delivery), conversation_thread_id, reason[:1000],
            operation_id, owner))

    def schedule_quality_correction(
        self, operation_id, *, owner, response_payload, delivery_payload,
        reasons, recent_ava_responses=(), retry_seconds=8,
    ):
        """Durably authorize the sole corrective generation for a required reply."""
        rejected_candidate = str(response_payload.get("response_text") or "").strip()
        excluded_exact_responses = list(dict.fromkeys(
            text for text in (
                rejected_candidate,
                *(str(item).strip() for item in recent_ava_responses),
            ) if text
        ))[:7]
        evidence = {
            "qualityCorrectiveRetry": {
                "required": True,
                "attempt": 2,
                "blockingReasons": list(reasons),
                "previousCandidateBlockedBeforeDelivery": True,
                "previousCandidateText": rejected_candidate,
                "excludedExactResponses": excluded_exact_responses,
                "exclusionAuthority": "FINAL_RESPONSE_EXACT_NOVELTY",
                "previousCandidateDiagnostics": dict(
                    response_payload.get("diagnostic_metadata") or {}
                ),
                "turnObligations": list(dict(
                    dict(response_payload.get("diagnostic_metadata") or {}).get(
                        "conversationStyle") or {}
                ).get("turnObligations") or ()),
                "semanticReferent": dict(
                    dict(response_payload.get("diagnostic_metadata") or {}).get(
                        "conversationCoherence") or {}
                ).get("resolvedCustomerMeaning"),
                "personaDomain": dict(
                    dict(response_payload.get("diagnostic_metadata") or {}).get(
                        "conversationCoherence") or {}
                ).get("resolvedPersonaDomain"),
                "canonicalKnownFacts": list(dict(
                    dict(response_payload.get("diagnostic_metadata") or {}).get(
                        "avaPersonaRuntime") or {}
                ).get("selected_lifestyle_facts") or ()),
                "previousCandidateFailure": ",".join(reasons),
                "offlineAccessAuthority": dict(
                    dict(response_payload.get("diagnostic_metadata") or {}).get(
                        "offlineAccessAuthority") or {}
                ),
                "offlineAccessCorrection": {
                    "required": (
                        "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION" in reasons
                    ),
                    "preserveWarmthAndFantasy": True,
                    "removeRealWorldAvailability": True,
                    "preferredBoundary": "Let's keep things online for now 😊",
                    "maximumGenerationAttempts": 2,
                },
                "commercialAuthorization": {
                    "decision": dict(
                        response_payload.get("diagnostic_metadata") or {}
                    ).get("customer_sales_decision"),
                    "reasonCode": dict(
                        response_payload.get("diagnostic_metadata") or {}
                    ).get("customer_sales_reason_code"),
                    "receptiveness": dict(
                        dict(response_payload.get("diagnostic_metadata") or {}).get(
                            "commercial_receptiveness"
                        ) or {}
                    ),
                    "directQuestionPrecedence": dict(
                        dict(response_payload.get("diagnostic_metadata") or {}).get(
                            "direct_question_precedence"
                        ) or {}
                    ),
                },
            }
        }
        from app.services.corrective_generation_evidence_service import (
            CorrectiveGenerationEvidenceService,
        )
        evidence = {
            "qualityCorrectiveRetry": CorrectiveGenerationEvidenceService.build(
                response_payload=response_payload, reasons=reasons,
                recent_ava_responses=recent_ava_responses, attempt=2,
            )
        }
        current = self.get(operation_id)
        merged_delivery = self.merge_current_delivery_with_durable_audit(
            getattr(current, "delivery_payload", None), delivery_payload,
        )
        return self._one("""UPDATE ordinary_chat_reply_operations current SET
            state=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>COALESCE(
                    current.burst_freshness_telegram_message_id,
                    current.inbound_telegram_message_id)
                AND (current.conversation_burst_id IS NULL OR
                     newer.conversation_burst_id IS DISTINCT FROM
                         current.conversation_burst_id)
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN 'SUPPRESSED' ELSE 'RETRYABLE' END,
            response_payload=NULL,response_text=NULL,response_content_sha256=NULL,
            delivery_payload=COALESCE(%s::jsonb,'{}'::jsonb) || %s::jsonb,
            generated_at=NULL,
            max_generation_attempts=LEAST(max_generation_attempts,generation_attempt_count+1),
            next_retry_at=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>COALESCE(
                    current.burst_freshness_telegram_message_id,
                    current.inbound_telegram_message_id)
                AND (current.conversation_burst_id IS NULL OR
                     newer.conversation_burst_id IS DISTINCT FROM
                         current.conversation_burst_id)
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN NULL ELSE NOW()+(%s*INTERVAL '1 second') END,
            last_error=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>COALESCE(
                    current.burst_freshness_telegram_message_id,
                    current.inbound_telegram_message_id)
                AND (current.conversation_burst_id IS NULL OR
                     newer.conversation_burst_id IS DISTINCT FROM
                         current.conversation_burst_id)
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN 'quality_correction_superseded_by_newer_inbound'
              ELSE 'quality_corrective_retry_scheduled' END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE current.operation_id=%s AND current.state='GENERATING'
              AND current.claim_owner=%s AND (
                  current.generation_attempt_count=1 OR EXISTS(
                    SELECT 1 FROM ordinary_generation_budgets b WHERE b.operation_id=current.operation_id
                      AND b.candidate_count=1 AND NOT b.correction_started))
              AND current.send_attempt_count=0
              AND current.outbound_telegram_message_id IS NULL
            RETURNING current.*""", (
            json.dumps(merged_delivery), json.dumps(evidence),
            max(8, int(retry_seconds)), operation_id, owner,
        ))

    def update_generated_payload(
        self, operation_id, *, response_payload, delivery_payload,
    ):
        """Persist commerce bootstrap data before the first send claim.

        A definitively-unsent commercial bootstrap failure leaves the generated
        response in RETRYABLE.  A successful retry must be able to enrich that
        same response and return it to GENERATED before the durable send claim.
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE operation_id=%s FOR UPDATE""", (operation_id,))
            current = cursor.fetchone()
            if current is None:
                return None
            merged_delivery = self.merge_current_delivery_with_durable_audit(
                current.get("delivery_payload"), delivery_payload,
            )
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='GENERATED',response_payload=%s::jsonb,
                delivery_payload=%s::jsonb,next_retry_at=NULL,last_error=NULL,
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
                WHERE operation_id=%s AND state IN ('GENERATED','RETRYABLE')
                  AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
                  AND response_payload IS NOT NULL
                RETURNING *""", (
                    json.dumps(response_payload), json.dumps(merged_delivery),
                    operation_id,
                ))
            updated = cursor.fetchone()
            connection.commit()
        return self._item(updated) if updated else None

    def fail_generation(self, operation_id, *, owner, reason, retry_seconds=15, evidence=None):
        # Provider resilience is local to the durable provider budget. Never
        # schedule another full analysis pipeline for a system/provider failure.
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='TERMINAL_FAILED',last_error=%s,failed_at=NOW(),next_retry_at=NULL,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING *""",
            (reason[:1000], json.dumps(evidence or {}), operation_id, owner))

    def fail_empty_generation(self, operation_id, *, owner, reason):
        return self.fail_generation(operation_id, owner=owner, reason=reason,
            evidence={'generationFailurePolicy': {'version': 'ORDINARY_RECOVERY_V1',
                      'outcome': 'NO_USABLE_GENERATION_RESULT', 'fullPipelineRetry': False}})

    def suppress(self, operation_id, *, reason, evidence=None):
        return self._one("""UPDATE ordinary_chat_reply_operations SET state='SUPPRESSED',
            last_error=%s,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=NULL,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            updated_at=NOW()
            WHERE operation_id=%s AND state IN (
              'PENDING_GENERATION','GENERATED','RETRYABLE') RETURNING *""",
            (reason[:1000], json.dumps(evidence or {}), operation_id))

    def invalidate_commercial_authority(
        self, *, operation_id, inbound_message_id, purchase_intent_id,
        revalidation_evidence,
    ):
        """Atomically retire one unsent offer denied by current policy."""
        reason = "COMMERCIAL_AUTHORITY_REVOKED_BEFORE_DELIVERY"
        evidence = dict(revalidation_evidence or {})
        if not (
            evidence.get("commercialAuthorityAllowed") is False
            and evidence.get("directCommercialSignal") is False
            and evidence.get("sexualSalesOpportunityEligible") is False
            and evidence.get("activePresentationBridge") is False
        ):
            return "CURRENT_AUTHORITY_NOT_DENIED", None
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM ordinary_chat_reply_operations
                   WHERE operation_id=%s AND inbound_telegram_message_id=%s
                   FOR UPDATE""",
                (operation_id, inbound_message_id),
            )
            current = cursor.fetchone()
            if current is None:
                return "AUTHORITY_MISMATCH", None
            if current["state"] == "SUPPRESSED" and current.get("last_error") == reason:
                return "ALREADY_INVALIDATED", self._item(current)
            delivery = dict(current.get("delivery_payload") or {})
            response = dict(current.get("response_payload") or {})
            private_ppv = dict(dict(delivery.get("metadata") or {}).get(
                "private_ppv_presentation"
            ) or {})
            persisted_intent_id = str(
                private_ppv.get("purchase_intent_id")
                or dict(dict(response.get("delivery_payload") or {}).get(
                    "metadata"
                ) or {}).get("private_ppv_presentation", {}).get(
                    "purchase_intent_id"
                )
                or ""
            )
            commercial_delivery = bool(
                persisted_intent_id
                and (
                    delivery.get("delivery_method") == "private_ppv_media"
                    or private_ppv
                )
            )
            if not commercial_delivery or persisted_intent_id != str(purchase_intent_id):
                return "COMMERCIAL_PAYLOAD_MISMATCH", None
            cursor.execute(
                """SELECT status,presented_at,purchased_at,telegram_message_id,
                          provider_transaction_order_id,provider_payment_id,
                          provider_event_id,purchase_acknowledged_at,
                          actual_charged_price_minor
                   FROM purchase_intents WHERE purchase_intent_id=%s""",
                (purchase_intent_id,),
            )
            intent = cursor.fetchone()
            if intent is None:
                return "PURCHASE_INTENT_MISSING", None
            protected = bool(
                intent["status"] != "ABANDONED"
                or intent.get("presented_at") is not None
                or intent.get("purchased_at") is not None
                or intent.get("telegram_message_id") is not None
                or intent.get("provider_transaction_order_id") is not None
                or intent.get("provider_payment_id") is not None
                or intent.get("provider_event_id") is not None
                or intent.get("purchase_acknowledged_at") is not None
                or intent.get("actual_charged_price_minor") is not None
            )
            if protected:
                return "PURCHASE_OR_OWNERSHIP_EVIDENCE_PRESENT", None
            cursor.execute(
                """SELECT EXISTS(
                       SELECT 1 FROM telegram_private_inbound_messages newer
                       WHERE newer.telegram_account_scope=%s
                         AND newer.telegram_chat_id=%s
                         AND newer.telegram_message_id>%s
                     ) OR EXISTS(
                       SELECT 1 FROM ordinary_chat_reply_operations newer
                       WHERE newer.telegram_account_scope=%s
                         AND newer.telegram_chat_id=%s
                         AND newer.inbound_telegram_message_id>%s
                         AND newer.state NOT IN ('SUPPRESSED','TERMINAL_FAILED')
                     ) OR EXISTS(
                       SELECT 1 FROM ordinary_chat_reply_operations answered
                       WHERE answered.telegram_account_scope=%s
                         AND answered.telegram_chat_id=%s
                         AND answered.state='SENT_CONFIRMED'
                         AND answered.sent_confirmed_at>%s
                     ) AS stale""",
                (
                    current["telegram_account_scope"], current["telegram_chat_id"],
                    inbound_message_id, current["telegram_account_scope"],
                    current["telegram_chat_id"], inbound_message_id,
                    current["telegram_account_scope"], current["telegram_chat_id"],
                    current["inbound_received_at"],
                ),
            )
            if cursor.fetchone()["stale"]:
                return "FRESHNESS_CHANGED", None
            cursor.execute(
                """UPDATE ordinary_chat_reply_operations SET
                       state='SUPPRESSED',last_error=%s,next_retry_at=NULL,
                       claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                       delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
                         || jsonb_build_object(
                           'commercialAuthorityInvalidation',
                           jsonb_build_object(
                             'reason',%s::text,'invalidatedAt',NOW(),
                             'previousState',state,
                             'previousError',last_error,
                             'purchaseIntentId',%s::text,
                             'revalidation',%s::jsonb)),
                       updated_at=NOW()
                   WHERE operation_id=%s
                     AND inbound_telegram_message_id=%s
                     AND state IN ('GENERATED','RETRYABLE')
                     AND response_payload IS NOT NULL
                     AND COALESCE(response_text,'')<>''
                     AND outbound_telegram_message_id IS NULL
                     AND uncertain_at IS NULL
                     AND sent_confirmed_at IS NULL
                     AND claim_owner IS NULL AND claimed_at IS NULL
                     AND lease_expires_at IS NULL
                   RETURNING *""",
                (
                    reason, reason, str(purchase_intent_id),
                    json.dumps(evidence), operation_id, inbound_message_id,
                ),
            )
            invalidated = cursor.fetchone()
            if invalidated is None:
                return "OPERATION_NOT_INVALIDATABLE", None
            return "INVALIDATED", self._item(invalidated)

    def cancel_operator_reply(self, *, operation_id, account_scope, chat_id,
                              sender_user_id, inbound_message_id,
                              cancelled_by="CREATOR_OS_OPERATOR"):
        """Atomically suppress one exact, definitively-unsent reply obligation."""
        reason = "OPERATOR_CANCELLED_PREPARED_REPLY"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE operation_id=%s AND telegram_account_scope=%s
                  AND telegram_chat_id=%s AND inbound_sender_telegram_user_id=%s
                  AND inbound_telegram_message_id=%s FOR UPDATE""", (
                    operation_id, account_scope, chat_id, sender_user_id,
                    inbound_message_id))
            current = cursor.fetchone()
            if current is None:
                return "AUTHORITY_MISMATCH", None
            if current["state"] == "SUPPRESSED" and current.get("last_error") == reason:
                return "ALREADY_CANCELLED", self._item(current)
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SUPPRESSED',last_error=%s,next_retry_at=NULL,
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
                  || jsonb_build_object('operatorCancellation',jsonb_build_object(
                       'reason',%s::text,'cancelledBy',%s::text,'cancelledAt',NOW(),
                       'previousState',state)),
                updated_at=NOW()
                WHERE operation_id=%s
                  AND state IN ('PENDING_GENERATION','GENERATED','RETRYABLE')
                  AND outbound_telegram_message_id IS NULL
                  AND uncertain_at IS NULL AND sending_at IS NULL
                  AND send_attempt_count=0
                  AND claim_owner IS NULL AND claimed_at IS NULL
                  AND lease_expires_at IS NULL
                RETURNING *""", (reason, reason, cancelled_by, operation_id))
            cancelled = cursor.fetchone()
            if cancelled is not None:
                return "CANCELLED", self._item(cancelled)
            return "DELIVERY_OR_LIFECYCLE_WON", self._item(current)

    def reserve_english_only_notice(
        self, operation_id, *, policy, after_notice_reason,
        notice_pending_reason, classification, creator_profile_id,
        fanvue_account_id,
    ):
        """Single-winner notice reservation using existing durable operation state."""
        marker = {"englishOnlyConversationPolicy": {
            "policy": policy, "noticeReserved": True,
            "classification": dict(classification),
        }}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s FOR UPDATE", (operation_id,))
            current = cursor.fetchone()
            if current is None:
                return "TERMINAL", None, None
            lock_key = (
                f"english-only-notice:{current['telegram_account_scope']}:"
                f"{current['telegram_chat_id']}:{current['inbound_sender_telegram_user_id']}"
            )
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (lock_key,))
            current_marker = dict(dict(current.get("delivery_payload") or {}).get(
                "englishOnlyConversationPolicy") or {})
            if current_marker.get("noticeReserved") is True:
                return "FIRST_NOTICE", self._item(current), "CURRENT_OPERATION_RESERVATION"
            cursor.execute("""SELECT 1 FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s AND state='SENT_CONFIRMED'
                  AND outbound_telegram_message_id IS NOT NULL
                  AND COALESCE(delivery_payload#>>'{englishOnlyConversationPolicy,noticeReserved}','false')='true'
                LIMIT 1""", (current["telegram_account_scope"], current["telegram_chat_id"],
                              current["inbound_sender_telegram_user_id"]))
            confirmed_authority = "CONFIRMED_ORDINARY_NOTICE" if cursor.fetchone() else None
            if confirmed_authority is None:
                cursor.execute("""SELECT 1 FROM telegram_operator_message_operations
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s AND telegram_chat_id=%s
                      AND state='CONFIRMED' AND outbound_telegram_message_id IS NOT NULL
                      AND regexp_replace(lower(message_text),'[^a-z]+','','g')
                          IN ('hisorryionlyspeakenglish','sorryionlyspeakenglish')
                    LIMIT 1""", (creator_profile_id, fanvue_account_id,
                                  current["inbound_sender_telegram_user_id"], current["telegram_chat_id"]))
                if cursor.fetchone():
                    confirmed_authority = "CONFIRMED_OPERATOR_NOTICE"
            if confirmed_authority:
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET state='SUPPRESSED',
                    last_error=%s,next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
                    lease_expires_at=NULL,delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                    updated_at=NOW() WHERE operation_id=%s AND state IN ('PENDING_GENERATION','RETRYABLE')
                    AND response_payload IS NULL AND send_attempt_count=0 RETURNING *""",
                    (after_notice_reason, json.dumps({"englishOnlyConversationPolicy": {
                        "policy": policy, "classification": dict(classification),
                        "noticeAuthority": confirmed_authority,
                    }}), operation_id))
                row = cursor.fetchone()
                return "SUPPRESSED_AFTER_NOTICE", self._item(row) if row else None, confirmed_authority
            cursor.execute("""SELECT operation_id FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s AND operation_id<>%s
                  AND state IN ('PENDING_GENERATION','GENERATING','GENERATED','RETRYABLE','SENDING')
                  AND COALESCE(delivery_payload#>>'{englishOnlyConversationPolicy,noticeReserved}','false')='true'
                LIMIT 1""", (current["telegram_account_scope"], current["telegram_chat_id"],
                              current["inbound_sender_telegram_user_id"], operation_id))
            if cursor.fetchone():
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET state='SUPPRESSED',
                    last_error=%s,next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
                    lease_expires_at=NULL,delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                    updated_at=NOW() WHERE operation_id=%s AND state IN ('PENDING_GENERATION','RETRYABLE')
                    AND response_payload IS NULL AND send_attempt_count=0 RETURNING *""",
                    (notice_pending_reason, json.dumps({"englishOnlyConversationPolicy": {
                        "policy": policy, "classification": dict(classification),
                        "noticeAuthority": "PENDING_NOTICE_OPERATION",
                    }}), operation_id))
                row = cursor.fetchone()
                return "SUPPRESSED_NOTICE_PENDING", self._item(row) if row else None, "PENDING_NOTICE_OPERATION"
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,updated_at=NOW()
                WHERE operation_id=%s AND state IN ('PENDING_GENERATION','RETRYABLE')
                  AND response_payload IS NULL AND send_attempt_count=0 RETURNING *""",
                (json.dumps(marker), operation_id))
            row = cursor.fetchone()
            return "FIRST_NOTICE", self._item(row) if row else None, "NEW_NOTICE_RESERVATION"

    def store_english_only_notice(self, operation_id, *, response_payload,
                                  response_text, content_sha256, delivery_payload):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN scheduled_delivery_at IS NOT NULL
                            AND scheduled_delivery_at>NOW()
                       THEN 'RETRYABLE' ELSE 'GENERATED' END,
            response_payload=%s::jsonb,response_text=%s,response_content_sha256=%s,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            generated_at=NOW(),
            next_retry_at=CASE WHEN scheduled_delivery_at IS NOT NULL
                                    AND scheduled_delivery_at>NOW()
                               THEN scheduled_delivery_at ELSE NULL END,
            last_error=CASE WHEN scheduled_delivery_at IS NOT NULL
                                 AND scheduled_delivery_at>NOW()
                            THEN 'prepared_for_scheduled_delivery' ELSE NULL END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state IN ('PENDING_GENERATION','RETRYABLE')
              AND response_payload IS NULL AND send_attempt_count=0
              AND COALESCE(delivery_payload#>>'{englishOnlyConversationPolicy,noticeReserved}','false')='true'
            RETURNING *""", (json.dumps(response_payload), response_text, content_sha256,
                              json.dumps(delivery_payload), operation_id))

    def suppress_for_market_limit(self, operation_id, *, reason, evidence):
        return self._one("""UPDATE ordinary_chat_reply_operations SET state='SUPPRESSED',
            last_error=%s,delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,next_retry_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='PENDING_GENERATION' AND response_payload IS NULL
              AND generation_attempt_count=0 AND send_attempt_count=0 RETURNING *""",
            (reason,json.dumps({'marketResourcePolicy':evidence}),operation_id))

    def suppress_historical_retryable(self, operation_id, *, reason, disposition_at):
        """Terminally disposition stale, unsent retry debt with preserved evidence."""
        audit = {
            "historicalRetryableDisposition": {
                "previousState": "RETRYABLE",
                "dispositionReason": str(reason),
                "dispositionAt": disposition_at.isoformat(),
                "noDeliveryConfirmed": True,
            }
        }
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='SUPPRESSED',
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
              || %s::jsonb
              || jsonb_build_object('historicalRetryableFailure',jsonb_build_object(
                   'originalOperationId',operation_id::text,
                   'originalLastError',last_error,
                   'originalGenerationAttempts',generation_attempt_count,
                   'originalSendAttempts',send_attempt_count)),
            last_error=%s,next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
            lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='RETRYABLE'
              AND response_payload IS NULL AND send_attempt_count=0
            RETURNING *""", (json.dumps(audit), str(reason)[:1000], operation_id))

    def claim_send(self, operation_id, *, owner, lease_seconds=300):
        return self._one("""UPDATE ordinary_chat_reply_operations SET state='SENDING',
            claim_owner=%s,claimed_at=NOW(),sending_at=NOW(),
            lease_expires_at=NOW()+(%s*INTERVAL '1 second'),
            send_attempt_count=send_attempt_count+1,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
              || jsonb_build_object('archivePreSendFreshness',jsonb_build_object(
                   'authoritativeForegroundInboundId',COALESCE(
                       burst_freshness_telegram_message_id,
                       inbound_telegram_message_id),
                   'newestRelevantArchivedInboundId',COALESCE(
                       burst_freshness_telegram_message_id,
                       inbound_telegram_message_id),
                   'archiveFreshnessSatisfied',true,
                   'mediaFreshnessDisposition',CASE WHEN EXISTS (
                     SELECT 1 FROM telegram_private_inbound_messages ignored_media
                     WHERE ignored_media.telegram_account_scope=
                             ordinary_chat_reply_operations.telegram_account_scope
                       AND ignored_media.telegram_chat_id=
                             ordinary_chat_reply_operations.telegram_chat_id
                       AND ignored_media.telegram_message_id>
                             COALESCE(
                               ordinary_chat_reply_operations.burst_freshness_telegram_message_id,
                               ordinary_chat_reply_operations.inbound_telegram_message_id)
                       AND ignored_media.has_media IS TRUE
                       AND ignored_media.reconciliation_state='NO_RESPONSE_REQUIRED'
                   ) THEN 'IRRELEVANT_TO_CURRENT_REPLY' ELSE 'NONE' END)),
            updated_at=NOW()
            WHERE operation_id=%s AND (
              state='GENERATED' OR (state='RETRYABLE' AND response_payload IS NOT NULL
                                    AND COALESCE(next_retry_at,NOW())<=NOW()))
              AND NOT EXISTS (
                SELECT 1 FROM active_offer_follow_through_events follow
                JOIN purchase_intents intent
                  ON intent.purchase_intent_id=follow.purchase_intent_id
                WHERE follow.operation_id=ordinary_chat_reply_operations.operation_id
                  AND (intent.status NOT IN ('PRESENTED','CLICKED')
                    OR intent.purchased_at IS NOT NULL
                    OR intent.provider_transaction_order_id IS NOT NULL
                    OR intent.provider_payment_id IS NOT NULL
                    OR intent.provider_event_id IS NOT NULL)
              )
              AND NOT EXISTS (
                SELECT 1 FROM telegram_private_inbound_messages archived
                WHERE archived.telegram_account_scope=
                        ordinary_chat_reply_operations.telegram_account_scope
                  AND archived.telegram_chat_id=
                        ordinary_chat_reply_operations.telegram_chat_id
                  AND archived.telegram_message_id>
                        COALESCE(
                          ordinary_chat_reply_operations.burst_freshness_telegram_message_id,
                          ordinary_chat_reply_operations.inbound_telegram_message_id)
                  AND (
                    BTRIM(COALESCE(archived.customer_text,''))<>''
                    OR (archived.has_media IS TRUE
                        AND archived.reconciliation_state<>'NO_RESPONSE_REQUIRED')
                  )
              )
              AND NOT EXISTS (
                SELECT 1 FROM ordinary_chat_reply_operations confirmed
                WHERE confirmed.operation_id<>
                        ordinary_chat_reply_operations.operation_id
                  AND confirmed.telegram_account_scope=
                        ordinary_chat_reply_operations.telegram_account_scope
                  AND confirmed.telegram_chat_id=
                        ordinary_chat_reply_operations.telegram_chat_id
                  AND confirmed.inbound_telegram_message_id=
                        ordinary_chat_reply_operations.inbound_telegram_message_id
                  AND confirmed.state='SENT_CONFIRMED'
                  AND confirmed.outbound_telegram_message_id IS NOT NULL
              )
              AND send_attempt_count<max_send_attempts RETURNING *""",
            (owner,max(1,int(lease_seconds)),operation_id))

    @staticmethod
    def _archive_row_relevant(row):
        return bool(
            str(row.get("customer_text") or "").strip()
            or (bool(row.get("has_media"))
                and str(row.get("reconciliation_state") or "")
                != "NO_RESPONSE_REQUIRED")
        )

    def archive_freshness(self, operation_id):
        """Read the same archive authority enforced atomically by ``claim_send``."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT COALESCE(current.burst_freshness_telegram_message_id,
                                               current.inbound_telegram_message_id) AS authority_id,
                    archived.telegram_message_id,archived.received_at,
                    archived.customer_text,archived.has_media,archived.media_types,
                    archived.reconciliation_state,archived.ingestion_provenance
                FROM ordinary_chat_reply_operations current
                LEFT JOIN telegram_private_inbound_messages archived
                  ON archived.telegram_account_scope=current.telegram_account_scope
                 AND archived.telegram_chat_id=current.telegram_chat_id
                 AND archived.telegram_message_id>=COALESCE(
                     current.burst_freshness_telegram_message_id,
                     current.inbound_telegram_message_id)
                WHERE current.operation_id=%s
                ORDER BY archived.received_at,archived.telegram_message_id""",
                (operation_id,))
            rows = [dict(row) for row in cursor.fetchall()]
        if not rows:
            return {"authoritativeForegroundInboundId": None,
                    "newestRelevantArchivedInboundId": None,
                    "archiveFreshnessSatisfied": False,
                    "mediaFreshnessDisposition": "ARCHIVE_AUTHORITY_MISSING"}
        authority = int(rows[0]["authority_id"])
        relevant = [row for row in rows
                    if row.get("telegram_message_id") is not None
                    and self._archive_row_relevant(row)]
        newest = max((int(row["telegram_message_id"]) for row in relevant),
                     default=authority)
        newer_media = [row for row in rows
                       if row.get("telegram_message_id") is not None
                       and int(row["telegram_message_id"]) > authority
                       and row.get("has_media")]
        disposition = "NONE"
        if newer_media:
            relevant_media = [row for row in newer_media
                              if self._archive_row_relevant(row)]
            if not relevant_media:
                disposition = "IRRELEVANT_TO_CURRENT_REPLY"
            elif any(
                int(text_row["telegram_message_id"]) > int(media_row["telegram_message_id"])
                and str(text_row.get("customer_text") or "").strip()
                for media_row in relevant_media for text_row in relevant
            ):
                disposition = "COALESCED_INTO_CURRENT_TURN"
            else:
                disposition = "CURRENT_SUPERSEDING"
        return {
            "authoritativeForegroundInboundId": authority,
            "newestRelevantArchivedInboundId": newest,
            "archiveFreshnessSatisfied": newest <= authority,
            "mediaFreshnessDisposition": disposition,
        }

    def suppress_settled_follow_through_before_send(self, operation_id):
        """Terminally block a generated nudge when settlement won the send race."""
        return self._one("""UPDATE ordinary_chat_reply_operations operation SET
            state='SUPPRESSED',next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
            lease_expires_at=NULL,last_error='active_offer_settled_before_send',
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||
              '{"preSendSettlementValidation":{"allowed":false,
                 "reason":"PURCHASE_SETTLED_BEFORE_SEND",
                 "transportAttempted":false}}'::jsonb,
            updated_at=NOW()
            FROM active_offer_follow_through_events follow
            JOIN purchase_intents intent
              ON intent.purchase_intent_id=follow.purchase_intent_id
            WHERE operation.operation_id=%s
              AND follow.operation_id=operation.operation_id
              AND operation.state IN ('GENERATED','RETRYABLE')
              AND (intent.status NOT IN ('PRESENTED','CLICKED')
                OR intent.purchased_at IS NOT NULL
                OR intent.provider_transaction_order_id IS NOT NULL
                OR intent.provider_payment_id IS NOT NULL
                OR intent.provider_event_id IS NOT NULL)
            RETURNING operation.*""", (operation_id,))

    def has_newer_unresolved_inbound(self, operation_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(SELECT 1
                FROM ordinary_chat_reply_operations current
                JOIN ordinary_chat_reply_operations newer
                  ON newer.telegram_account_scope=current.telegram_account_scope
                 AND newer.telegram_chat_id=current.telegram_chat_id
                 AND newer.inbound_telegram_message_id>COALESCE(
                     current.burst_freshness_telegram_message_id,
                     current.inbound_telegram_message_id)
                 AND (current.conversation_burst_id IS NULL OR
                      newer.conversation_burst_id IS DISTINCT FROM
                          current.conversation_burst_id)
                WHERE current.operation_id=%s
                  AND newer.state NOT IN ('TERMINAL_FAILED','SUPPRESSED')) AS present""",
                (operation_id,))
            row = cursor.fetchone()
        return bool(row and row["present"])

    def requeue_empty_generation(self, operation_id, *, reason):
        """Recover a definitively unsent empty result after a generation defect."""
        current = self.get(operation_id)
        durable_audit = self.merge_current_delivery_with_durable_audit(
            getattr(current, "delivery_payload", None), {},
        )
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',response_payload=NULL,response_text=NULL,
            response_content_sha256=NULL,delivery_payload=%s::jsonb,generated_at=NULL,
            next_retry_at=NOW(),last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATED'
              AND COALESCE(response_text,'')='' AND send_attempt_count=0
              AND outbound_telegram_message_id IS NULL RETURNING *""",
            (json.dumps(durable_audit), reason[:1000], operation_id))

    def requeue_suppressed_engine_exception(self, operation_id, *, reason):
        """Release a definitively unsent empty engine-exception suppression."""
        current = self.get(operation_id)
        durable_audit = self.merge_current_delivery_with_durable_audit(
            getattr(current, "delivery_payload", None), {},
        )
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',response_payload=NULL,response_text=NULL,
            response_content_sha256=NULL,delivery_payload=%s::jsonb,generated_at=NULL,
            next_retry_at=NOW(),last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='SUPPRESSED'
              AND last_error='intentional_suppression:decision_engine_exception'
              AND COALESCE(response_text,'')='' AND send_attempt_count=0
              AND outbound_telegram_message_id IS NULL
              AND generation_attempt_count<max_generation_attempts RETURNING *""",
            (json.dumps(durable_audit), reason[:1000], operation_id))

    def recover_denied_optional_active_offer(
        self, *, operation_id, creator_profile_id, fanvue_account_id,
        global_reply_authorized, safety_authorized,
    ):
        """Release one untouched current optional-nudge suppression to availability."""
        if not global_reply_authorized or not safety_authorized:
            return None
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"optional-active-offer-recovery:{operation_id}",),
            )
            cursor.execute("""SELECT target.* FROM ordinary_chat_reply_operations target
                WHERE target.operation_id=%s FOR UPDATE""", (operation_id,))
            original = cursor.fetchone()
            if original is None:
                return None
            original_payload = dict(original.get("delivery_payload") or {})
            audit = {"optionalActiveOfferSuppressionRecovery": {
                "authority": "OrdinaryChatReplyRepository",
                "originalState": str(original.get("state") or ""),
                "originalReason": str(original.get("last_error") or ""),
                "originalSuppressedAt": (
                    original["updated_at"].isoformat()
                    if original.get("updated_at") else None
                ),
                "originalGenerationAttemptCount": int(original.get("generation_attempt_count") or 0),
                "originalSendAttemptCount": int(original.get("send_attempt_count") or 0),
                "originalCommercialDiagnostics": (
                    original_payload.get("preGenerationCommercialDecision")
                    or original_payload.get("marketResourcePolicy")
                ),
                "recoveryDestination": "ORDINARY_AVAILABILITY",
                "commercialAuthorityGranted": False,
                "directGeneration": False,
                "directSend": False,
            }}
            cursor.execute("""UPDATE ordinary_chat_reply_operations target SET
                state='RETRYABLE',next_retry_at=NOW(),scheduled_delivery_at=NULL,
                preparation_eligible_at=NULL,last_error='availability_deferred',
                delivery_payload=COALESCE(target.delivery_payload,'{}'::jsonb)||%s::jsonb,
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
              WHERE target.operation_id=%s
                AND target.telegram_account_scope='AVA_TELETHON_PRIVATE'
                AND target.state='SUPPRESSED'
                AND target.last_error='ACTIVE_OFFER_NUDGE_RESERVATION_DENIED'
                AND target.generation_attempt_count=0 AND target.send_attempt_count=0
                AND target.response_payload IS NULL AND target.response_text IS NULL
                AND target.outbound_telegram_message_id IS NULL
                AND target.sent_confirmed_at IS NULL AND target.sending_at IS NULL
                AND (target.claim_owner IS NULL OR target.lease_expires_at<=NOW())
                AND EXISTS (SELECT 1 FROM telegram_private_inbound_messages archived
                  WHERE archived.telegram_account_scope=target.telegram_account_scope
                    AND archived.telegram_chat_id=target.telegram_chat_id
                    AND archived.telegram_user_id=target.inbound_sender_telegram_user_id
                    AND archived.telegram_message_id=target.inbound_telegram_message_id
                    AND archived.creator_profile_id=%s AND archived.fanvue_account_id=%s)
                AND NOT EXISTS (SELECT 1 FROM telegram_private_inbound_messages newer
                  WHERE newer.telegram_account_scope=target.telegram_account_scope
                    AND newer.telegram_chat_id=target.telegram_chat_id
                    AND newer.telegram_message_id>target.inbound_telegram_message_id)
                AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                  WHERE newer.telegram_account_scope=target.telegram_account_scope
                    AND newer.telegram_chat_id=target.telegram_chat_id
                    AND newer.inbound_telegram_message_id>target.inbound_telegram_message_id)
                AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations competing
                  WHERE competing.operation_id<>target.operation_id
                    AND competing.telegram_account_scope=target.telegram_account_scope
                    AND competing.telegram_chat_id=target.telegram_chat_id
                    AND competing.state IN ('PENDING_GENERATION','GENERATING','GENERATED','RETRYABLE','SENDING'))
                AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations answered
                  WHERE answered.telegram_account_scope=target.telegram_account_scope
                    AND answered.telegram_chat_id=target.telegram_chat_id
                    AND answered.state='SENT_CONFIRMED'
                    AND answered.sent_confirmed_at>target.inbound_received_at)
                AND NOT EXISTS (SELECT 1 FROM telegram_operator_message_operations manual
                  WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                    AND manual.telegram_user_id=target.inbound_sender_telegram_user_id
                    AND manual.telegram_chat_id=target.telegram_chat_id
                    AND manual.state='CONFIRMED' AND manual.confirmed_at>target.inbound_received_at)
                AND COALESCE((SELECT control.mode FROM telegram_relationship_controls control
                  WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                    AND control.telegram_user_id=target.inbound_sender_telegram_user_id
                    AND control.telegram_chat_id=target.telegram_chat_id LIMIT 1),'AVA_AUTO')='AVA_AUTO'
                AND COALESCE((SELECT control.communication_disposition
                  FROM telegram_relationship_controls control
                  WHERE control.creator_profile_id=%s AND control.fanvue_account_id=%s
                    AND control.telegram_user_id=target.inbound_sender_telegram_user_id
                    AND control.telegram_chat_id=target.telegram_chat_id LIMIT 1),'ACTIVE')='ACTIVE'
              RETURNING target.*""", (
                json.dumps(audit), operation_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
            ))
            recovered = cursor.fetchone()
            connection.commit()
        return self._item(recovered) if recovered else None

    def requeue_historical_corrective(
        self, *, target_operation_id, causal_operation_id,
        creator_profile_id, fanvue_account_id, telegram_user_id,
        occurrence_id, resolution_plan_id, approved_by, idempotency_key,
        recovery_execution_constraint=None,
    ):
        """Create one immutable-history corrective obligation idempotently.

        The due-availability poll remains the only release authority. This method
        neither invokes generation nor sends to Telegram.
        """
        from app.services.autobiographical_question_authority import (
            AutobiographicalQuestionAuthority,
        )
        causal = self.get(causal_operation_id)
        parent = self.get(target_operation_id)
        if causal is None or parent is None:
            return None
        recovery_key = f"historical-corrective:{causal_operation_id}:{idempotency_key}"
        from app.services.historical_corrective_eligibility_service import (
            HistoricalCorrectiveEligibilityService,
        )
        eligibility = HistoricalCorrectiveEligibilityService(
            connection_factory=self.connection_factory,
        ).evaluate(
            root=causal, parent=parent,
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=causal.telegram_chat_id,
            chat_allowed=True,
        )
        if not eligibility["eligible"]:
            # A concurrent execution with the same idempotency authority may
            # have created the only permitted child between the initial reads.
            # Return that exact child; a different key remains fail-closed.
            return self._one("""SELECT * FROM ordinary_chat_reply_operations
                WHERE recovery_idempotency_key=%s""", (recovery_key,))
        inbound_text = str(getattr(causal, "inbound_message_text", "") or "")
        referent = AutobiographicalQuestionAuthority.referent(inbound_text)
        prior_reasons = [name for name in (
            "CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED",
        ) if name in str(getattr(causal, "last_error", "") or "")]
        audit={"approvedHistoricalCorrection":{
            "attentionOccurrenceId":str(occurrence_id),
            "causalOperationId":str(causal_operation_id),
            "parentOperationId":str(target_operation_id),
            "resolutionPlanId":str(resolution_plan_id),
            "approvedBy":str(approved_by),"idempotencyKey":str(idempotency_key),
            "historicalCandidateReused":False,
            "historicalMediaReused":False,
            "historicalPurchaseIntentAuthoritative":False,
            "rootEligibilityCategory":eligibility["category"],
            "deliveryResolutionId":eligibility.get("resolutionId"),
            "currentPolicyReevaluationRequired":True,
        }}
        constraint=dict(recovery_execution_constraint or {})
        constrained_categories = {
            HistoricalCorrectiveEligibilityService.NOT_DELIVERED,
            HistoricalCorrectiveEligibilityService.CONSTRAINT_FAILURE_FOLLOW_UP,
        }
        if eligibility["category"] in constrained_categories:
            from app.services.recovery_execution_constraint_service import (
                RecoveryExecutionConstraintService,
            )
            if constraint != RecoveryExecutionConstraintService.authority():
                return None
            audit["recoveryExecutionConstraint"]=constraint
        elif constraint:
            from app.services.recovery_execution_constraint_service import (
                RecoveryExecutionConstraintService,
            )
            if constraint != RecoveryExecutionConstraintService.authority():
                return None
            audit["recoveryExecutionConstraint"]=constraint
        if eligibility["category"] == HistoricalCorrectiveEligibilityService.QUALITY:
            from app.services.corrective_generation_evidence_service import (
                CorrectiveGenerationEvidenceService,
            )
            error = str(getattr(causal, "last_error", "") or "")
            failure_text = error.split(":", 1)[1] if ":" in error else ""
            historical_reasons = [
                item.strip() for item in failure_text.split(",") if item.strip()
            ] or prior_reasons
            original_payload = dict(getattr(causal, "response_payload", None) or {})
            if not original_payload.get("response_text"):
                original_payload["response_text"] = str(
                    getattr(causal, "response_text", "") or ""
                )
            repetition = "FINAL_REPETITION_FAILURE" in historical_reasons
            correction = CorrectiveGenerationEvidenceService.build(
                response_payload=original_payload,
                reasons=historical_reasons,
                recent_ava_responses=self.recent_ava_responses(causal),
                attempt=2,
                source="OPERATOR_APPROVED_HISTORICAL_CORRECTION",
                original_operation_id=causal.operation_id,
                original_inbound_message_id=causal.inbound_telegram_message_id,
                require_rejected_candidate=repetition,
            )
            if not correction["turnObligations"]:
                correction["turnObligations"] = ["ANSWER_DIRECT_QUESTION"]
            if correction.get("semanticReferent") is None:
                correction["semanticReferent"] = referent
            correction["unknownBiographyInstructionRequired"] = referent is not None
            correction["originalGenerationAttemptCount"] = int(
                getattr(causal, "generation_attempt_count", 0) or 0
            )
            correction["historicalRecoveryGenerationLimit"] = 1
            audit["qualityCorrectiveRetry"] = correction
        elif eligibility["category"] == HistoricalCorrectiveEligibilityService.RETRY_EXHAUSTED:
            audit["retryExhaustedCurrentPolicyReevaluation"] = {
                "required": True,
                "freshGenerationRequired": True,
                "historicalPayloadReuseAllowed": False,
                "historicalCommercialAuthorityAllowed": False,
                "commercialEvaluationRequiredBeforeConversation": True,
                "singleCustomerVisibleOutcome": True,
            }
        else:
            audit["canonicalNotDeliveredCorrection"] = {
                "required": True,
                "freshGenerationRequired": True,
                "historicalPayloadReuseAllowed": False,
                "historicalCommercialAuthorityAllowed": False,
            }
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (recovery_key,),
            )
            cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                WHERE recovery_idempotency_key=%s""", (recovery_key,))
            existing = cursor.fetchone()
            if existing is not None:
                return self._item(existing)
            cursor.execute("""INSERT INTO ordinary_chat_reply_operations(
                  operation_id,telegram_account_scope,telegram_chat_id,
                  inbound_telegram_message_id,inbound_sender_telegram_user_id,
                  inbound_message_text,inbound_received_at,conversation_thread_id,
                  correlation_id,delivery_payload,state,generation_attempt_count,
                  send_attempt_count,max_generation_attempts,max_send_attempts,
                  next_retry_at,last_error,operation_kind,causal_operation_id,
                  recovery_parent_operation_id,
                  recovery_attention_occurrence_id,recovery_resolution_plan_id,
                  recovery_idempotency_key)
                SELECT %s,root.telegram_account_scope,root.telegram_chat_id,
                  root.inbound_telegram_message_id,
                  root.inbound_sender_telegram_user_id,
                  root.inbound_message_text,root.inbound_received_at,
                  root.conversation_thread_id,%s,%s::jsonb,'RETRYABLE',0,0,1,
                  root.max_send_attempts,NOW()+INTERVAL '8 seconds',
                  'availability_deferred','HISTORICAL_CORRECTIVE',root.operation_id,
                  parent.operation_id,%s,%s,%s
                FROM ordinary_chat_reply_operations root
                JOIN ordinary_chat_reply_operations parent
                  ON parent.operation_id=%s
                WHERE root.operation_id=%s
                  AND root.telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND root.inbound_sender_telegram_user_id=%s
                  AND root.outbound_telegram_message_id IS NULL
                  AND root.operation_kind='PRIMARY'
                  AND (
                    (root.state='SUPPRESSED' AND root.send_attempt_count=0 AND
                      (root.last_error LIKE 'quality_blocked_before_delivery:%%'
                       OR root.last_error LIKE 'quality_corrective_retry_exhausted:%%'))
                    OR
                    (root.state='SEND_UNCERTAIN' AND root.sent_confirmed_at IS NULL
                     AND EXISTS(SELECT 1 FROM operator_delivery_resolutions resolution
                       WHERE resolution.ordinary_operation_id=root.operation_id
                         AND resolution.outcome='NOT_DELIVERED'
                         AND resolution.provenance='OPERATOR_ATTESTED'
                         AND resolution.provider_acceptance_evidence=FALSE
                         AND resolution.provider_readback_evidence=TRUE
                         AND resolution.evidence->>'classification'='CONFIRMED_NOT_DELIVERED'
                         AND COALESCE((resolution.evidence->>'complete')::boolean,FALSE)=TRUE
                         AND COALESCE((resolution.evidence->>'matchingCandidateCount')::integer,-1)=0))
                    OR
                    (root.state='TERMINAL_FAILED'
                     AND root.last_error LIKE 'DECISION_ENGINE_EXCEPTION:%%'
                     AND root.generation_attempt_count>=root.max_generation_attempts
                     AND root.max_generation_attempts>0
                     AND root.send_attempt_count=0
                     AND root.sent_confirmed_at IS NULL
                     AND BTRIM(COALESCE(root.response_text,''))=''
                     AND COALESCE(root.response_payload->>'response_text','')=''
                     AND NOT EXISTS(
                       SELECT 1 FROM ordinary_reply_generation_attempts attempt
                        WHERE attempt.operation_id=root.operation_id
                          AND BTRIM(COALESCE(attempt.candidate_text,''))<>''))
                  )
                  AND parent.telegram_account_scope=root.telegram_account_scope
                  AND parent.telegram_chat_id=root.telegram_chat_id
                  AND parent.inbound_telegram_message_id=root.inbound_telegram_message_id
                  AND parent.inbound_sender_telegram_user_id=root.inbound_sender_telegram_user_id
                  AND parent.inbound_message_text IS NOT DISTINCT FROM root.inbound_message_text
                  AND (
                    parent.operation_id=root.operation_id
                    OR (
                      parent.operation_kind='HISTORICAL_CORRECTIVE'
                      AND parent.causal_operation_id=root.operation_id
                      AND parent.state IN ('SUPPRESSED','TERMINAL_FAILED')
                      AND parent.outbound_telegram_message_id IS NULL
                      AND parent.sent_confirmed_at IS NULL
                      AND (
                        parent.last_error='RECOVERY_ABORTED_TELEGRAM_PEER_ID_INVALID'
                        OR (
                          parent.delivery_payload #>>
                            '{telegramDefinitiveRejection,classification}'=
                              'DEFINITIVE_NOT_DELIVERED'
                          AND COALESCE((parent.delivery_payload #>>
                            '{telegramDefinitiveRejection,automaticRetryAllowed}')::boolean,
                            FALSE)=FALSE
                        )
                        OR (
                          parent.recovery_parent_operation_id=root.operation_id
                          AND parent.send_attempt_count=0
                          AND parent.last_error=
                            'recovery_execution_constraint_violation:OPERATOR_RECOVERY_CONVERSATION_ONLY'
                          AND parent.recovery_resolution_plan_id IS NOT NULL
                          AND EXISTS(
                            SELECT 1 FROM conversation_resolution_plans parent_plan
                            WHERE parent_plan.plan_id=
                                parent.recovery_resolution_plan_id
                              AND parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,constraint}'=
                                  'CONVERSATION_ONLY_TEXT'
                              AND parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,authority}'=
                                  'OPERATOR_APPROVED_RECOVERY_PLAN'
                              AND parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,commercialActionAuthorization}'=
                                  'DENIED_BY_OPERATOR_RECOVERY_CONSTRAINT'
                              AND COALESCE((parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,commercialProgressionAllowed}')::boolean,
                                TRUE)=FALSE
                              AND COALESCE((parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,purchaseIntentAllowed}')::boolean,
                                TRUE)=FALSE
                              AND COALESCE((parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,mediaAllowed}')::boolean,
                                TRUE)=FALSE
                              AND COALESCE((parent_plan.parameters #>>
                                '{recoveryExecutionConstraint,textOnly}')::boolean,
                                FALSE)=TRUE
                          )
                        )
                      )
                    )
                  )
                  AND EXISTS(SELECT 1 FROM telegram_sales_prospects p
                    WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s
                      AND p.telegram_user_id=%s
                      AND p.telegram_chat_id=root.telegram_chat_id)
                  AND NOT EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                    WHERE newer.telegram_account_scope=root.telegram_account_scope
                      AND newer.telegram_chat_id=root.telegram_chat_id
                      AND newer.telegram_message_id>root.inbound_telegram_message_id)
                  AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                    WHERE newer.telegram_account_scope=root.telegram_account_scope
                      AND newer.telegram_chat_id=root.telegram_chat_id
                      AND newer.inbound_telegram_message_id>
                          root.inbound_telegram_message_id)
                  AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations later_recovery
                    WHERE later_recovery.operation_kind='HISTORICAL_CORRECTIVE'
                      AND later_recovery.causal_operation_id=root.operation_id
                      AND later_recovery.created_at>parent.created_at)
                  AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations competing
                    WHERE competing.operation_id NOT IN (root.operation_id,parent.operation_id)
                      AND competing.telegram_account_scope=root.telegram_account_scope
                      AND competing.telegram_chat_id=root.telegram_chat_id
                      AND competing.inbound_telegram_message_id=
                          root.inbound_telegram_message_id
                      AND competing.state IN ('PENDING_GENERATION','GENERATING',
                          'GENERATED','RETRYABLE','SENDING','SEND_UNCERTAIN',
                          'SENT_CONFIRMED'))
                  AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                    WHERE answered.telegram_account_scope=root.telegram_account_scope
                      AND answered.telegram_chat_id=root.telegram_chat_id
                      AND answered.state='SENT_CONFIRMED'
                      AND answered.sent_confirmed_at>root.inbound_received_at)
                  AND NOT EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                    WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                      AND manual.telegram_user_id=root.inbound_sender_telegram_user_id
                      AND manual.telegram_chat_id=root.telegram_chat_id
                      AND manual.state='CONFIRMED'
                      AND manual.confirmed_at>root.inbound_received_at)
                  AND COALESCE((SELECT control.mode
                    FROM telegram_relationship_controls control
                    WHERE control.creator_profile_id=%s
                      AND control.fanvue_account_id=%s
                      AND control.telegram_user_id=root.inbound_sender_telegram_user_id
                      AND control.telegram_chat_id=root.telegram_chat_id LIMIT 1),
                      'AVA_AUTO')='AVA_AUTO'
                  AND COALESCE((SELECT control.communication_disposition
                    FROM telegram_relationship_controls control
                    WHERE control.creator_profile_id=%s
                      AND control.fanvue_account_id=%s
                      AND control.telegram_user_id=root.inbound_sender_telegram_user_id
                      AND control.telegram_chat_id=root.telegram_chat_id LIMIT 1),
                      'ACTIVE')='ACTIVE'
                ON CONFLICT (recovery_idempotency_key)
                  WHERE recovery_idempotency_key IS NOT NULL DO NOTHING
                RETURNING *""", (
                uuid4(), recovery_key, json.dumps(audit), str(occurrence_id),
                resolution_plan_id, recovery_key, target_operation_id,
                causal_operation_id, telegram_user_id, creator_profile_id,
                fanvue_account_id, telegram_user_id, creator_profile_id,
                fanvue_account_id, creator_profile_id, fanvue_account_id,
                creator_profile_id, fanvue_account_id,
            ))
            created = cursor.fetchone()
            return self._item(created) if created else None

    def requeue_interrupted_generation(
        self, *, operation_id, creator_profile_id, fanvue_account_id,
        telegram_user_id, telegram_chat_id, approved_by, idempotency_key,
    ):
        """Atomically reopen one latest, definitively-unsent interrupted generation."""
        marker={"interruptedGenerationRecovery":{
            "approvedBy":str(approved_by),"idempotencyKey":str(idempotency_key),
            "freshGenerationRequired":True,"previousCandidateReused":False}}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations target SET
              state='RETRYABLE',response_payload=NULL,response_text=NULL,
              response_content_sha256=NULL,delivery_payload=%s::jsonb,
              generation_attempt_count=0,max_generation_attempts=2,
              next_retry_at=NOW()+INTERVAL '8 seconds',last_error='availability_deferred',
              generated_at=NULL,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
              updated_at=NOW()
              WHERE target.operation_id=%s
                AND target.telegram_account_scope='AVA_TELETHON_PRIVATE'
                AND target.inbound_sender_telegram_user_id=%s
                AND target.telegram_chat_id=%s
                AND target.state='GENERATING' AND target.lease_expires_at<NOW()
                AND target.generation_attempt_count>=target.max_generation_attempts
                AND target.response_payload IS NULL
                AND target.send_attempt_count=0
                AND target.outbound_telegram_message_id IS NULL
                AND target.sent_confirmed_at IS NULL
                AND EXISTS(SELECT 1 FROM telegram_sales_prospects p
                  WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s
                    AND p.telegram_user_id=%s AND p.telegram_chat_id=%s)
                AND COALESCE((SELECT c.mode FROM telegram_relationship_controls c
                  WHERE c.creator_profile_id=%s AND c.fanvue_account_id=%s
                    AND c.telegram_user_id=%s AND c.telegram_chat_id=%s
                  LIMIT 1),'AVA_AUTO')='AVA_AUTO'
                AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                  WHERE newer.telegram_account_scope=target.telegram_account_scope
                    AND newer.telegram_chat_id=target.telegram_chat_id
                    AND newer.inbound_telegram_message_id>target.inbound_telegram_message_id)
                AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations answered
                  WHERE answered.telegram_account_scope=target.telegram_account_scope
                    AND answered.telegram_chat_id=target.telegram_chat_id
                    AND answered.state='SENT_CONFIRMED'
                    AND answered.sent_confirmed_at>target.inbound_received_at)
                AND NOT EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                  WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                    AND manual.telegram_user_id=%s AND manual.telegram_chat_id=%s
                    AND manual.state='CONFIRMED'
                    AND manual.confirmed_at>target.inbound_received_at)
              RETURNING target.*""", (json.dumps(marker),operation_id,
                telegram_user_id,telegram_chat_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id))
            row=cursor.fetchone()
            if row is None:
                cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                  WHERE operation_id=%s AND inbound_sender_telegram_user_id=%s
                    AND telegram_chat_id=%s
                    AND delivery_payload->'interruptedGenerationRecovery'->>'idempotencyKey'=%s
                    AND state IN ('RETRYABLE','PENDING_GENERATION','GENERATING','GENERATED','SENDING','SENT_CONFIRMED')""",
                    (operation_id,telegram_user_id,telegram_chat_id,str(idempotency_key)))
                row=cursor.fetchone()
            connection.commit()
        return self._item(row) if row else None

    def fail_generated_before_send(self, operation_id, *, reason):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN send_attempt_count>=max_send_attempts
                       THEN 'TERMINAL_FAILED' ELSE 'RETRYABLE' END,
            last_error=%s,failed_at=CASE WHEN send_attempt_count>=max_send_attempts
                                        THEN NOW() ELSE failed_at END,
            next_retry_at=CASE WHEN send_attempt_count>=max_send_attempts
                               THEN NULL ELSE NOW() END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATED'
              AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
            RETURNING *""", (reason[:1000], operation_id))

    def terminalize_deterministic_authorization_failure(
        self, operation_id, *, reason,
    ):
        """Fail closed an immutable pre-transport rejection without a send attempt.

        A prepared operation is represented as RETRYABLE so the scheduler can
        wake it at its send time.  Once its persisted delivery evidence proves
        that sending can never be authorized, retrying is unsafe and pointless.
        This transition deliberately accepts only GENERATED and prepared
        RETRYABLE rows which have generated evidence and have never entered the
        transport namespace.
        """
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='SUPPRESSED',last_error=%s,failed_at=COALESCE(failed_at,NOW()),
            next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
            lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s
              AND state IN ('GENERATED','RETRYABLE')
              AND generation_attempt_count>0
              AND response_text IS NOT NULL
              AND delivery_payload IS NOT NULL
              AND send_attempt_count=0
              AND outbound_telegram_message_id IS NULL
              AND claim_owner IS NULL
            RETURNING *""", (reason[:1000], operation_id))

    def confirm_sent(self, operation_id, *, owner, telegram_message_id,
                     creator_profile_id=None, fanvue_account_id=None,
                     resource_classification=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
            state='SENT_CONFIRMED',outbound_telegram_message_id=%s,sent_confirmed_at=NOW(),
            response_payload=CASE
              WHEN COALESCE(response_payload#>>'{diagnostic_metadata,commercial_tease_delivery_pending_confirmation}','false')='true'
              THEN jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(jsonb_set(
                COALESCE(response_payload,'{}'::jsonb),
                '{diagnostic_metadata,commercial_tease_delivered}','true'::jsonb,true),
                '{diagnostic_metadata,commercial_tease_exposure_recorded}','true'::jsonb,true),
                '{diagnostic_metadata,progression_finalized_after_delivery}','true'::jsonb,true),
                '{diagnostic_metadata,commercial_tease_delivery_pending_confirmation}','false'::jsonb,true),
                '{diagnostic_metadata,commercial_tease_delivered_at}',to_jsonb(NOW()::text),true),
                '{diagnostic_metadata,commercial_summary,sexualCommercialProgression,commercialTeaseDelivered}','true'::jsonb,true),
                '{diagnostic_metadata,commercial_summary,sexualCommercialProgression,commercialTeaseExposureRecorded}','true'::jsonb,true),
                '{diagnostic_metadata,commercial_summary,sexualCommercialProgression,progressionFinalizedAfterDelivery}','true'::jsonb,true)
              ELSE response_payload END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,next_retry_at=NULL,
            last_error=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s
              AND (delivery_payload#>'{provider_delivery_evidence,transport_route}' IS NULL
                OR delivery_payload#>>'{provider_delivery_evidence,telegram_message_id}'=%s::text)
            RETURNING *""",
            (telegram_message_id,operation_id,owner,str(telegram_message_id)))
            row = cursor.fetchone()
            if row is not None:
                cursor.execute("""UPDATE ordinary_reply_generation_attempts SET
                  sent_confirmed=TRUE,outbound_telegram_message_id=%s,
                  sent_confirmed_at=%s
                  WHERE operation_id=%s AND attempt_number=%s
                    AND quality_disposition='ALLOWED_BEFORE_DELIVERY'
                    AND sent_confirmed=FALSE""", (
                    row["outbound_telegram_message_id"], row["sent_confirmed_at"],
                    row["operation_id"], row["generation_attempt_count"],
                ))
            if (row is not None and resource_classification == "ORDINARY_NONCOMMERCIAL"
                    and creator_profile_id is not None and fanvue_account_id is not None):
                cursor.execute("""INSERT INTO market_tier_confirmed_reply_events(
                    event_id,operation_id,creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,resource_classification,
                    outbound_telegram_message_id,confirmed_at)
                    VALUES(%s,%s,%s,%s,%s,%s,'ORDINARY_NONCOMMERCIAL',%s,%s)
                    ON CONFLICT(operation_id) DO NOTHING""", (
                    uuid4(), row["operation_id"], creator_profile_id,
                    fanvue_account_id, row["inbound_sender_telegram_user_id"],
                    row["telegram_chat_id"], row["outbound_telegram_message_id"],
                    row["sent_confirmed_at"]))
        if row is not None:
            self._finalize_optional_active_offer_follow_through(row)
        return self._item(row) if row else None

    def _finalize_optional_active_offer_follow_through(self, operation):
        """Keep optional follow-through persistence outside delivery truth."""
        status = "UNAVAILABLE"
        try:
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute(
                    "SELECT to_regclass('public.active_offer_follow_through_events') AS present"
                )
                if cursor.fetchone()["present"] is not None:
                    cursor.execute("""UPDATE active_offer_follow_through_events
                        SET delivery_state='SENT_CONFIRMED',confirmed_at=%s,
                            outbound_telegram_message_id=%s,updated_at=NOW()
                        WHERE operation_id=%s
                          AND delivery_state IN ('AUTHORIZED','GENERATED','SENDING')""",
                        (operation["sent_confirmed_at"],
                         operation["outbound_telegram_message_id"],
                         operation["operation_id"]))
                    status = "RECORDED" if cursor.rowcount else "NOT_APPLICABLE"
                cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                    delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                    updated_at=NOW() WHERE operation_id=%s""", (
                    json.dumps({"optionalPersistence": {
                        "activeOfferFollowThrough": status,
                        "deliveryConfirmationAuthoritative": True,
                    }}), operation["operation_id"],
                ))
        except Exception as error:
            # The customer-visible confirmation already committed. Record the
            # optional failure separately and never downgrade delivery truth.
            self._one("""UPDATE ordinary_chat_reply_operations SET
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                updated_at=NOW() WHERE operation_id=%s RETURNING *""", (
                json.dumps({"optionalPersistence": {
                    "activeOfferFollowThrough": "ERROR",
                    "errorType": type(error).__name__,
                    "deliveryConfirmationAuthoritative": True,
                }}), operation["operation_id"],
            ))

    def record_provider_evidence(self, operation_id, *, owner, evidence):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=jsonb_set(COALESCE(delivery_payload,'{}'::jsonb),
                '{provider_delivery_evidence}', COALESCE(delivery_payload->'provider_delivery_evidence','{}'::jsonb) || %s::jsonb),
            updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s
              AND (NOT (%s::jsonb ? 'transport_route')
                OR delivery_payload#>>'{provider_delivery_evidence,transport_route,invocation_started_at}' IS NULL
                OR (delivery_payload#>>'{provider_delivery_evidence,transport_route,invocation_started_at}')::timestamptz < sending_at)
            RETURNING *""",
            (json.dumps(dict(evidence)),
             operation_id, owner, json.dumps(dict(evidence))))

    def reconcile_confirmed_commercial_edit(
        self, operation_id, *, telegram_message_id, response_text,
        response_payload, delivery_payload,
    ):
        """Persist a provider-verified in-place edit without reopening send state."""
        content_sha256 = __import__("hashlib").sha256(
            str(response_text).encode("utf-8")
        ).hexdigest()
        current = self.get(operation_id)
        merged_delivery = self.merge_current_delivery_with_durable_audit(
            getattr(current, "delivery_payload", None), delivery_payload,
        )
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            response_text=%s,response_content_sha256=%s,
            response_payload=%s::jsonb,delivery_payload=%s::jsonb,
            last_error=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENT_CONFIRMED'
              AND outbound_telegram_message_id=%s RETURNING *""", (
                response_text, content_sha256, json.dumps(response_payload),
                json.dumps(merged_delivery), operation_id,
                int(telegram_message_id),
            ))

    def fail_send(self, operation_id, *, owner, reason, ambiguous=False,
                  terminal=False, retry_seconds=30, evidence=None):
        requested = "SEND_UNCERTAIN" if ambiguous else "TERMINAL_FAILED" if terminal else "RETRYABLE"
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN %s='RETRYABLE' AND send_attempt_count>=max_send_attempts
                       THEN 'TERMINAL_FAILED' ELSE %s END,
            last_error=%s,uncertain_at=CASE WHEN %s THEN NOW() ELSE uncertain_at END,
            failed_at=CASE WHEN %s OR send_attempt_count>=max_send_attempts
                           THEN NOW() ELSE failed_at END,
            next_retry_at=CASE WHEN %s AND send_attempt_count<max_send_attempts
                               THEN NOW()+(%s*INTERVAL '1 second') ELSE NULL END,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s RETURNING *""",
            (requested,requested,reason[:1000],ambiguous,terminal,(not ambiguous and not terminal),
             max(1,int(retry_seconds)),json.dumps(evidence or {}),operation_id,owner))

    def record_deterministic_delivery_block(self, operation_id, *, owner, reason,
                                            metadata=None):
        """Stop transport retries until a deterministic authority changes."""
        evidence = {"deterministicDeliveryBlock": {
            "reason": str(reason), "metadata": dict(metadata or {}),
            "transportAttempted": False,
        }}
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',last_error=%s,next_retry_at=NULL,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s
            RETURNING *""", (
                f"deterministic_delivery_block:{str(reason)[:900]}",
                json.dumps(evidence),operation_id,owner,
            ))

    def recover_terminal_generated_for_delivery(
        self, *, operation_id, creator_profile_id, fanvue_account_id,
        telegram_user_id, telegram_chat_id, inbound_message_id,
        approved_by, idempotency_key, historical_cause=None,
        historical_infrastructure_cause=None, incident_resolved_at=None,
    ):
        """Reopen one current, unsent generated reply for one governed send only."""
        marker = {"operatorAuthorizedDeliveryRecovery": {
            "approvedBy": str(approved_by),
            "idempotencyKey": str(idempotency_key),
            "previousState": "TERMINAL_FAILED",
            "previousSendAttemptCount": 5,
            "generatedPayloadReused": True,
            "providerRegenerationAuthorized": False,
            "historicalCause": historical_cause,
            "historicalInfrastructureCause": historical_infrastructure_cause,
            "incidentResolvedAt": (
                incident_resolved_at.isoformat()
                if hasattr(incident_resolved_at, "isoformat")
                else incident_resolved_at
            ),
        }}
        return self._one("""UPDATE ordinary_chat_reply_operations target SET
            state='RETRYABLE',send_attempt_count=0,max_send_attempts=1,
            next_retry_at=NOW(),last_error='operator_authorized_delivery_recovery',
            delivery_payload=COALESCE(target.delivery_payload,'{}'::jsonb)||%s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE target.operation_id=%s
              AND target.telegram_account_scope='AVA_TELETHON_PRIVATE'
              AND target.telegram_chat_id=%s
              AND target.inbound_sender_telegram_user_id=%s
              AND target.inbound_telegram_message_id=%s
              AND target.state='TERMINAL_FAILED'
              AND target.response_payload IS NOT NULL
              AND BTRIM(COALESCE(target.response_text,''))<>''
              AND target.outbound_telegram_message_id IS NULL
              AND target.sent_confirmed_at IS NULL
              AND EXISTS(SELECT 1 FROM telegram_sales_prospects prospect
                WHERE prospect.creator_profile_id=%s
                  AND prospect.fanvue_account_id=%s
                  AND prospect.telegram_user_id=%s
                  AND prospect.telegram_chat_id=%s)
              AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                WHERE newer.telegram_account_scope=target.telegram_account_scope
                  AND newer.telegram_chat_id=target.telegram_chat_id
                  AND newer.inbound_telegram_message_id>target.inbound_telegram_message_id)
              AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations delivered
                WHERE delivered.telegram_account_scope=target.telegram_account_scope
                  AND delivered.telegram_chat_id=target.telegram_chat_id
                  AND delivered.sent_confirmed_at>target.inbound_received_at
                  AND delivered.state='SENT_CONFIRMED'
                  AND delivered.outbound_telegram_message_id IS NOT NULL)
            RETURNING target.*""", (
                json.dumps(marker),operation_id,telegram_chat_id,telegram_user_id,
                inbound_message_id,creator_profile_id,fanvue_account_id,
                telegram_user_id,telegram_chat_id,
            ))

    def recover_attested_not_delivered(
        self, *, operation_id, creator_profile_id, fanvue_account_id,
        telegram_account_scope, telegram_user_id, telegram_chat_id,
        inbound_message_id,
    ):
        """Atomically unlock one proven-not-delivered persisted reply for retry."""
        import hashlib
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"ordinary-not-delivered-recovery:{operation_id}",),
            )
            cursor.execute(
                "SELECT * FROM ordinary_chat_reply_operations "
                "WHERE operation_id=%s FOR UPDATE", (operation_id,),
            )
            operation = cursor.fetchone()
            if operation is None:
                raise LookupError("Ordinary reply operation was not found.")
            expected_scope = (
                int(operation["telegram_chat_id"]) == int(telegram_chat_id)
                and int(operation["inbound_sender_telegram_user_id"]) == int(telegram_user_id)
                and int(operation["inbound_telegram_message_id"]) == int(inbound_message_id)
                and operation["telegram_account_scope"] == telegram_account_scope
            )
            if not expected_scope:
                raise PermissionError("Ordinary reply recovery scope mismatch.")
            if operation["state"] != "SEND_UNCERTAIN":
                raise ValueError("Only SEND_UNCERTAIN can use NOT_DELIVERED recovery.")
            text = str(operation.get("response_text") or "")
            stored_hash = str(operation.get("response_content_sha256") or "")
            if not operation.get("response_payload") or not text.strip():
                raise ValueError("Persisted response payload and text are required.")
            if hashlib.sha256(text.encode()).hexdigest() != stored_hash:
                raise ValueError("Persisted response hash is invalid.")
            if operation.get("outbound_telegram_message_id") is not None or operation.get("sent_confirmed_at") is not None:
                raise ValueError("Confirmed delivery evidence blocks NOT_DELIVERED recovery.")
            if (operation.get("claim_owner") is not None
                    and operation.get("lease_expires_at") is not None
                    and operation["lease_expires_at"] > __import__("datetime").datetime.now(
                        operation["lease_expires_at"].tzinfo)):
                raise ValueError("An active operation lease blocks recovery.")
            if int(operation["send_attempt_count"]) >= int(operation["max_send_attempts"]):
                raise ValueError("The durable send-attempt limit blocks recovery.")
            cursor.execute(
                "SELECT * FROM operator_delivery_resolutions "
                "WHERE ordinary_operation_id=%s FOR UPDATE", (operation_id,),
            )
            resolution = cursor.fetchone()
            if resolution is None or resolution["outcome"] != "NOT_DELIVERED":
                raise ValueError("Authoritative NOT_DELIVERED reconciliation is required.")
            resolution_scope = (
                int(resolution["creator_profile_id"]) == int(creator_profile_id)
                and int(resolution["fanvue_account_id"]) == int(fanvue_account_id)
                and int(resolution["telegram_user_id"]) == int(telegram_user_id)
                and int(resolution["telegram_chat_id"]) == int(telegram_chat_id)
                and resolution["original_operation_state"] == "SEND_UNCERTAIN"
                and resolution["provenance"] == "OPERATOR_ATTESTED"
            )
            if not resolution_scope:
                raise PermissionError("NOT_DELIVERED attestation scope mismatch.")
            cursor.execute("""SELECT 1 WHERE
                EXISTS(SELECT 1 FROM telegram_private_inbound_messages newer
                  WHERE newer.telegram_account_scope=%s AND newer.telegram_chat_id=%s
                    AND newer.telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
                  WHERE newer.telegram_account_scope=%s AND newer.telegram_chat_id=%s
                    AND newer.inbound_telegram_message_id>%s)
                OR EXISTS(SELECT 1 FROM ordinary_chat_reply_operations delivered
                  WHERE delivered.telegram_account_scope=%s AND delivered.telegram_chat_id=%s
                    AND delivered.state='SENT_CONFIRMED'
                    AND delivered.sent_confirmed_at>%s)
                OR EXISTS(SELECT 1 FROM telegram_operator_message_operations manual
                  WHERE manual.creator_profile_id=%s AND manual.fanvue_account_id=%s
                    AND manual.telegram_user_id=%s AND manual.telegram_chat_id=%s
                    AND manual.state='CONFIRMED' AND manual.confirmed_at>%s)""", (
                operation["telegram_account_scope"], telegram_chat_id, inbound_message_id,
                operation["telegram_account_scope"], telegram_chat_id, inbound_message_id,
                operation["telegram_account_scope"], telegram_chat_id,
                operation["inbound_received_at"], creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id, operation["inbound_received_at"],
            ))
            if cursor.fetchone() is not None:
                raise ValueError("The persisted response is stale or already answered.")
            cursor.execute("""SELECT COALESCE(mode,'AVA_AUTO') AS mode,
                COALESCE(communication_disposition,'ACTIVE') AS disposition
                FROM telegram_relationship_controls
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s LIMIT 1""", (
                creator_profile_id, fanvue_account_id, telegram_user_id, telegram_chat_id,
            ))
            control = cursor.fetchone()
            if control and (control["mode"] != "AVA_AUTO" or control["disposition"] != "ACTIVE"):
                raise PermissionError("Relationship controls block recovery.")
            marker = {"attestedNotDeliveredRecovery": {
                "authority": "OperatorDeliveryResolutionRepository",
                "resolutionId": str(resolution["resolution_id"]),
                "outcome": "NOT_DELIVERED",
                "samePayload": True,
                "providerRegenerationAuthorized": False,
                "previousSendAttemptCount": int(operation["send_attempt_count"]),
            }}
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='RETRYABLE',next_retry_at=NOW(),
                last_error='attested_not_delivered_same_payload_retry',
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
                WHERE operation_id=%s AND state='SEND_UNCERTAIN'
                  AND response_payload IS NOT NULL AND response_text=%s
                  AND response_content_sha256=%s
                  AND outbound_telegram_message_id IS NULL
                  AND sent_confirmed_at IS NULL
                RETURNING *""", (
                json.dumps(marker), operation_id, text, stored_hash,
            ))
            recovered = cursor.fetchone()
            if recovered is None:
                raise RuntimeError("NOT_DELIVERED recovery lost its atomic state race.")
            connection.commit()
            return self._item(recovered)

    def reconcile_send_uncertain_delivery(
        self, *, operation_id, creator_profile_id, fanvue_account_id,
        telegram_user_id, telegram_chat_id, inbound_message_id,
        expected_text, telegram_message_id, telegram_sent_at,
        telegram_sender_id, authorized_sender_id, evidence_source,
        idempotency_key,
    ):
        """Confirm one uncertain operation from exact external delivery evidence."""
        marker = {"sendUncertainReconciliation": {
            "authority": "OrdinaryChatReplyRepository",
            "evidenceSource": str(evidence_source),
            "idempotencyKey": str(idempotency_key),
            "telegramMessageId": int(telegram_message_id),
            "telegramSenderId": int(telegram_sender_id),
            "telegramSentAt": telegram_sent_at.isoformat(),
            "customerVisibleText": str(expected_text),
            "resendPerformed": False,
            "providerGenerationPerformed": False,
        }}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"ordinary-reconciliation:{fanvue_account_id}:{telegram_message_id}",),
            )
            cursor.execute("""SELECT target.* FROM ordinary_chat_reply_operations target
                WHERE target.operation_id=%s FOR UPDATE""", (operation_id,))
            row = cursor.fetchone()
            if row is None:
                return None
            existing = dict(dict(row.get("delivery_payload") or {}).get(
                "sendUncertainReconciliation") or {})
            if row["state"] == "SENT_CONFIRMED":
                if (existing.get("idempotencyKey") == str(idempotency_key)
                        and row["outbound_telegram_message_id"] == int(telegram_message_id)):
                    return self._item(row)
                return None
            if row["state"] != "SEND_UNCERTAIN":
                return None
            canonical_text = str(
                dict(row.get("delivery_payload") or {}).get("message_text")
                or dict(dict(row.get("response_payload") or {}).get(
                    "delivery_payload") or {}).get("message_text")
                or row.get("response_text") or ""
            )
            provider = dict(dict(row.get("delivery_payload") or {}).get(
                "provider_delivery_evidence") or {})
            exact = (
                row["telegram_account_scope"] == "AVA_TELETHON_PRIVATE"
                and int(row["telegram_chat_id"]) == int(telegram_chat_id)
                and int(row["inbound_sender_telegram_user_id"]) == int(telegram_user_id)
                and int(row["inbound_telegram_message_id"]) == int(inbound_message_id)
                and canonical_text == str(expected_text)
                and int(provider.get("telegram_message_id") or 0) == int(telegram_message_id)
                and int(telegram_sender_id) == int(authorized_sender_id)
                and row["sending_at"] is not None
                and telegram_sent_at >= row["sending_at"]
                and (row["uncertain_at"] is None or telegram_sent_at <= row["uncertain_at"])
            )
            if not exact:
                return None
            cursor.execute("""SELECT 1 FROM creator_profiles creator
                JOIN telegram_identity_map mapping
                  ON mapping.fanvue_account_id::text=creator.fanvue_account_id
                 AND mapping.telegram_user_id=%s AND mapping.telegram_chat_id=%s
                 AND mapping.is_active=TRUE AND mapping.verification_status='VERIFIED'
               WHERE creator.id=%s AND creator.fanvue_account_id=%s::text
                 AND creator.is_active=TRUE""",
                (telegram_user_id, telegram_chat_id, creator_profile_id,
                 fanvue_account_id))
            if cursor.fetchone() is None:
                return None
            cursor.execute("""SELECT 1 FROM ordinary_chat_reply_operations
                WHERE operation_id<>%s AND telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND telegram_chat_id=%s AND outbound_telegram_message_id=%s""",
                (operation_id, telegram_chat_id, telegram_message_id))
            if cursor.fetchone() is not None:
                return None
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SENT_CONFIRMED',response_text=%s,response_content_sha256=%s,
                outbound_telegram_message_id=%s,sent_confirmed_at=%s,
                uncertain_at=NULL,next_retry_at=NULL,last_error=NULL,
                claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||%s::jsonb,
                updated_at=NOW()
                WHERE operation_id=%s AND state='SEND_UNCERTAIN' RETURNING *""", (
                canonical_text,
                __import__("hashlib").sha256(canonical_text.encode()).hexdigest(),
                telegram_message_id, telegram_sent_at, json.dumps(marker), operation_id,
            ))
            confirmed = cursor.fetchone()
            if confirmed is None:
                return None
            cursor.execute("SELECT to_regclass('public.market_tier_confirmed_reply_events') AS present")
            if cursor.fetchone()["present"] is not None:
                cursor.execute("""INSERT INTO market_tier_confirmed_reply_events(
                    event_id,operation_id,creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,resource_classification,
                    outbound_telegram_message_id,confirmed_at)
                    VALUES(%s,%s,%s,%s,%s,%s,'ORDINARY_NONCOMMERCIAL',%s,%s)
                    ON CONFLICT(operation_id) DO NOTHING""", (
                    uuid4(), confirmed["operation_id"], creator_profile_id,
                    fanvue_account_id, telegram_user_id, telegram_chat_id,
                    telegram_message_id, telegram_sent_at,
                ))
        self._finalize_optional_active_offer_follow_through(confirmed)
        return self._item(confirmed)

    def recover_orphaned_sends(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SEND_UNCERTAIN',last_error='worker_restarted_during_provider_send',
                uncertain_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                next_retry_at=NULL,updated_at=NOW()
                WHERE state='SENDING' RETURNING *""")
            return [self._item(row) for row in cursor.fetchall()]

    def quarantine_legacy_ambiguous_media_retries(self):
        """Stop legacy sendPhoto retries whose provider acceptance is unknowable."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SEND_UNCERTAIN',
                last_error='legacy_sendPhoto_acceptance_unknown',
                uncertain_at=COALESCE(uncertain_at,updated_at,NOW()),
                next_retry_at=NULL,claim_owner=NULL,claimed_at=NULL,
                lease_expires_at=NULL,updated_at=NOW()
                WHERE state='RETRYABLE' AND send_attempt_count>0
                  AND outbound_telegram_message_id IS NULL
                  AND last_error='TelegramOutboundSendError: Telegram sendPhoto request failed.'
                  AND COALESCE(delivery_payload->>'delivery_method','')='private_ppv_media'
                  AND NULLIF(delivery_payload->>'asset_path','') IS NOT NULL
                RETURNING *""")
            return [self._item(row) for row in cursor.fetchall()]

    def _one(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); row=cursor.fetchone()
        return self._item(row) if row else None

    @staticmethod
    def _item(row):
        if row is None: return None
        values=dict(row); values["operation_id"]=UUID(str(values["operation_id"]))
        values["state"]=OrdinaryChatReplyState(values["state"])
        for key in ("conversation_burst_id", "burst_survivor_operation_id"):
            if values.get(key) is not None:
                values[key] = UUID(str(values[key]))
        for key in ("response_payload","delivery_payload"):
            values[key]=dict(values[key]) if values.get(key) is not None else None
        for key in ("burst_member_obligations", "burst_obligations"):
            values[key]=list(values.get(key) or [])
        return OrdinaryChatReplyOperation(**values)
