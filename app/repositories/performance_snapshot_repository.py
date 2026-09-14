"""PostgreSQL read authority for performance snapshot base records."""

from __future__ import annotations

from app.database import get_db_connection


class PerformanceSnapshotRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def business_customer_contexts(self, *, creator_profile_id: int, fanvue_account_id: int):
        """One bounded identity/commerce projection shared by every drill-down row."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""
                SELECT profile.customer_commerce_profile_id,profile.external_fanvue_user_uuid,
                       profile.display_name provider_display_name,profile.handle provider_handle,
                       profile.profile_state,profile.lifetime_gross_minor,profile.purchase_count,
                       profile.first_purchase_at,profile.last_purchase_at,
                       customer.id local_fanvue_user_id,customer.display_name canonical_display_name,
                       customer.username canonical_username,mapping.telegram_user_id,
                       observation.telegram_chat_id,
                       EXISTS(SELECT 1 FROM telegram_sales_prospects prospect
                         WHERE prospect.creator_profile_id=%s AND prospect.fanvue_account_id=%s
                           AND prospect.telegram_user_id=mapping.telegram_user_id) has_conversation
                  FROM customer_commerce_profiles profile
                  LEFT JOIN fanvue_users customer ON customer.fanvue_account_id=profile.fanvue_account_id
                   AND customer.fanvue_user_uuid=profile.external_fanvue_user_uuid
                  LEFT JOIN telegram_identity_map mapping ON mapping.fanvue_account_id=profile.fanvue_account_id
                   AND mapping.external_fanvue_user_uuid=profile.external_fanvue_user_uuid
                   AND mapping.is_active AND mapping.verification_status='VERIFIED'
                  LEFT JOIN telegram_identity_observations observation
                    ON observation.telegram_user_id=mapping.telegram_user_id
                 WHERE profile.creator_profile_id=%s AND profile.fanvue_account_id=%s
            """,(creator_profile_id,fanvue_account_id,creator_profile_id,fanvue_account_id))
            return [dict(row) for row in cursor.fetchall()]

    def people(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH ids AS (
                  SELECT telegram_user_id FROM telegram_sales_prospects
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  UNION SELECT telegram_user_id FROM telegram_identity_map
                   WHERE fanvue_account_id=%s
                )
                SELECT ids.telegram_user_id, observation.username,
                       observation.display_name, prospect.telegram_sales_prospect_id,
                       prospect.relationship_state, prospect.graduated_mapping_id,
                       mapping.id AS mapping_id, mapping.verification_status,
                       mapping.is_active AS mapping_active,
                       mapping.local_fanvue_user_id,
                       mapping.external_fanvue_user_uuid,
                       profile.customer_commerce_profile_id, profile.profile_state,
                       profile.lifetime_gross_minor, profile.purchase_count
                  FROM ids
                  LEFT JOIN telegram_identity_observations observation USING(telegram_user_id)
                  LEFT JOIN telegram_sales_prospects prospect
                    ON prospect.telegram_user_id=ids.telegram_user_id
                   AND prospect.creator_profile_id=%s AND prospect.fanvue_account_id=%s
                  LEFT JOIN telegram_identity_map mapping
                    ON mapping.telegram_user_id=ids.telegram_user_id
                   AND mapping.fanvue_account_id=%s AND mapping.is_active=TRUE
                  LEFT JOIN customer_commerce_profiles profile
                    ON mapping.verification_status='VERIFIED'
                   AND profile.creator_profile_id=%s
                   AND profile.fanvue_account_id=%s
                   AND profile.external_fanvue_user_uuid=mapping.external_fanvue_user_uuid
                 ORDER BY ids.telegram_user_id
                """,
                (creator_profile_id, fanvue_account_id, fanvue_account_id,
                 creator_profile_id, fanvue_account_id, fanvue_account_id,
                 creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def inbound_events(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH scoped AS (
                  SELECT telegram_user_id FROM telegram_sales_prospects
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  UNION SELECT telegram_user_id FROM telegram_identity_map
                   WHERE fanvue_account_id=%s
                ), events AS (
                  SELECT o.inbound_sender_telegram_user_id AS telegram_user_id,
                         'telegram:'||o.telegram_chat_id||':'||o.inbound_telegram_message_id AS event_key,
                         o.inbound_received_at AS occurred_at, 'ordinary_operation' AS source
                    FROM ordinary_chat_reply_operations o JOIN scoped s
                      ON s.telegram_user_id=o.inbound_sender_telegram_user_id
                   WHERE o.inbound_received_at IS NOT NULL
                  UNION ALL
                  SELECT m.telegram_user_id,
                         'telegram:'||(cm.raw_payload->>'telegram_chat_id')||':'||
                           (cm.raw_payload->>'telegram_message_id') AS event_key,
                         cm.sent_at, 'chat_message'
                    FROM chat_messages cm
                    JOIN chat_threads thread ON thread.id=cm.thread_id
                    JOIN telegram_identity_map m
                      ON m.fanvue_account_id=thread.fanvue_account_id
                     AND m.local_fanvue_user_id=thread.fanvue_user_id
                     AND m.is_active=TRUE AND m.verification_status='VERIFIED'
                   WHERE cm.direction='inbound' AND cm.sender_type='user'
                     AND cm.raw_payload->>'provider'='TELEGRAM'
                     AND cm.raw_payload->>'telegram_message_id' IS NOT NULL
                     AND thread.fanvue_account_id=%s
                ) SELECT * FROM events ORDER BY occurred_at,event_key
                """,
                (creator_profile_id, fanvue_account_id, fanvue_account_id,
                 fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def ava_events(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH scoped AS (
                  SELECT telegram_user_id FROM telegram_sales_prospects
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  UNION SELECT telegram_user_id FROM telegram_identity_map
                   WHERE fanvue_account_id=%s
                ), events AS (
                  SELECT o.inbound_sender_telegram_user_id AS telegram_user_id,
                         COALESCE('telegram:'||o.telegram_chat_id||':'||o.outbound_telegram_message_id,
                                  'correlation:'||o.correlation_id) AS event_key,
                         o.sent_confirmed_at AS occurred_at, 'ordinary_operation' AS source
                    FROM ordinary_chat_reply_operations o JOIN scoped s
                      ON s.telegram_user_id=o.inbound_sender_telegram_user_id
                   WHERE o.state='SENT_CONFIRMED' AND o.sent_confirmed_at IS NOT NULL
                  UNION ALL
                  SELECT m.telegram_user_id,
                         COALESCE('telegram:'||(cm.raw_payload->>'telegram_chat_id')||':'||
                                  (cm.raw_payload->>'telegram_message_id'),
                                  'chat-message:'||cm.id),
                         cm.sent_at, 'chat_message'
                    FROM chat_messages cm JOIN chat_threads thread ON thread.id=cm.thread_id
                    JOIN telegram_identity_map m ON m.fanvue_account_id=thread.fanvue_account_id
                     AND m.local_fanvue_user_id=thread.fanvue_user_id
                     AND m.is_active=TRUE AND m.verification_status='VERIFIED'
                   WHERE cm.direction='outbound' AND cm.sender_type='bot'
                     AND cm.raw_payload->>'provider'='TELEGRAM'
                     AND thread.fanvue_account_id=%s
                  UNION ALL
                  SELECT m.telegram_user_id,
                         COALESCE('telegram:'||d.telegram_chat_id||':'||d.outbound_telegram_message_id,
                                  'correlation:'||d.correlation_id),
                         d.confirmed_at, 'commercial_delivery'
                    FROM telegram_sales_delivery_operations d
                    JOIN telegram_identity_map m ON m.fanvue_account_id=d.fanvue_account_id
                     AND m.local_fanvue_user_id=d.fanvue_user_id
                     AND m.is_active=TRUE AND m.verification_status='VERIFIED'
                   WHERE d.creator_profile_id=%s AND d.fanvue_account_id=%s
                     AND d.state='CONFIRMED' AND d.confirmed_at IS NOT NULL
                ) SELECT * FROM events ORDER BY occurred_at,event_key
                """,
                (creator_profile_id, fanvue_account_id, fanvue_account_id,
                 fanvue_account_id, creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def transactions(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT transaction.customer_commerce_transaction_id AS record_id,
                       transaction.transaction_order_id, transaction.gross_minor,
                       transaction.net_minor, transaction.payment_status,
                       transaction.purchase_source, transaction.payment_timestamp,
                       profile.customer_commerce_profile_id,
                       profile.external_fanvue_user_uuid,
                       intent.purchase_intent_id,
                       COALESCE(ownership.attributed_asset_count,0) AS attributed_asset_count,
                       COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                         OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                         OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','')
                              ILIKE 'CONTROLLED_TEST%%' AS excluded_test
                  FROM customer_commerce_transactions transaction
                  JOIN customer_commerce_profiles profile
                    ON profile.customer_commerce_profile_id=transaction.customer_commerce_profile_id
                  LEFT JOIN purchase_intents intent
                    ON intent.provider_transaction_order_id=transaction.transaction_order_id
                   AND intent.fanvue_account_id=transaction.fanvue_account_id
                  LEFT JOIN commercial_publications publication
                    ON publication.publication_id=intent.commercial_publication_id
                  LEFT JOIN LATERAL (
                    SELECT COUNT(DISTINCT owned.content_item_id) AS attributed_asset_count
                      FROM provider_purchase_asset_ownership owned
                     WHERE owned.fanvue_account_id=transaction.fanvue_account_id
                       AND owned.provider_transaction_id=transaction.transaction_order_id
                  ) ownership ON TRUE
                 WHERE profile.creator_profile_id=%s AND transaction.fanvue_account_id=%s
                 ORDER BY transaction.payment_timestamp,transaction.transaction_order_id
                """,
                (creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def offers(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT intent.purchase_intent_id AS record_id,intent.telegram_user_id,
                       intent.external_fanvue_user_uuid,intent.commercial_offering_id,
                       intent.expected_price_minor,intent.status,intent.presented_at,
                       offering.title AS offering_title,offering.offering_type,
                       settlement.purchased_at,settlement.realized_amount_minor,
                       settlement.customer_commerce_transaction_id,
                       COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                         OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                         OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','')
                              ILIKE 'CONTROLLED_TEST%%' AS excluded_test
                  FROM purchase_intents intent
                  JOIN commercial_publications publication
                    ON publication.publication_id=intent.commercial_publication_id
                  JOIN commercial_offerings offering
                    ON offering.offering_id=intent.commercial_offering_id
                  LEFT JOIN LATERAL (
                    SELECT transaction.payment_timestamp AS purchased_at,
                           transaction.gross_minor AS realized_amount_minor,
                           transaction.customer_commerce_transaction_id
                      FROM customer_commerce_transactions transaction
                      JOIN customer_commerce_profiles profile
                        ON profile.customer_commerce_profile_id=transaction.customer_commerce_profile_id
                     WHERE transaction.fanvue_account_id=intent.fanvue_account_id
                       AND transaction.transaction_order_id=intent.provider_transaction_order_id
                       AND profile.creator_profile_id=intent.creator_profile_id
                       AND LOWER(transaction.payment_status) IN ('succeeded','successful','paid','completed')
                     ORDER BY transaction.payment_timestamp,
                              transaction.customer_commerce_transaction_id
                     LIMIT 1
                  ) settlement ON TRUE
                 WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                   AND intent.presented_at IS NOT NULL
                 ORDER BY intent.presented_at,intent.purchase_intent_id
                """, (creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def would_have_sold(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT outcome_id AS record_id,external_fanvue_user_uuid,
                          telegram_user_id,commercial_offering_id,purchase_intent_id,
                          observed_at,evidence
                     FROM commerce_recommendation_outcomes
                    WHERE creator_profile_id=%s AND fanvue_account_id=%s
                      AND outcome_type='WOULD_HAVE_SOLD'
                      AND NOT COALESCE((evidence->>'test_specific')::boolean,FALSE)
                      AND COALESCE(evidence->>'source','') NOT ILIKE '%%certification%%'
                    ORDER BY observed_at,outcome_id""",
                (creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def current_customer_state(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT m.telegram_user_id,
                          EXISTS(SELECT 1 FROM purchase_intents i
                           WHERE i.creator_profile_id=%s AND i.fanvue_account_id=%s
                             AND i.telegram_user_id=m.telegram_user_id
                             AND i.status IN ('CREATED','PRESENTED','CLICKED')) AS active_purchase_intent,
                          EXISTS(SELECT 1 FROM sales_sessions s
                           WHERE s.creator_profile_id=%s AND s.fanvue_account_id=%s
                             AND s.fanvue_user_id=m.local_fanvue_user_id
                             AND s.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')) AS active_sales_session
                     FROM telegram_identity_map m
                    WHERE m.fanvue_account_id=%s AND m.is_active=TRUE""",
                (creator_profile_id, fanvue_account_id, creator_profile_id,
                 fanvue_account_id, fanvue_account_id),
            )
            return {int(row["telegram_user_id"]): dict(row) for row in cursor.fetchall()}

    def current_sales_status(self, *, creator_profile_id: int, fanvue_account_id: int):
        """Point-in-time canonical active Sales Session and PurchaseIntent counts."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                     (SELECT COUNT(*) FROM sales_sessions
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')
                         AND NOT EXISTS (
                           SELECT 1 FROM purchase_intents test_intent
                           LEFT JOIN commercial_publications publication
                             ON publication.publication_id=test_intent.commercial_publication_id
                          WHERE test_intent.creator_profile_id=sales_sessions.creator_profile_id
                            AND test_intent.fanvue_account_id=sales_sessions.fanvue_account_id
                            AND test_intent.external_fanvue_user_uuid=sales_sessions.external_fanvue_user_uuid
                            AND (COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                              OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                              OR COALESCE(test_intent.created_metadata#>>'{recommendation_trace,strategy}','') ILIKE 'CONTROLLED_TEST%%')
                         )) AS active_sales_sessions,
                     (SELECT COUNT(*) FROM purchase_intents intent
                       LEFT JOIN commercial_publications publication
                         ON publication.publication_id=intent.commercial_publication_id
                       WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                         AND intent.status IN ('CREATED','PRESENTED','CLICKED')
                         AND NOT (COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                           OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                           OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','') ILIKE 'CONTROLLED_TEST%%')) AS active_purchase_intents""",
                (creator_profile_id, fanvue_account_id, creator_profile_id, fanvue_account_id),
            )
            return dict(cursor.fetchone())
