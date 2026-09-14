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
                    FROM telegram_sales_delivery_operations d JOIN telegram_identity_map m
                      ON m.fanvue_account_id=d.fanvue_account_id
                     AND m.local_fanvue_user_id=d.fanvue_user_id AND m.is_active=TRUE
                     AND m.verification_status='VERIFIED'
                   WHERE d.creator_profile_id=%s AND d.fanvue_account_id=%s
                     AND d.state='CONFIRMED' AND d.confirmed_at IS NOT NULL
                ) SELECT DISTINCT ON (telegram_user_id) telegram_user_id,content,occurred_at,direction,event_key
                    FROM events WHERE BTRIM(COALESCE(content,''))<>''
                   ORDER BY telegram_user_id,occurred_at DESC,event_key DESC
            """, (creator_profile_id,fanvue_account_id,creator_profile_id,
                  fanvue_account_id,fanvue_account_id,creator_profile_id,
                  fanvue_account_id,creator_profile_id,fanvue_account_id))
            return {int(row["telegram_user_id"]):dict(row) for row in cursor.fetchall()}

    def inbox_state(self, *, creator_profile_id: int, fanvue_account_id: int):
        """Return actionable inbox state in one account-scoped query."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                WITH inbound AS (
                  SELECT inbound_sender_telegram_user_id telegram_user_id,
                         MAX(inbound_received_at) last_customer_inbound_at,
                         MAX(inbound_telegram_message_id) last_inbound_message_id
                    FROM ordinary_chat_reply_operations
                   WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                     AND inbound_received_at IS NOT NULL
                   GROUP BY inbound_sender_telegram_user_id
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
                        JOIN telegram_identity_map mapping
                          ON mapping.fanvue_account_id=delivery.fanvue_account_id
                         AND mapping.local_fanvue_user_id=delivery.fanvue_user_id
                         AND mapping.is_active=TRUE AND mapping.verification_status='VERIFIED'
                       WHERE delivery.creator_profile_id=%s AND delivery.fanvue_account_id=%s
                         AND delivery.state='CONFIRMED'
                         AND delivery.outbound_telegram_message_id IS NOT NULL
                    ) visible GROUP BY telegram_user_id
                )
                SELECT prospect.telegram_user_id,prospect.telegram_chat_id,
                       COALESCE(control.mode,'AVA_AUTO') control_mode,
                       COALESCE(control.communication_disposition,'ACTIVE') communication_disposition,
                       (SELECT value_override.classification
                          FROM telegram_relationship_value_overrides value_override
                         WHERE value_override.creator_profile_id=prospect.creator_profile_id
                           AND value_override.fanvue_account_id=prospect.fanvue_account_id
                           AND value_override.telegram_user_id=prospect.telegram_user_id
                           AND value_override.telegram_chat_id=prospect.telegram_chat_id
                           AND value_override.removed_at IS NULL LIMIT 1
                       ) operator_classification,
                       (SELECT tier.market_tier
                          FROM telegram_relationship_market_tiers tier
                         WHERE tier.creator_profile_id=prospect.creator_profile_id
                           AND tier.fanvue_account_id=prospect.fanvue_account_id
                           AND tier.telegram_user_id=prospect.telegram_user_id
                           AND tier.telegram_chat_id=prospect.telegram_chat_id
                           AND tier.removed_at IS NULL LIMIT 1
                       ) market_tier,
                       inbound.last_customer_inbound_at,inbound.last_inbound_message_id,
                       outbound.last_visible_outbound_at,NOW() database_now,
                       operation.operation_id,operation.state operation_state,
                       operation.last_error operation_last_error,
                       operation.next_retry_at,operation.response_payload IS NOT NULL has_response_payload,
                       operation.generation_attempt_count,operation.max_generation_attempts,
                       operation.send_attempt_count,operation.max_send_attempts,
                       operation.claim_owner,operation.claimed_at,operation.lease_expires_at,
                       operation.outbound_telegram_message_id,
                       operation.delivery_payload,
                       acknowledgement.acknowledged_at,
                       acknowledgement.acknowledged_by,
                       acknowledgement.occurrence_id acknowledged_occurrence_id
                  FROM telegram_sales_prospects prospect
                  LEFT JOIN telegram_relationship_controls control
                    ON control.creator_profile_id=prospect.creator_profile_id
                   AND control.fanvue_account_id=prospect.fanvue_account_id
                   AND control.telegram_user_id=prospect.telegram_user_id
                  LEFT JOIN inbound ON inbound.telegram_user_id=prospect.telegram_user_id
                  LEFT JOIN outbound ON outbound.telegram_user_id=prospect.telegram_user_id
                  LEFT JOIN LATERAL (
                    SELECT candidate.*
                      FROM ordinary_chat_reply_operations candidate
                     WHERE candidate.telegram_account_scope='AVA_TELETHON_PRIVATE'
                       AND candidate.telegram_chat_id=prospect.telegram_chat_id
                       AND candidate.inbound_sender_telegram_user_id=prospect.telegram_user_id
                       AND (outbound.last_visible_outbound_at IS NULL
                            OR candidate.inbound_received_at>outbound.last_visible_outbound_at)
                     ORDER BY
                       CASE
                         WHEN candidate.state IN ('RETRYABLE','PENDING_GENERATION','GENERATING','GENERATED','SENDING') THEN 0
                         WHEN candidate.state IN ('SEND_UNCERTAIN','TERMINAL_FAILED') THEN 1
                         WHEN candidate.state='SUPPRESSED' AND (
                           candidate.last_error LIKE 'quality_corrective_retry_exhausted:%%'
                           OR candidate.last_error LIKE 'quality_blocked_before_delivery:CUSTOMER_QUESTION_UNANSWERED%%'
                           OR candidate.last_error LIKE 'quality_blocked_before_delivery:TURN_OBLIGATIONS_UNSATISFIED%%'
                           OR candidate.last_error LIKE 'quality_blocked_before_delivery:%%CUSTOMER_QUESTION_UNANSWERED%%'
                           OR candidate.last_error LIKE 'quality_blocked_before_delivery:%%TURN_OBLIGATIONS_UNSATISFIED%%'
                         ) THEN 1 ELSE 2 END,
                       candidate.inbound_telegram_message_id DESC
                     LIMIT 1
                  ) operation ON TRUE
                  LEFT JOIN LATERAL (
                    SELECT ack.occurrence_id,ack.acknowledged_at,ack.acknowledged_by
                      FROM conversation_attention_acknowledgements ack
                     WHERE ack.creator_profile_id=prospect.creator_profile_id
                       AND ack.fanvue_account_id=prospect.fanvue_account_id
                       AND ack.telegram_user_id=prospect.telegram_user_id
                       AND ack.triggering_inbound_message_id=inbound.last_inbound_message_id
                       AND ack.revoked_at IS NULL
                     ORDER BY ack.acknowledged_at DESC LIMIT 1
                  ) acknowledgement ON TRUE
                 WHERE prospect.creator_profile_id=%s AND prospect.fanvue_account_id=%s
            """, (creator_profile_id, fanvue_account_id, creator_profile_id,
                    fanvue_account_id, creator_profile_id, fanvue_account_id))
            return {int(row["telegram_user_id"]): dict(row) for row in cursor.fetchall()}

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
                 telegram_user_id: int):
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
                    JOIN telegram_identity_map m ON m.fanvue_account_id=d.fanvue_account_id
                     AND m.local_fanvue_user_id=d.fanvue_user_id AND m.is_active=TRUE
                     AND m.verification_status='VERIFIED'
                   WHERE d.creator_profile_id=%s AND d.fanvue_account_id=%s
                     AND m.telegram_user_id=%s AND d.state='CONFIRMED' AND d.confirmed_at IS NOT NULL
                ), deduped AS (
                  SELECT *,ROW_NUMBER() OVER(PARTITION BY event_key ORDER BY priority,occurred_at) rank
                    FROM events
                ) SELECT event_key,direction,content,occurred_at,telegram_message_id,
                         message_type,purchase_intent_id
                    FROM deduped WHERE rank=1
                   ORDER BY occurred_at,event_key
            """, (telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id, telegram_user_id, fanvue_account_id,
                  telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id, creator_profile_id, fanvue_account_id,
                  telegram_user_id))
            return [dict(row) for row in cursor.fetchall()]

    def control_context(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT prospect.telegram_chat_id,mapping.id telegram_identity_mapping_id,
                       mapping.local_fanvue_user_id,mapping.external_fanvue_user_uuid,
                       thread.id conversation_thread_id,
                       (SELECT inbound_telegram_message_id FROM ordinary_chat_reply_operations inbound
                         WHERE inbound.inbound_sender_telegram_user_id=prospect.telegram_user_id
                           AND inbound.telegram_chat_id=prospect.telegram_chat_id
                           AND inbound.inbound_received_at IS NOT NULL
                         ORDER BY inbound.inbound_received_at DESC LIMIT 1) latest_inbound_telegram_message_id,
                       EXISTS(SELECT 1 FROM purchase_intents intent
                         WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                           AND intent.telegram_user_id=%s
                           AND intent.status IN ('CREATED','PRESENTED','CLICKED')) active_purchase_intent,
                       EXISTS(SELECT 1 FROM sales_sessions session
                         WHERE session.creator_profile_id=%s AND session.fanvue_account_id=%s
                           AND session.fanvue_user_id=mapping.local_fanvue_user_id
                           AND session.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')) active_sales_session
                  FROM telegram_sales_prospects prospect
                  LEFT JOIN telegram_identity_map mapping
                    ON mapping.fanvue_account_id=prospect.fanvue_account_id
                   AND mapping.telegram_user_id=prospect.telegram_user_id
                   AND mapping.is_active=TRUE AND mapping.verification_status='VERIFIED'
                  LEFT JOIN chat_threads thread ON thread.fanvue_account_id=mapping.fanvue_account_id
                   AND thread.fanvue_user_id=mapping.local_fanvue_user_id
                 WHERE prospect.creator_profile_id=%s AND prospect.fanvue_account_id=%s
                   AND prospect.telegram_user_id=%s LIMIT 1""",
                (creator_profile_id,fanvue_account_id,telegram_user_id,
                 creator_profile_id,fanvue_account_id,
                 creator_profile_id,fanvue_account_id,telegram_user_id))
            row=cursor.fetchone()
        return dict(row) if row else None

    def intelligence(self, *, creator_profile_id: int, fanvue_account_id: int,
                     telegram_user_id: int, customer_commerce_profile_id=None,
                     local_fanvue_user_id=None):
        """Read the durable records needed by the operator-safe drawer."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT mapping.local_fanvue_user_id,
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
                """SELECT preference_state,relationship_state
                     FROM public.telegram_sales_prospects
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND telegram_user_id=%s""",
                (creator_profile_id, fanvue_account_id, telegram_user_id),
            )
            row = cursor.fetchone()
            prospect = dict(row) if row else {}
            cursor.execute("""SELECT response_payload->'diagnostic_metadata'
                                      ->'customer_value_attention' AS value_attention
                FROM ordinary_chat_reply_operations
                WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND inbound_sender_telegram_user_id=%s
                  AND response_payload->'diagnostic_metadata'
                        ->'customer_value_attention'->>'schemaVersion'
                        ='customer_value_attention_v1'
                ORDER BY inbound_received_at DESC LIMIT 1""", (telegram_user_id,))
            row = cursor.fetchone()
            latest_value_attention = dict(row["value_attention"] or {}) if row else {}
        return {"profile": identity, "intents": intents, "purchases": purchases,
                "active_session": session, "prospect": prospect,
                "latest_value_attention": latest_value_attention}
