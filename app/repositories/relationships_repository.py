"""Read-only Telegram relationship transcript queries."""

from uuid import uuid4

from app.database import get_db_connection


class RelationshipsRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def latest_messages(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH events AS (
                  SELECT o.inbound_sender_telegram_user_id telegram_user_id,
                         o.inbound_message_text content,o.inbound_received_at occurred_at,'CUSTOMER' direction,
                         'telegram:'||o.telegram_chat_id||':'||o.inbound_telegram_message_id event_key
                    FROM ordinary_chat_reply_operations o
                   WHERE o.telegram_account_scope='AVA_TELETHON_PRIVATE'
                     AND o.inbound_received_at IS NOT NULL
                     AND EXISTS(SELECT 1 FROM telegram_sales_prospects p WHERE
                       p.creator_profile_id=%s AND p.fanvue_account_id=%s
                       AND p.telegram_user_id=o.inbound_sender_telegram_user_id)
                  UNION ALL
                  SELECT o.inbound_sender_telegram_user_id,o.response_text,o.sent_confirmed_at,'AVA',
                         COALESCE('telegram:'||o.telegram_chat_id||':'||o.outbound_telegram_message_id,
                                  'correlation:'||o.correlation_id)
                    FROM ordinary_chat_reply_operations o
                   WHERE o.telegram_account_scope='AVA_TELETHON_PRIVATE' AND o.state='SENT_CONFIRMED'
                     AND o.sent_confirmed_at IS NOT NULL
                     AND EXISTS(SELECT 1 FROM telegram_sales_prospects p WHERE
                       p.creator_profile_id=%s AND p.fanvue_account_id=%s
                       AND p.telegram_user_id=o.inbound_sender_telegram_user_id)
                  UNION ALL
                  SELECT m.telegram_user_id,cm.text,cm.sent_at,
                         CASE WHEN cm.direction='inbound' THEN 'CUSTOMER' ELSE 'AVA' END,
                         COALESCE('telegram:'||(cm.raw_payload->>'telegram_chat_id')||':'||
                           (cm.raw_payload->>'telegram_message_id'),'chat-message:'||cm.id)
                    FROM chat_messages cm JOIN chat_threads thread ON thread.id=cm.thread_id
                    JOIN telegram_identity_map m ON m.fanvue_account_id=thread.fanvue_account_id
                     AND m.local_fanvue_user_id=thread.fanvue_user_id AND m.is_active=TRUE
                     AND m.verification_status='VERIFIED'
                   WHERE thread.fanvue_account_id=%s AND cm.raw_payload->>'provider'='TELEGRAM'
                     AND ((cm.direction='inbound' AND cm.sender_type='user') OR
                          (cm.direction='outbound' AND cm.sender_type='bot'))
                  UNION ALL
                  SELECT o.telegram_user_id,o.message_text,o.confirmed_at,'AVA',
                         'telegram:'||o.telegram_chat_id||':'||o.outbound_telegram_message_id
                    FROM telegram_operator_message_operations o
                   WHERE o.creator_profile_id=%s AND o.fanvue_account_id=%s
                     AND o.state='CONFIRMED' AND o.confirmed_at IS NOT NULL
                  UNION ALL
                  SELECT m.telegram_user_id,d.response_text,d.confirmed_at,'AVA',
                         COALESCE('telegram:'||d.telegram_chat_id||':'||d.outbound_telegram_message_id,
                                  'correlation:'||d.correlation_id)
                    FROM telegram_sales_delivery_operations d JOIN purchase_intents m
                      ON m.purchase_intent_id=d.purchase_intent_id
                     AND m.creator_profile_id=d.creator_profile_id AND m.fanvue_account_id=d.fanvue_account_id
                     AND m.telegram_chat_id=d.telegram_chat_id
                   WHERE d.creator_profile_id=%s AND d.fanvue_account_id=%s
                     AND d.state='CONFIRMED' AND d.confirmed_at IS NOT NULL
                ) SELECT DISTINCT ON (telegram_user_id) telegram_user_id,content,occurred_at,direction,event_key
                    FROM events WHERE BTRIM(COALESCE(content,''))<>''
                   ORDER BY telegram_user_id,occurred_at DESC,event_key DESC
            """, (creator_profile_id,fanvue_account_id,creator_profile_id,
                  fanvue_account_id,fanvue_account_id,creator_profile_id,
                  fanvue_account_id,creator_profile_id,fanvue_account_id))
            return {int(row["telegram_user_id"]):dict(row) for row in cursor.fetchall()}

    def commercial_attention_by_person(self, *, creator_profile_id: int,
                                       fanvue_account_id: int):
        """Project distinct failed presentations and verified purchases once."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT telegram_user_id,
                  COUNT(DISTINCT purchase_intent_id) FILTER (
                    WHERE status IN ('EXPIRED','ABANDONED','SUPERSEDED','ADMIN_CLOSED')
                      AND presented_at IS NOT NULL
                      AND purchased_at IS NULL
                  )::int AS failed_presentation_count,
                  COUNT(DISTINCT purchase_intent_id) FILTER (
                    WHERE status='PURCHASED' AND purchased_at IS NOT NULL
                  )::int AS verified_purchase_count
                FROM purchase_intents
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id IS NOT NULL
                GROUP BY telegram_user_id
            """, (creator_profile_id, fanvue_account_id))
            return {
                int(row["telegram_user_id"]): dict(row)
                for row in cursor.fetchall()
            }

    def inbox_state(self, *, creator_profile_id: int, fanvue_account_id: int):
        """Return actionable inbox state in one account-scoped query."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH relationship AS (
                  SELECT prospect.creator_profile_id,prospect.fanvue_account_id,
                         prospect.telegram_user_id,prospect.telegram_chat_id
                    FROM telegram_sales_prospects prospect
                   WHERE prospect.creator_profile_id=%s AND prospect.fanvue_account_id=%s
                  UNION
                  SELECT %s::BIGINT,mapping.fanvue_account_id,
                         mapping.telegram_user_id,mapping.telegram_chat_id
                    FROM telegram_identity_map mapping
                   WHERE mapping.fanvue_account_id=%s AND mapping.is_active=TRUE
                     AND mapping.verification_status='VERIFIED'
                ), inbound AS (
                  SELECT DISTINCT ON (telegram_user_id,telegram_chat_id)
                         telegram_user_id,telegram_chat_id,received_at last_customer_inbound_at,
                         message_id last_inbound_message_id,customer_text latest_inbound_text
                    FROM (
                      SELECT inbound_sender_telegram_user_id telegram_user_id,telegram_chat_id,
                             inbound_received_at received_at,inbound_telegram_message_id message_id,
                             inbound_message_text customer_text
                        FROM ordinary_chat_reply_operations
                       WHERE telegram_account_scope='AVA_TELETHON_PRIVATE' AND inbound_received_at IS NOT NULL
                      UNION ALL
                      SELECT telegram_user_id,telegram_chat_id,received_at,telegram_message_id,customer_text
                        FROM telegram_private_inbound_messages
                       WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                    ) received
                   ORDER BY telegram_user_id,telegram_chat_id,message_id DESC,received_at DESC
                ), outbound AS (
                  SELECT telegram_user_id,MAX(occurred_at) last_visible_outbound_at
                    FROM (
                      SELECT inbound_sender_telegram_user_id telegram_user_id,
                             sent_confirmed_at occurred_at
                        FROM ordinary_chat_reply_operations
                       WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                         AND state='SENT_CONFIRMED' AND outbound_telegram_message_id IS NOT NULL
                      UNION ALL
                      SELECT telegram_user_id,confirmed_at
                        FROM telegram_operator_message_operations
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND state='CONFIRMED' AND outbound_telegram_message_id IS NOT NULL
                      UNION ALL
                      SELECT mapping.telegram_user_id,delivery.confirmed_at
                        FROM telegram_sales_delivery_operations delivery
                        JOIN purchase_intents mapping
                          ON mapping.purchase_intent_id=delivery.purchase_intent_id
                         AND mapping.creator_profile_id=delivery.creator_profile_id
                         AND mapping.fanvue_account_id=delivery.fanvue_account_id
                         AND mapping.telegram_chat_id=delivery.telegram_chat_id
                       WHERE delivery.creator_profile_id=%s AND delivery.fanvue_account_id=%s
                         AND delivery.state='CONFIRMED'
                         AND delivery.outbound_telegram_message_id IS NOT NULL
                    ) visible GROUP BY telegram_user_id
                )
                SELECT relationship.telegram_user_id,relationship.telegram_chat_id,
                       COALESCE(control.mode,'AVA_AUTO') control_mode,
                       COALESCE(control.communication_disposition,'ACTIVE') communication_disposition,
                       (SELECT value_override.classification
                          FROM telegram_relationship_value_overrides value_override
                         WHERE value_override.creator_profile_id=relationship.creator_profile_id
                           AND value_override.fanvue_account_id=relationship.fanvue_account_id
                           AND value_override.telegram_user_id=relationship.telegram_user_id
                           AND value_override.telegram_chat_id=relationship.telegram_chat_id
                           AND value_override.removed_at IS NULL LIMIT 1
                       ) operator_classification,
                       (SELECT tier.market_tier
                          FROM telegram_relationship_market_tiers tier
                         WHERE tier.creator_profile_id=relationship.creator_profile_id
                           AND tier.fanvue_account_id=relationship.fanvue_account_id
                           AND tier.telegram_user_id=relationship.telegram_user_id
                           AND tier.telegram_chat_id=relationship.telegram_chat_id
                           AND tier.removed_at IS NULL LIMIT 1
                       ) market_tier,
                       inbound.last_customer_inbound_at,inbound.last_inbound_message_id,inbound.latest_inbound_text,
                       outbound.last_visible_outbound_at,NOW() database_now,
                       EXISTS(
                         SELECT 1 FROM ordinary_chat_reply_operations active_operation
                          WHERE active_operation.telegram_account_scope='AVA_TELETHON_PRIVATE'
                            AND active_operation.telegram_chat_id=relationship.telegram_chat_id
                            AND active_operation.inbound_sender_telegram_user_id=
                                relationship.telegram_user_id
                            AND (outbound.last_visible_outbound_at IS NULL OR
                                 active_operation.inbound_received_at>
                                     outbound.last_visible_outbound_at)
                            AND active_operation.state IN (
                              'RETRYABLE','PENDING_GENERATION','GENERATING',
                              'GENERATED','SENDING'
                            )
                       ) has_active_response_operation,
                       EXISTS(
                         SELECT 1 FROM ordinary_chat_reply_operations obligation_operation
                          WHERE obligation_operation.telegram_account_scope=
                                'AVA_TELETHON_PRIVATE'
                            AND obligation_operation.telegram_chat_id=
                                relationship.telegram_chat_id
                            AND obligation_operation.inbound_sender_telegram_user_id=
                                relationship.telegram_user_id
                            AND (outbound.last_visible_outbound_at IS NULL OR
                                 obligation_operation.inbound_received_at>
                                     outbound.last_visible_outbound_at)
                            AND (
                              jsonb_array_length(COALESCE(
                                obligation_operation.burst_member_obligations,
                                '[]'::jsonb))>0
                              OR COALESCE(
                                obligation_operation.delivery_payload
                                  #>>'{attentionInvestment,meaningfulObligation}',
                                'false')='true'
                            )
                       ) has_unresolved_meaningful_obligation,
                       (SELECT jsonb_agg(history.event ORDER BY history.event_id DESC) FROM (
                          SELECT event_id,jsonb_build_object('eventId',event_id,'observedAt',observed_at,
                              'projection',projection) event
                            FROM conversation_projection_events event
                           WHERE event.creator_profile_id=relationship.creator_profile_id
                             AND event.fanvue_account_id=relationship.fanvue_account_id
                             AND event.telegram_user_id=relationship.telegram_user_id
                             AND event.telegram_chat_id=relationship.telegram_chat_id
                           ORDER BY event_id DESC LIMIT 10) history) projection_history,
                       operation.operation_id,
                       operation.inbound_message_text,operation.burst_obligations,
                       operation.burst_member_obligations,operation.burst_freshness_telegram_message_id,
                       operation.response_payload,operation.media_turn_member_watermark,
                       budget.obligation generation_obligation,budget.candidate_count,
                       budget.provider_attempt_count,budget.correction_started,budget.initial_started,
                       (budget.operation_id IS NOT NULL OR operation.created_at>=policy.installed_at) prospective_generation_eligible,
                       uncertain.operations uncertain_operations,

                       operation.inbound_telegram_message_id operation_inbound_message_id,
                       operation.state operation_state,
                       operation.last_error operation_last_error,
                       operation.next_retry_at,operation.scheduled_delivery_at,
                       operation.preparation_eligible_at,
                       operation.response_payload IS NOT NULL has_response_payload,
                       CASE WHEN operation.conversation_burst_id IS NOT NULL
                         THEN jsonb_array_length(COALESCE(
                           operation.burst_member_obligations,'[]'::jsonb))>0
                         ELSE COALESCE(operation.delivery_payload
                           #>>'{attentionInvestment,meaningfulObligation}','false')='true'
                       END operation_has_meaningful_obligation,
                       operation.response_text pending_reply_preview,
                       operation.generation_attempt_count,operation.max_generation_attempts,
                       operation.send_attempt_count,operation.max_send_attempts,
                       operation.claim_owner,operation.claimed_at,operation.lease_expires_at,
                       operation.outbound_telegram_message_id,
                       operation.generated_at,operation.sending_at,
                       operation.sent_confirmed_at,operation.updated_at operation_updated_at,
                       operation.delivery_payload,
                       delivery_resolution.outcome delivery_resolution_outcome,
                       delivery_resolution.provenance delivery_resolution_provenance,
                       delivery_resolution.resolution_id delivery_resolution_id,
                       acknowledgement.acknowledgement_id,acknowledgement.acknowledged_at,
                       acknowledgement.acknowledged_by,
                       acknowledgement.occurrence_id acknowledged_occurrence_id,
                       uncertainty_ack.items uncertainty_acknowledgements
                  FROM relationship
                  LEFT JOIN telegram_relationship_controls control
                    ON control.creator_profile_id=relationship.creator_profile_id
                   AND control.fanvue_account_id=relationship.fanvue_account_id
                   AND control.telegram_user_id=relationship.telegram_user_id
                  LEFT JOIN inbound ON inbound.telegram_user_id=relationship.telegram_user_id AND inbound.telegram_chat_id=relationship.telegram_chat_id
                  LEFT JOIN outbound ON outbound.telegram_user_id=relationship.telegram_user_id
                  LEFT JOIN LATERAL (
                    SELECT candidate.*, (
                        SELECT max(media.newest_message_freshness_watermark)
                          FROM telegram_inbound_media_turns media
                         WHERE media.creator_profile_id=relationship.creator_profile_id
                           AND media.fanvue_account_id=relationship.fanvue_account_id
                           AND media.telegram_chat_id=candidate.telegram_chat_id
                           AND media.telegram_user_id=candidate.inbound_sender_telegram_user_id
                           AND media.state IN ('OPEN','BOUND')
                           AND candidate.inbound_telegram_message_id=ANY(media.member_telegram_message_ids)
                           AND (media.authoritative_response_operation_id=candidate.operation_id
                                OR media.authoritative_response_operation_id IS NULL)
                           AND candidate.delivery_payload->'current_turn_visual_context'->>'operation_id'=media.media_operation_id::text
                    ) media_turn_member_watermark
                      FROM ordinary_chat_reply_operations candidate
                     WHERE candidate.telegram_account_scope='AVA_TELETHON_PRIVATE'
                       AND candidate.telegram_chat_id=relationship.telegram_chat_id
                       AND candidate.inbound_sender_telegram_user_id=relationship.telegram_user_id
                       AND (outbound.last_visible_outbound_at IS NULL
                            OR candidate.inbound_received_at>outbound.last_visible_outbound_at)
                     ORDER BY COALESCE(candidate.burst_freshness_telegram_message_id,
                                       candidate.inbound_telegram_message_id) DESC,
                       CASE WHEN candidate.burst_role='SURVIVOR' THEN 0 ELSE 1 END,
                       candidate.created_at DESC
                     LIMIT 1
                  ) operation ON TRUE
                  LEFT JOIN ordinary_generation_budgets budget ON budget.operation_id=operation.operation_id
                  LEFT JOIN ordinary_generation_policy policy ON policy.singleton=TRUE
                  LEFT JOIN LATERAL (
                    SELECT jsonb_agg(jsonb_build_object('operationId',u.operation_id,
                        'domain',u.domain,'inboundMessageId',u.inbound_message_id,'reason',u.reason)
                        ORDER BY u.domain,u.operation_id) operations
                    FROM (
                      SELECT o.operation_id,'ORDINARY' domain,o.inbound_telegram_message_id inbound_message_id,o.last_error reason
                        FROM ordinary_chat_reply_operations o
                       WHERE o.telegram_account_scope='AVA_TELETHON_PRIVATE'
                         AND o.telegram_chat_id=relationship.telegram_chat_id
                         AND o.inbound_sender_telegram_user_id=relationship.telegram_user_id AND o.state='SEND_UNCERTAIN'
                         AND NOT EXISTS (SELECT 1 FROM operator_delivery_resolutions resolution
                           WHERE resolution.ordinary_operation_id=o.operation_id
                             AND resolution.outcome='DELIVERED' AND resolution.provenance='OPERATOR_ATTESTED')
                      UNION ALL
                      SELECT m.operation_id,'MANUAL_TEXT',NULL,m.last_error
                        FROM telegram_operator_message_operations m
                       WHERE m.creator_profile_id=relationship.creator_profile_id AND m.fanvue_account_id=relationship.fanvue_account_id
                         AND m.telegram_chat_id=relationship.telegram_chat_id AND m.state='AMBIGUOUS'
                      UNION ALL
                      SELECT m.operation_id,'MANUAL_OFFER',NULL,m.last_error
                        FROM telegram_manual_offer_operations m
                       WHERE m.creator_profile_id=relationship.creator_profile_id AND m.fanvue_account_id=relationship.fanvue_account_id
                         AND m.telegram_chat_id=relationship.telegram_chat_id AND m.state='AMBIGUOUS'
                      UNION ALL
                      SELECT d.operation_id,'SALES',d.inbound_telegram_message_id,d.failure_reason
                        FROM telegram_sales_delivery_operations d
                       WHERE d.creator_profile_id=relationship.creator_profile_id AND d.fanvue_account_id=relationship.fanvue_account_id
                         AND d.telegram_chat_id=relationship.telegram_chat_id AND d.state='AMBIGUOUS'
                      UNION ALL
                      SELECT t.operation_id,'TEASER',t.inbound_telegram_message_id,t.failure_reason
                        FROM telegram_engagement_teaser_delivery_operations t
                       WHERE t.creator_profile_id=relationship.creator_profile_id AND t.fanvue_account_id=relationship.fanvue_account_id
                         AND t.telegram_chat_id=relationship.telegram_chat_id AND t.state='AMBIGUOUS'
                    ) u
                  ) uncertain ON TRUE
                  LEFT JOIN LATERAL (
                    SELECT COALESCE(jsonb_agg(jsonb_build_object('attention_reason',ack.attention_reason,
                        'acknowledged_at',ack.acknowledged_at,'acknowledged_by',ack.acknowledged_by)), '[]'::jsonb) items
                    FROM conversation_attention_acknowledgements ack
                    WHERE ack.creator_profile_id=relationship.creator_profile_id
                      AND ack.fanvue_account_id=relationship.fanvue_account_id
                      AND ack.telegram_user_id=relationship.telegram_user_id
                      AND ack.telegram_chat_id=relationship.telegram_chat_id
                      AND ack.predicate_version='DELIVERY_UNCERTAIN_ACK_V1' AND ack.revoked_at IS NULL
                  ) uncertainty_ack ON TRUE
                  LEFT JOIN public.operator_delivery_resolutions delivery_resolution
                    ON delivery_resolution.ordinary_operation_id=operation.operation_id
                  LEFT JOIN LATERAL (
                    SELECT ack.acknowledgement_id,ack.occurrence_id,ack.acknowledged_at,ack.acknowledged_by
                      FROM conversation_attention_acknowledgements ack
                     WHERE ack.creator_profile_id=relationship.creator_profile_id
                       AND ack.fanvue_account_id=relationship.fanvue_account_id
                       AND ack.telegram_user_id=relationship.telegram_user_id
                       AND ack.triggering_inbound_message_id=inbound.last_inbound_message_id
                       AND ack.predicate_version<>'DELIVERY_UNCERTAIN_ACK_V1'
                       AND ack.revoked_at IS NULL
                     ORDER BY ack.acknowledged_at DESC LIMIT 1
                  ) acknowledgement ON TRUE
            """, (creator_profile_id, fanvue_account_id, creator_profile_id,
                    fanvue_account_id, creator_profile_id, fanvue_account_id,
                    creator_profile_id, fanvue_account_id))
            return {int(row["telegram_user_id"]): dict(row) for row in cursor.fetchall()}

    def record_projection_transition(self, *, creator_profile_id, fanvue_account_id,
                                     telegram_user_id, telegram_chat_id, projection):
        """Append on observed change; no operation, budget or delivery side effects."""
        import hashlib,json
        keys=('operationalStatus','operationalCategory','operationalStatusReason','responseObligation',
              'latestInboundMessageId','causalOperationId','supersededOperationId','automaticRecoveryEligible',
              'candidateBudgetRemaining','candidateCount','responseProviderAttempts','systemIncidentReason',
              'deliveryCertainty','uncertainOperations','operatorAlertActive','attentionOccurrenceId',
              'attentionAcknowledgementId','attentionAcknowledgedAt','attentionAcknowledgedBy',
              'operationState','nextAutomaticAttemptAt')
        payload=json.dumps({key:projection.get(key) for key in keys},sort_keys=True,default=str)
        digest=hashlib.sha256(payload.encode()).hexdigest()
        scope=(creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id)
        with self.connection_factory() as connection,connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))',
                ('conversation-projection:'+':'.join(map(str,scope)),))
            cursor.execute("""INSERT INTO conversation_projection_events
                (creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,projection_hash,projection)
                SELECT %s,%s,%s,%s,%s,%s::jsonb
                WHERE %s IS DISTINCT FROM (SELECT projection_hash FROM conversation_projection_events
                  WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s AND telegram_chat_id=%s
                  ORDER BY event_id DESC LIMIT 1) RETURNING event_id,observed_at""",
                (*scope,digest,payload,digest,*scope))
            row=cursor.fetchone()
        return dict(row) if row else None

    def acknowledge_attention(
        self, *, occurrence_id, creator_profile_id, fanvue_account_id,
        telegram_user_id, telegram_chat_id, triggering_inbound_message_id,
        causal_operation_id, attention_reason, predicate_version,
        acknowledged_by,
    ):
        """Idempotently acknowledge one validated occurrence without touching chat state."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO conversation_attention_acknowledgements(
                acknowledgement_id,occurrence_id,creator_profile_id,fanvue_account_id,
                telegram_account_scope,telegram_chat_id,telegram_user_id,
                triggering_inbound_message_id,causal_operation_id,attention_reason,
                predicate_version,acknowledged_by)
                VALUES (%s,%s,%s,%s,'AVA_TELETHON_PRIVATE',%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(occurrence_id) DO UPDATE SET
                  occurrence_id=EXCLUDED.occurrence_id
                WHERE conversation_attention_acknowledgements.creator_profile_id=EXCLUDED.creator_profile_id
                  AND conversation_attention_acknowledgements.fanvue_account_id=EXCLUDED.fanvue_account_id
                  AND conversation_attention_acknowledgements.telegram_chat_id=EXCLUDED.telegram_chat_id
                  AND conversation_attention_acknowledgements.telegram_user_id=EXCLUDED.telegram_user_id
                  AND conversation_attention_acknowledgements.triggering_inbound_message_id=EXCLUDED.triggering_inbound_message_id
                  AND conversation_attention_acknowledgements.attention_reason=EXCLUDED.attention_reason
                RETURNING *""", (
                uuid4(), occurrence_id, creator_profile_id, fanvue_account_id,
                telegram_chat_id, telegram_user_id, triggering_inbound_message_id,
                causal_operation_id, attention_reason, predicate_version,
                acknowledged_by,
            ))
            row = cursor.fetchone()
        return dict(row) if row else None

    def messages(self, *, creator_profile_id: int, fanvue_account_id: int,
                 telegram_user_id: int, before_occurred_at=None,
                 before_event_key=None, limit=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH events AS (
                  SELECT 'telegram:'||o.telegram_chat_id||':'||o.inbound_telegram_message_id event_key,
                         'CUSTOMER' direction,o.inbound_message_text content,
                         o.inbound_received_at occurred_at,o.inbound_telegram_message_id telegram_message_id,
                         'ORDINARY_CHAT' message_type,1 priority,NULL::uuid purchase_intent_id
                    FROM ordinary_chat_reply_operations o
                   WHERE o.inbound_sender_telegram_user_id=%s
                     AND o.telegram_account_scope='AVA_TELETHON_PRIVATE'
                     AND o.inbound_received_at IS NOT NULL AND BTRIM(COALESCE(o.inbound_message_text,''))<>''
                  UNION ALL
                  SELECT 'telegram:'||i.telegram_chat_id||':'||i.telegram_message_id,
                         'CUSTOMER',CASE WHEN BTRIM(i.customer_text)<>'' THEN i.customer_text
                           WHEN i.has_media THEN '[Media received]' ELSE '' END,
                         i.received_at,i.telegram_message_id,'INBOUND_MEDIA',2,NULL::uuid
                    FROM telegram_private_inbound_messages i
                   WHERE i.creator_profile_id=%s AND i.fanvue_account_id=%s
                     AND i.telegram_user_id=%s
                     AND (BTRIM(i.customer_text)<>'' OR i.has_media=TRUE)
                  UNION ALL
                  SELECT COALESCE('telegram:'||(cm.raw_payload->>'telegram_chat_id')||':'||
                           (cm.raw_payload->>'telegram_message_id'),'chat-message:'||cm.id),
                         CASE WHEN cm.direction='inbound' THEN 'CUSTOMER' ELSE 'AVA' END,
                         cm.text,cm.sent_at,NULLIF(cm.raw_payload->>'telegram_message_id','')::bigint,
                         'CHAT_MESSAGE',3,NULL::uuid
                    FROM chat_messages cm JOIN chat_threads thread ON thread.id=cm.thread_id
                    JOIN telegram_identity_map m ON m.fanvue_account_id=thread.fanvue_account_id
                     AND m.local_fanvue_user_id=thread.fanvue_user_id AND m.is_active=TRUE
                     AND m.verification_status='VERIFIED'
                   WHERE m.telegram_user_id=%s AND thread.fanvue_account_id=%s
                     AND cm.raw_payload->>'provider'='TELEGRAM'
                     AND ((cm.direction='inbound' AND cm.sender_type='user') OR
                          (cm.direction='outbound' AND cm.sender_type='bot'))
                  UNION ALL
                  SELECT COALESCE('telegram:'||o.telegram_chat_id||':'||o.outbound_telegram_message_id,
                                  'correlation:'||o.correlation_id),
                         'AVA',o.response_text,o.sent_confirmed_at,o.outbound_telegram_message_id,
                         'ORDINARY_CHAT',1,NULL::uuid
                    FROM ordinary_chat_reply_operations o
                   WHERE o.inbound_sender_telegram_user_id=%s
                     AND o.telegram_account_scope='AVA_TELETHON_PRIVATE'
                     AND o.state='SENT_CONFIRMED' AND o.sent_confirmed_at IS NOT NULL
                     AND BTRIM(COALESCE(o.response_text,''))<>''
                  UNION ALL
                  SELECT 'telegram:'||o.telegram_chat_id||':'||o.outbound_telegram_message_id,
                         'AVA',o.message_text,o.confirmed_at,o.outbound_telegram_message_id,
                         'HUMAN_OPERATOR',4,NULL::uuid
                    FROM telegram_operator_message_operations o
                   WHERE o.creator_profile_id=%s AND o.fanvue_account_id=%s
                     AND o.telegram_user_id=%s AND o.state='CONFIRMED'
                     AND o.confirmed_at IS NOT NULL
                  UNION ALL
                  SELECT COALESCE('telegram:'||d.telegram_chat_id||':'||d.outbound_telegram_message_id,
                                  'correlation:'||d.correlation_id),
                         'AVA',d.response_text,d.confirmed_at,d.outbound_telegram_message_id,
                         'COMMERCIAL_OFFER',1,d.purchase_intent_id
                    FROM telegram_sales_delivery_operations d
                    JOIN purchase_intents m ON m.purchase_intent_id=d.purchase_intent_id
                     AND m.creator_profile_id=d.creator_profile_id AND m.fanvue_account_id=d.fanvue_account_id
                     AND m.telegram_chat_id=d.telegram_chat_id
                   WHERE d.creator_profile_id=%s AND d.fanvue_account_id=%s
                     AND m.telegram_user_id=%s AND d.state='CONFIRMED' AND d.confirmed_at IS NOT NULL
                ), deduped AS (
                  SELECT *,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY priority,occurred_at) rank
                    FROM events
                ) SELECT event_key,direction,content,occurred_at,telegram_message_id,
                         message_type,purchase_intent_id
                    FROM deduped WHERE rank=1
                     AND (%s::timestamptz IS NULL OR
                          (occurred_at,event_key)<(%s::timestamptz,%s::text))
                   ORDER BY occurred_at DESC,event_key DESC
                   LIMIT COALESCE(%s,2147483647)
            """, (telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id, telegram_user_id, fanvue_account_id,
                  telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id, before_occurred_at, before_occurred_at,
                  before_event_key, limit))
            return [dict(row) for row in reversed(cursor.fetchall())]

    def relationship_exists(self, *, creator_profile_id: int,
                            fanvue_account_id: int, telegram_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT EXISTS(
                SELECT 1 FROM telegram_sales_prospects
                 WHERE creator_profile_id=%s AND fanvue_account_id=%s
                   AND telegram_user_id=%s
                UNION ALL
                SELECT 1 FROM telegram_identity_map
                 WHERE fanvue_account_id=%s AND telegram_user_id=%s
                   AND is_active=TRUE AND verification_status='VERIFIED') AS found""",
                (creator_profile_id, fanvue_account_id, telegram_user_id,
                 fanvue_account_id, telegram_user_id))
            return bool(cursor.fetchone()["found"])

    def control_context(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH relationship AS (
                    SELECT %s::BIGINT AS telegram_user_id
                     WHERE EXISTS (
                        SELECT 1 FROM telegram_sales_prospects prospect
                         WHERE prospect.creator_profile_id=%s
                           AND prospect.fanvue_account_id=%s
                           AND prospect.telegram_user_id=%s)
                        OR EXISTS (
                        SELECT 1 FROM telegram_identity_map mapping
                         WHERE mapping.fanvue_account_id=%s
                           AND mapping.telegram_user_id=%s
                           AND mapping.is_active=TRUE
                           AND mapping.verification_status='VERIFIED')
                )
                SELECT COALESCE(prospect.telegram_chat_id,mapping.telegram_chat_id,
                                relationship.telegram_user_id) telegram_chat_id,
                       mapping.id telegram_identity_mapping_id,
                       mapping.local_fanvue_user_id,mapping.external_fanvue_user_uuid,
                       thread.id conversation_thread_id,
                       (SELECT inbound_telegram_message_id FROM ordinary_chat_reply_operations inbound
                         WHERE inbound.inbound_sender_telegram_user_id=relationship.telegram_user_id
                           AND inbound.inbound_received_at IS NOT NULL
                         ORDER BY inbound.inbound_received_at DESC LIMIT 1) latest_inbound_telegram_message_id,
                       (SELECT inbound.telegram_account_scope FROM ordinary_chat_reply_operations inbound
                         WHERE inbound.inbound_sender_telegram_user_id=relationship.telegram_user_id
                           AND inbound.telegram_chat_id=COALESCE(prospect.telegram_chat_id,
                               mapping.telegram_chat_id,relationship.telegram_user_id)
                           AND inbound.inbound_received_at IS NOT NULL
                         ORDER BY inbound.inbound_received_at DESC LIMIT 1) telegram_account_scope,
                       EXISTS(SELECT 1 FROM purchase_intents intent
                         WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                           AND intent.telegram_user_id=%s
                           AND intent.status IN ('CREATED','PRESENTED','CLICKED')) active_purchase_intent,
                       EXISTS(SELECT 1 FROM sales_sessions session
                         WHERE session.creator_profile_id=%s AND session.fanvue_account_id=%s
                           AND session.fanvue_user_id=mapping.local_fanvue_user_id
                           AND session.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')) active_sales_session
                  FROM relationship
                  LEFT JOIN telegram_sales_prospects prospect
                    ON prospect.creator_profile_id=%s
                   AND prospect.fanvue_account_id=%s
                   AND prospect.telegram_user_id=relationship.telegram_user_id
                  LEFT JOIN telegram_identity_map mapping
                    ON mapping.fanvue_account_id=%s
                   AND mapping.telegram_user_id=relationship.telegram_user_id
                   AND mapping.is_active=TRUE AND mapping.verification_status='VERIFIED'
                  LEFT JOIN chat_threads thread ON thread.fanvue_account_id=mapping.fanvue_account_id
                   AND thread.fanvue_user_id=mapping.local_fanvue_user_id
                 LIMIT 1""",
                (telegram_user_id, creator_profile_id, fanvue_account_id,
                 telegram_user_id, fanvue_account_id, telegram_user_id,
                 creator_profile_id, fanvue_account_id, telegram_user_id,
                 creator_profile_id, fanvue_account_id,
                 creator_profile_id, fanvue_account_id, fanvue_account_id))
            row=cursor.fetchone()
        return dict(row) if row else None

    def intelligence(self, *, creator_profile_id: int, fanvue_account_id: int,
                     telegram_user_id: int, customer_commerce_profile_id=None,
                     local_fanvue_user_id=None):
        """Read the durable records needed by the operator-safe drawer."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.local_fanvue_user_id,mapping.telegram_chat_id,
                          profile.customer_commerce_profile_id,
                          profile.average_order_value_minor,
                          profile.largest_purchase_minor,profile.last_purchase_at
                     FROM public.telegram_identity_map mapping
                     LEFT JOIN public.customer_commerce_profiles profile
                       ON profile.creator_profile_id=%s
                      AND profile.fanvue_account_id=mapping.fanvue_account_id
                      AND profile.external_fanvue_user_uuid=
                          mapping.external_fanvue_user_uuid
                    WHERE mapping.fanvue_account_id=%s
                      AND mapping.telegram_user_id=%s
                      AND mapping.is_active=TRUE
                      AND mapping.verification_status='VERIFIED'
                    LIMIT 1""",
                (creator_profile_id, fanvue_account_id, telegram_user_id),
            )
            identity = dict(cursor.fetchone() or {})
            customer_commerce_profile_id = (
                customer_commerce_profile_id
                or identity.get("customer_commerce_profile_id")
            )
            local_fanvue_user_id = (
                local_fanvue_user_id or identity.get("local_fanvue_user_id")
            )
            cursor.execute(
                """SELECT intent.purchase_intent_id,intent.status,intent.presented_at,
                          intent.purchased_at,intent.expected_price_minor,
                          offering.title,offering.offering_type,
                          EXISTS(SELECT 1 FROM public.sales_session_purchase_intents link
                                  WHERE link.purchase_intent_id=intent.purchase_intent_id)
                              AS session_offering,
                          EXISTS(
                            SELECT 1 FROM public.telegram_sales_delivery_operations delivery
                             WHERE delivery.purchase_intent_id=intent.purchase_intent_id
                               AND delivery.state='CONFIRMED'
                               AND delivery.confirmed_at IS NOT NULL
                          ) AS confirmed_delivery
                     FROM public.purchase_intents intent
                     JOIN public.commercial_offerings offering
                       ON offering.offering_id=intent.commercial_offering_id
                    WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                      AND intent.telegram_user_id=%s
                    ORDER BY intent.presented_at DESC NULLS LAST,intent.created_at DESC""",
                (creator_profile_id, fanvue_account_id, telegram_user_id),
            )
            intents = [dict(row) for row in cursor.fetchall()]

            purchases = []
            if customer_commerce_profile_id is not None:
                cursor.execute(
                    """SELECT transaction.payment_timestamp,transaction.gross_minor,
                              offering.title,offering.offering_type,
                              intent.purchase_intent_id,
                              EXISTS(SELECT 1 FROM public.sales_session_purchase_intents link
                                      WHERE link.purchase_intent_id=intent.purchase_intent_id)
                                  AS session_offering,
                              EXISTS(SELECT 1 FROM public.provider_purchase_asset_ownership own
                                      WHERE own.creator_profile_id=%s
                                        AND own.fanvue_account_id=transaction.fanvue_account_id
                                        AND own.provider_transaction_id=intent.provider_payment_id)
                                  AS ownership_confirmed
                         FROM public.customer_commerce_transactions transaction
                         LEFT JOIN public.purchase_intents intent
                           ON intent.fanvue_account_id=transaction.fanvue_account_id
                          AND intent.provider_transaction_order_id=transaction.transaction_order_id
                         LEFT JOIN public.commercial_offerings offering
                           ON offering.offering_id=intent.commercial_offering_id
                        WHERE transaction.customer_commerce_profile_id=%s
                          AND transaction.fanvue_account_id=%s
                          AND LOWER(transaction.payment_status) IN
                              ('succeeded','successful','paid','completed')
                        ORDER BY transaction.payment_timestamp DESC,
                                 transaction.customer_commerce_transaction_id DESC""",
                    (creator_profile_id, customer_commerce_profile_id, fanvue_account_id),
                )
                purchases = [dict(row) for row in cursor.fetchall()]

            session = None
            if local_fanvue_user_id is not None:
                cursor.execute(
                    """SELECT state,progression_stage,commercial_foundation_type,
                              last_activity_at
                         FROM public.sales_sessions
                        WHERE creator_profile_id=%s AND fanvue_account_id=%s
                          AND fanvue_user_id=%s
                          AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')
                        ORDER BY last_activity_at DESC LIMIT 1""",
                    (creator_profile_id, fanvue_account_id, local_fanvue_user_id),
                )
                row = cursor.fetchone()
                session = dict(row) if row else None

            cursor.execute(
                """SELECT preference_state,relationship_state,telegram_chat_id
                     FROM public.telegram_sales_prospects
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s""",
                (creator_profile_id, fanvue_account_id, telegram_user_id),
            )
            row = cursor.fetchone()
            prospect = dict(row) if row else {}
            telegram_chat_id = int(prospect.get("telegram_chat_id")
                                   or identity.get("telegram_chat_id") or telegram_user_id)
            cursor.execute("""SELECT response_payload->'diagnostic_metadata' AS diagnostics,
                       inbound_telegram_message_id AS diagnostic_inbound_message_id,
                       inbound_received_at AS diagnostic_inbound_received_at,
                       operation_id AS diagnostic_operation_id
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND inbound_sender_telegram_user_id=%s
                  AND telegram_chat_id=%s AND state='SENT_CONFIRMED'
                  AND response_payload->'diagnostic_metadata' IS NOT NULL
                ORDER BY inbound_received_at DESC LIMIT 1""",
                (telegram_user_id, telegram_chat_id))
            row = cursor.fetchone()
            latest_diagnostics = dict(row["diagnostics"] or {}) if row else {}
            diagnostic_source = ({
                "inbound_telegram_message_id": row["diagnostic_inbound_message_id"],
                "inbound_received_at": row["diagnostic_inbound_received_at"],
                "operation_id": row["diagnostic_operation_id"],
            } if row else {})
            latest_value_attention = dict(
                latest_diagnostics.get("customer_value_attention") or {})
            last_presented_at = next((item.get("presented_at") for item in intents
                                      if item.get("presented_at") is not None
                                      and item.get("confirmed_delivery") is True), None)
            messages_since_last_offer = None
            if last_presented_at is not None:
                cursor.execute("""SELECT count(*)::int AS count
                    FROM telegram_private_inbound_messages
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s AND telegram_chat_id=%s
                      AND received_at>%s""", (creator_profile_id, fanvue_account_id,
                    telegram_user_id, telegram_chat_id, last_presented_at))
                messages_since_last_offer = int(cursor.fetchone()["count"])
            cursor.execute(
                "SELECT to_regclass('public.active_offer_follow_through_events') AS present")
            follow_table_available = cursor.fetchone()["present"] is not None
            follow_through = {"available": follow_table_available}
            if follow_table_available:
                cursor.execute("""SELECT
                    bool_or(e.delivery_state='SENT_CONFIRMED') AS confirmed_nudge,
                    bool_or(e.delivery_state='AUTHORIZED'
                            AND p.status IN ('PRESENTED','CLICKED')
                            AND p.purchased_at IS NULL) AS eligible,
                    bool_or(delivery_state='SENT_CONFIRMED'
                            AND customer_response_observed_at IS NOT NULL
                            AND purchase_observed_at IS NULL
                            AND p.purchased_at IS NULL) AS backoff
                  FROM active_offer_follow_through_events e
                  JOIN purchase_intents p USING(purchase_intent_id)
                 WHERE e.creator_profile_id=%s AND e.fanvue_account_id=%s
                   AND e.telegram_user_id=%s AND e.telegram_chat_id=%s""",
                    (creator_profile_id, fanvue_account_id,
                     telegram_user_id, telegram_chat_id))
                follow_through.update(dict(cursor.fetchone() or {}))
            cursor.execute("""SELECT operation.delivery_payload->'postNudgeConversationPolicy' AS policy
                FROM ordinary_chat_reply_operations operation
                JOIN telegram_private_inbound_messages inbound
                  ON inbound.telegram_account_scope=operation.telegram_account_scope
                 AND inbound.telegram_chat_id=operation.telegram_chat_id
                 AND inbound.telegram_message_id=operation.inbound_telegram_message_id
                WHERE inbound.creator_profile_id=%s AND inbound.fanvue_account_id=%s
                  AND operation.inbound_sender_telegram_user_id=%s AND operation.telegram_chat_id=%s
                  AND operation.delivery_payload ? 'postNudgeConversationPolicy'
                ORDER BY operation.inbound_received_at DESC LIMIT 1""", (
                    creator_profile_id, fanvue_account_id,
                    telegram_user_id, telegram_chat_id))
            policy_row = cursor.fetchone()
            conversation_policy = dict((policy_row or {}).get("policy") or {})
            if conversation_policy:
                follow_through["conversation_policy"] = conversation_policy
        return {"profile": identity, "intents": intents, "purchases": purchases,
                "active_session": session, "prospect": prospect,
                "latest_value_attention": latest_value_attention,
                "latest_sales_diagnostics": latest_diagnostics,
                "latest_sales_diagnostic_source": diagnostic_source,
                "messages_since_last_offer": messages_since_last_offer,
                "follow_through": follow_through}
