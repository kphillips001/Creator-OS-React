"""PostgreSQL claims and lifecycle transitions for ordinary Telegram replies."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.ordinary_chat_reply_operation import (
    OrdinaryChatReplyOperation, OrdinaryChatReplyState,
)


class OrdinaryChatReplyRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_or_create(self, *, account_scope, chat_id, inbound_message_id,
                      sender_user_id, correlation_id, inbound_message_text,
                      inbound_received_at=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO ordinary_chat_reply_operations(
                operation_id,telegram_account_scope,telegram_chat_id,
                inbound_telegram_message_id,inbound_sender_telegram_user_id,correlation_id,
                inbound_message_text,inbound_received_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,COALESCE(%s,NOW()))
                ON CONFLICT(telegram_account_scope,telegram_chat_id,inbound_telegram_message_id)
                DO NOTHING RETURNING *""", (uuid4(), account_scope, chat_id,
                inbound_message_id, sender_user_id, correlation_id,
                inbound_message_text, inbound_received_at))
            row = cursor.fetchone(); created = row is not None
            if row is None:
                cursor.execute("""SELECT * FROM ordinary_chat_reply_operations
                    WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                      AND inbound_telegram_message_id=%s""",
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

    def get(self, operation_id):
        return self._one("SELECT * FROM ordinary_chat_reply_operations WHERE operation_id=%s",
                         (operation_id,))

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
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='GENERATING',claim_owner=%s,claimed_at=NOW(),
            lease_expires_at=NOW()+(%s*INTERVAL '1 second'),
            generation_attempt_count=generation_attempt_count+1,updated_at=NOW()
            WHERE operation_id=%s AND (
              state='PENDING_GENERATION'
              OR (state='RETRYABLE' AND response_payload IS NULL
                  AND COALESCE(next_retry_at,NOW())<=NOW())
              OR (state='GENERATING' AND lease_expires_at<NOW()))
              AND generation_attempt_count<max_generation_attempts
            RETURNING *""", (owner, max(1, int(lease_seconds)), operation_id))

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
        return self._one("""UPDATE ordinary_chat_reply_operations current SET
            state='RETRYABLE',next_retry_at=GREATEST(
              COALESCE((SELECT MIN(existing.next_retry_at)
                FROM ordinary_chat_reply_operations existing
                WHERE existing.telegram_account_scope=current.telegram_account_scope
                  AND existing.telegram_chat_id=current.telegram_chat_id
                  AND existing.state='RETRYABLE' AND existing.response_payload IS NULL
                  AND existing.last_error IN (
                    'availability_deferred','quality_corrective_retry_scheduled'
                  )),%s),
              NOW()+(%s*INTERVAL '1 second')),
            last_error=%s,
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='PENDING_GENERATION'
              AND response_payload IS NULL AND send_attempt_count=0 RETURNING *""", (
            available_at,quiet_seconds,"availability_deferred",
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

    def record_pre_generation_commercial_decision(self, operation_id, projection):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            updated_at=NOW() WHERE operation_id=%s
              AND state='PENDING_GENERATION' AND response_payload IS NULL
            RETURNING *""", (json.dumps({
                "preGenerationCommercialDecision": dict(projection)}), operation_id))

    def buyer_attention_context(self, *, telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT COALESCE(profile.purchase_count,0) AS purchase_count,
                COALESCE(profile.lifetime_gross_minor,0) AS lifetime_gross_minor
                FROM telegram_identity_map mapping
                LEFT JOIN customer_commerce_profiles profile
                  ON profile.fanvue_account_id=mapping.fanvue_account_id
                 AND profile.external_fanvue_user_uuid=mapping.external_fanvue_user_uuid
                WHERE mapping.telegram_user_id=%s AND mapping.is_active
                  AND mapping.verification_status='VERIFIED' LIMIT 1""",(telegram_user_id,))
            row=cursor.fetchone()
        purchases=int((row or {}).get("purchase_count") or 0)
        gross=int((row or {}).get("lifetime_gross_minor") or 0)
        return {"verified_buyer":purchases>0,"repeat_buyer":purchases>1,
                "high_value_buyer":gross>=50000}

    def release_due_availability(self, *, account_scope, now):
        """Atomically collapse each quiet burst to its latest authoritative turn."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""WITH candidates AS (
                SELECT operation_id,telegram_chat_id,next_retry_at,
                       MAX(inbound_telegram_message_id) OVER(
                         PARTITION BY telegram_chat_id) AS latest_message_id,
                       CASE
                         WHEN COALESCE(inbound_message_text,'') ~* %s THEN 2
                         WHEN COALESCE(inbound_message_text,'') ~* %s THEN 1
                         ELSE 0 END AS obligation_priority,
                       inbound_telegram_message_id
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND state='RETRYABLE'
                  AND response_payload IS NULL AND send_attempt_count=0
                  AND last_error IN (
                    'availability_deferred','quality_corrective_retry_scheduled'
                  )
            ), ranked AS (
                SELECT *,ROW_NUMBER() OVER(PARTITION BY telegram_chat_id
                    ORDER BY obligation_priority DESC,
                             inbound_telegram_message_id DESC) AS rank
                FROM candidates
            ), due_chats AS (
                SELECT telegram_chat_id FROM candidates
                WHERE inbound_telegram_message_id=latest_message_id
                  AND next_retry_at<=%s
            ) UPDATE ordinary_chat_reply_operations o SET
                state='SUPPRESSED',next_retry_at=NULL,
                last_error='availability_burst_coalesced',updated_at=NOW()
            FROM ranked r,due_chats d
            WHERE o.operation_id=r.operation_id AND r.telegram_chat_id=d.telegram_chat_id
              AND r.rank>1""", (
                r"\?|(^|\W)(who|what|when|where|why|how|can|could|would|do|does|did|are|is|will)(\W|$)",
                r"(^|\W)(buy|price|purchase|unlock|offer|available|content|photo|video|set)(\W|$)",
                account_scope, now,
            ))
            cursor.execute("""WITH ready AS (
                SELECT o.operation_id FROM ordinary_chat_reply_operations o
                WHERE o.telegram_account_scope=%s AND o.state='RETRYABLE'
                  AND o.response_payload IS NULL AND o.send_attempt_count=0
                  AND o.last_error IN (
                    'availability_deferred','quality_corrective_retry_scheduled'
                  ) AND o.next_retry_at<=%s
                  AND NOT EXISTS (SELECT 1 FROM ordinary_chat_reply_operations newer
                    WHERE newer.telegram_account_scope=o.telegram_account_scope
                      AND newer.telegram_chat_id=o.telegram_chat_id
                      AND newer.state='RETRYABLE' AND newer.response_payload IS NULL
                      AND newer.last_error IN (
                        'availability_deferred','quality_corrective_retry_scheduled'
                      )
                      AND newer.inbound_telegram_message_id>o.inbound_telegram_message_id)
            ) UPDATE ordinary_chat_reply_operations o SET
                state='PENDING_GENERATION',next_retry_at=NULL,last_error=NULL,
                updated_at=NOW() FROM ready WHERE o.operation_id=ready.operation_id
                RETURNING o.*""", (account_scope, now))
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

    def coalesced_burst_messages(self, operation, *, now):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT inbound_telegram_message_id,inbound_message_text
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND ((operation_id=%s) OR (
                    state='SUPPRESSED' AND last_error='availability_burst_coalesced'
                    AND updated_at>=%s-INTERVAL '2 minutes'))
                ORDER BY inbound_telegram_message_id""", (
                operation.telegram_account_scope, operation.telegram_chat_id,
                operation.operation_id, now,
            ))
            rows = cursor.fetchall()
        return [{"message_id": int(row["inbound_telegram_message_id"]),
                 "text": str(row["inbound_message_text"] or "").strip()}
                for row in rows if str(row["inbound_message_text"] or "").strip()]

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
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='GENERATED',response_payload=%s::jsonb,response_text=%s,
            response_content_sha256=%s,delivery_payload=%s::jsonb,
            conversation_thread_id=COALESCE(conversation_thread_id,%s),
            generated_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=NULL,last_error=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING *""",
            (json.dumps(response_payload), response_text, content_sha256,
             json.dumps(delivery_payload), conversation_thread_id, operation_id, owner))

    def store_suppressed_generation(
        self, operation_id, *, owner, response_payload, response_text,
        content_sha256, delivery_payload, reason, conversation_thread_id=None,
    ):
        """Persist an intentional fail-closed generation as terminal/non-sendable."""
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='SUPPRESSED',response_payload=%s::jsonb,response_text=%s,
            response_content_sha256=%s,delivery_payload=%s::jsonb,
            conversation_thread_id=COALESCE(conversation_thread_id,%s),
            generated_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=NULL,last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING *""",
            (json.dumps(response_payload), response_text, content_sha256,
             json.dumps(delivery_payload), conversation_thread_id, reason[:1000],
            operation_id, owner))

    def schedule_quality_correction(
        self, operation_id, *, owner, response_payload, delivery_payload,
        reasons, retry_seconds=8,
    ):
        """Durably authorize the sole corrective generation for a required reply."""
        evidence = {
            "qualityCorrectiveRetry": {
                "required": True,
                "attempt": 2,
                "blockingReasons": list(reasons),
                "previousCandidateBlockedBeforeDelivery": True,
                "previousCandidateDiagnostics": dict(
                    response_payload.get("diagnostic_metadata") or {}
                ),
            }
        }
        return self._one("""UPDATE ordinary_chat_reply_operations current SET
            state=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>current.inbound_telegram_message_id
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN 'SUPPRESSED' ELSE 'RETRYABLE' END,
            response_payload=NULL,response_text=NULL,response_content_sha256=NULL,
            delivery_payload=COALESCE(%s::jsonb,'{}'::jsonb) || %s::jsonb,
            generated_at=NULL,
            max_generation_attempts=LEAST(max_generation_attempts,2),
            next_retry_at=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>current.inbound_telegram_message_id
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN NULL ELSE NOW()+(%s*INTERVAL '1 second') END,
            last_error=CASE WHEN EXISTS (
              SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=current.telegram_account_scope
                AND newer.telegram_chat_id=current.telegram_chat_id
                AND newer.inbound_telegram_message_id>current.inbound_telegram_message_id
                AND newer.state NOT IN ('SENT_CONFIRMED','TERMINAL_FAILED')
            ) THEN 'quality_correction_superseded_by_newer_inbound'
              ELSE 'quality_corrective_retry_scheduled' END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE current.operation_id=%s AND current.state='GENERATING'
              AND current.claim_owner=%s AND current.generation_attempt_count=1
              AND current.send_attempt_count=0
              AND current.outbound_telegram_message_id IS NULL
            RETURNING current.*""", (
            json.dumps(delivery_payload or {}), json.dumps(evidence),
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
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='GENERATED',response_payload=%s::jsonb,
            delivery_payload=%s::jsonb,next_retry_at=NULL,last_error=NULL,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state IN ('GENERATED','RETRYABLE')
              AND send_attempt_count=0 AND outbound_telegram_message_id IS NULL
              AND response_payload IS NOT NULL
            RETURNING *""", (
                json.dumps(response_payload), json.dumps(delivery_payload),
                operation_id,
            ))

    def fail_generation(self, operation_id, *, owner, reason, retry_seconds=30):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN generation_attempt_count>=max_generation_attempts
                       THEN 'TERMINAL_FAILED' ELSE 'RETRYABLE' END,
            last_error=%s,failed_at=CASE WHEN generation_attempt_count>=max_generation_attempts
                                        THEN NOW() ELSE failed_at END,
            next_retry_at=CASE WHEN generation_attempt_count>=max_generation_attempts
                               THEN NULL ELSE NOW()+(%s*INTERVAL '1 second') END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s RETURNING *""",
            (reason[:1000], max(1,int(retry_seconds)), operation_id, owner))

    def fail_empty_generation(self, operation_id, *, owner, reason):
        """Atomically reject an unblocked empty candidate for immediate retry."""
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN generation_attempt_count>=max_generation_attempts
                       THEN 'TERMINAL_FAILED' ELSE 'RETRYABLE' END,
            last_error=%s,failed_at=CASE WHEN generation_attempt_count>=max_generation_attempts
                                        THEN NOW() ELSE failed_at END,
            next_retry_at=CASE WHEN generation_attempt_count>=max_generation_attempts
                               THEN NULL ELSE NOW() END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATING' AND claim_owner=%s
            RETURNING *""", (reason[:1000], operation_id, owner))

    def suppress(self, operation_id, *, reason):
        return self._one("""UPDATE ordinary_chat_reply_operations SET state='SUPPRESSED',
            last_error=%s,claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
            next_retry_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state IN (
              'PENDING_GENERATION','GENERATED','RETRYABLE') RETURNING *""",
            (reason[:1000], operation_id))

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
            send_attempt_count=send_attempt_count+1,updated_at=NOW()
            WHERE operation_id=%s AND (
              state='GENERATED' OR (state='RETRYABLE' AND response_payload IS NOT NULL
                                    AND COALESCE(next_retry_at,NOW())<=NOW()))
              AND send_attempt_count<max_send_attempts RETURNING *""",
            (owner,max(1,int(lease_seconds)),operation_id))

    def has_newer_unresolved_inbound(self, operation_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(SELECT 1
                FROM ordinary_chat_reply_operations current
                JOIN ordinary_chat_reply_operations newer
                  ON newer.telegram_account_scope=current.telegram_account_scope
                 AND newer.telegram_chat_id=current.telegram_chat_id
                 AND newer.inbound_telegram_message_id>current.inbound_telegram_message_id
                WHERE current.operation_id=%s
                  AND newer.state NOT IN ('TERMINAL_FAILED','SUPPRESSED')) AS present""",
                (operation_id,))
            row = cursor.fetchone()
        return bool(row and row["present"])

    def requeue_empty_generation(self, operation_id, *, reason):
        """Recover a definitively unsent empty result after a generation defect."""
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',response_payload=NULL,response_text=NULL,
            response_content_sha256=NULL,delivery_payload=NULL,generated_at=NULL,
            next_retry_at=NOW(),last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='GENERATED'
              AND COALESCE(response_text,'')='' AND send_attempt_count=0
              AND outbound_telegram_message_id IS NULL RETURNING *""",
            (reason[:1000], operation_id))

    def requeue_suppressed_engine_exception(self, operation_id, *, reason):
        """Release a definitively unsent empty engine-exception suppression."""
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state='RETRYABLE',response_payload=NULL,response_text=NULL,
            response_content_sha256=NULL,delivery_payload=NULL,generated_at=NULL,
            next_retry_at=NOW(),last_error=%s,updated_at=NOW()
            WHERE operation_id=%s AND state='SUPPRESSED'
              AND last_error='intentional_suppression:decision_engine_exception'
              AND COALESCE(response_text,'')='' AND send_attempt_count=0
              AND outbound_telegram_message_id IS NULL
              AND generation_attempt_count<max_generation_attempts RETURNING *""",
            (reason[:1000], operation_id))

    def requeue_historical_corrective(
        self, *, target_operation_id, causal_operation_id,
        creator_profile_id, fanvue_account_id, telegram_user_id,
        occurrence_id, approved_by, idempotency_key,
    ):
        """Re-establish one latest-turn obligation without reusing rejected copy.

        The due-availability poll remains the only release authority. This method
        neither invokes generation nor sends to Telegram.
        """
        audit={"approvedHistoricalCorrection":{
            "attentionOccurrenceId":str(occurrence_id),
            "causalOperationId":str(causal_operation_id),
            "approvedBy":str(approved_by),"idempotencyKey":str(idempotency_key),
            "historicalCandidateReused":False,
        }}
        return self._one("""UPDATE ordinary_chat_reply_operations target SET
          state='RETRYABLE',response_payload=NULL,response_text=NULL,
          response_content_sha256=NULL,
          delivery_payload=%s::jsonb,generation_attempt_count=0,
          max_generation_attempts=LEAST(target.max_generation_attempts,2),
          send_attempt_count=0,next_retry_at=NOW()+INTERVAL '8 seconds',
          last_error='availability_deferred',generated_at=NULL,
          claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
          FROM ordinary_chat_reply_operations causal
          WHERE target.operation_id=%s AND causal.operation_id=%s
            AND target.telegram_account_scope='AVA_TELETHON_PRIVATE'
            AND causal.telegram_account_scope=target.telegram_account_scope
            AND causal.telegram_chat_id=target.telegram_chat_id
            AND target.inbound_sender_telegram_user_id=%s
            AND causal.inbound_sender_telegram_user_id=%s
            AND target.state='SUPPRESSED' AND target.send_attempt_count=0
            AND target.outbound_telegram_message_id IS NULL
            AND causal.state='SUPPRESSED' AND causal.send_attempt_count=0
            AND (causal.last_error LIKE 'quality_blocked_before_delivery:%%'
                 OR causal.last_error LIKE 'quality_corrective_retry_exhausted:%%')
            AND EXISTS(SELECT 1 FROM telegram_sales_prospects p
              WHERE p.creator_profile_id=%s AND p.fanvue_account_id=%s
                AND p.telegram_user_id=%s AND p.telegram_chat_id=target.telegram_chat_id)
            AND NOT EXISTS(SELECT 1 FROM ordinary_chat_reply_operations newer
              WHERE newer.telegram_account_scope=target.telegram_account_scope
                AND newer.telegram_chat_id=target.telegram_chat_id
                AND newer.inbound_telegram_message_id>target.inbound_telegram_message_id)
          RETURNING target.*""", (json.dumps(audit),target_operation_id,causal_operation_id,
            telegram_user_id,telegram_user_id,creator_profile_id,fanvue_account_id,
            telegram_user_id))

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
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s RETURNING *""",
            (telegram_message_id,operation_id,owner))
            row = cursor.fetchone()
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
        return self._item(row) if row else None

    def record_provider_evidence(self, operation_id, *, owner, evidence):
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            delivery_payload=COALESCE(delivery_payload,'{}'::jsonb) || %s::jsonb,
            updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s RETURNING *""",
            (json.dumps({"provider_delivery_evidence": dict(evidence)}),
             operation_id, owner))

    def reconcile_confirmed_commercial_edit(
        self, operation_id, *, telegram_message_id, response_text,
        response_payload, delivery_payload,
    ):
        """Persist a provider-verified in-place edit without reopening send state."""
        content_sha256 = __import__("hashlib").sha256(
            str(response_text).encode("utf-8")
        ).hexdigest()
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            response_text=%s,response_content_sha256=%s,
            response_payload=%s::jsonb,delivery_payload=%s::jsonb,
            last_error=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENT_CONFIRMED'
              AND outbound_telegram_message_id=%s RETURNING *""", (
                response_text, content_sha256, json.dumps(response_payload),
                json.dumps(delivery_payload), operation_id,
                int(telegram_message_id),
            ))

    def fail_send(self, operation_id, *, owner, reason, ambiguous=False,
                  terminal=False, retry_seconds=30):
        requested = "SEND_UNCERTAIN" if ambiguous else "TERMINAL_FAILED" if terminal else "RETRYABLE"
        return self._one("""UPDATE ordinary_chat_reply_operations SET
            state=CASE WHEN %s='RETRYABLE' AND send_attempt_count>=max_send_attempts
                       THEN 'TERMINAL_FAILED' ELSE %s END,
            last_error=%s,uncertain_at=CASE WHEN %s THEN NOW() ELSE uncertain_at END,
            failed_at=CASE WHEN %s OR send_attempt_count>=max_send_attempts
                           THEN NOW() ELSE failed_at END,
            next_retry_at=CASE WHEN %s AND send_attempt_count<max_send_attempts
                               THEN NOW()+(%s*INTERVAL '1 second') ELSE NULL END,
            claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
            WHERE operation_id=%s AND state='SENDING' AND claim_owner=%s RETURNING *""",
            (requested,requested,reason[:1000],ambiguous,terminal,(not ambiguous and not terminal),
             max(1,int(retry_seconds)),operation_id,owner))

    def recover_orphaned_sends(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations SET
                state='SEND_UNCERTAIN',last_error='worker_restarted_during_provider_send',
                uncertain_at=NOW(),claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                next_retry_at=NULL,updated_at=NOW()
                WHERE state='SENDING' RETURNING *""")
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
        for key in ("response_payload","delivery_payload"):
            values[key]=dict(values[key]) if values.get(key) is not None else None
        return OrdinaryChatReplyOperation(**values)
