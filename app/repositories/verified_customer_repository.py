"""Read authority for the production Verified Customers directory."""

from __future__ import annotations

from app.database import get_db_connection


class VerifiedCustomerRepository:
    """Project successful, non-test commerce without treating provider users as customers."""

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def customers(self, *, creator_profile_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """
                WITH qualifying_transactions AS (
                  SELECT transaction.*,
                         NOT (COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                           OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                           OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','') ILIKE 'CONTROLLED_TEST%%') AS production_eligible
                    FROM customer_commerce_transactions transaction
                    LEFT JOIN purchase_intents intent ON intent.provider_transaction_order_id=transaction.transaction_order_id AND intent.fanvue_account_id=transaction.fanvue_account_id
                    LEFT JOIN commercial_publications publication ON publication.publication_id=intent.commercial_publication_id
                   WHERE transaction.fanvue_account_id=%s
                     AND LOWER(transaction.payment_status) IN ('succeeded','successful','paid','completed')
                ), production_profiles AS (
                  SELECT profile.* FROM customer_commerce_profiles profile
                   WHERE profile.creator_profile_id=%s AND profile.fanvue_account_id=%s
                     AND EXISTS (SELECT 1 FROM qualifying_transactions transaction WHERE transaction.customer_commerce_profile_id=profile.customer_commerce_profile_id AND transaction.production_eligible)
                )
                SELECT profile.*, fanvue.id AS local_fanvue_user_id,
                       COALESCE(profile.display_name,fanvue.display_name,profile.handle,fanvue.username,'Verified customer') AS resolved_display_name,
                       COALESCE(profile.handle,fanvue.username) AS resolved_handle,
                       mapping.telegram_user_id AS mapped_telegram_user_id,
                       CASE WHEN mapping.telegram_user_id IS NOT NULL THEN 'telegram:' || mapping.telegram_user_id::text END AS relationship_key,
                       intelligence.buyer_tier,intelligence.is_top_spender,intelligence.is_whale,
                       EXISTS (SELECT 1 FROM sales_sessions session WHERE session.creator_profile_id=profile.creator_profile_id AND session.fanvue_account_id=profile.fanvue_account_id AND session.external_fanvue_user_uuid=profile.external_fanvue_user_uuid AND session.state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT','CONTINUING')) AS active_sales_session,
                       EXISTS (SELECT 1 FROM purchase_intents pi WHERE pi.creator_profile_id=profile.creator_profile_id AND pi.fanvue_account_id=profile.fanvue_account_id AND pi.external_fanvue_user_uuid=profile.external_fanvue_user_uuid AND pi.status IN ('CREATED','PRESENTED','CLICKED')) AS active_purchase_intent
                  FROM production_profiles profile
                  LEFT JOIN fanvue_users fanvue ON fanvue.fanvue_account_id=profile.fanvue_account_id AND fanvue.fanvue_user_uuid=profile.external_fanvue_user_uuid
                  LEFT JOIN telegram_identity_map mapping ON mapping.fanvue_account_id=profile.fanvue_account_id AND mapping.external_fanvue_user_uuid=profile.external_fanvue_user_uuid AND mapping.is_active=TRUE AND mapping.verification_status='VERIFIED'
                  LEFT JOIN buyer_intelligence intelligence ON intelligence.fanvue_account_id=profile.fanvue_account_id AND intelligence.fanvue_user_id=fanvue.id::text
                 ORDER BY profile.last_purchase_at DESC,profile.customer_commerce_profile_id
                """, (fanvue_account_id, creator_profile_id, fanvue_account_id),
            )
            return [dict(row) for row in cursor.fetchall()]

    def transactions(self, *, profile_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT transaction.customer_commerce_transaction_id,transaction.transaction_order_id,
                          transaction.gross_minor,transaction.net_minor,transaction.payment_status,
                          transaction.purchase_source,transaction.payment_timestamp
                     FROM customer_commerce_transactions transaction
                     LEFT JOIN purchase_intents intent
                       ON intent.provider_transaction_order_id=transaction.transaction_order_id
                      AND intent.fanvue_account_id=transaction.fanvue_account_id
                     LEFT JOIN commercial_publications publication
                       ON publication.publication_id=intent.commercial_publication_id
                    WHERE transaction.customer_commerce_profile_id=%s
                      AND LOWER(transaction.payment_status) IN ('succeeded','successful','paid','completed')
                      AND NOT (COALESCE((publication.publication_metadata->>'test_specific')::boolean,FALSE)
                        OR COALESCE(publication.publication_metadata->>'purpose','') ILIKE 'controlled_smoke_test%%'
                        OR COALESCE(intent.created_metadata#>>'{recommendation_trace,strategy}','') ILIKE 'CONTROLLED_TEST%%')
                    ORDER BY transaction.payment_timestamp DESC,transaction.customer_commerce_transaction_id""", (profile_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def subscription_events(self, *, fanvue_account_id: int, external_uuid):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT event_type,payload,received_at FROM webhook_events
                    WHERE event_type IN ('subscription_new','subscription_renewed','subscription_cancelled','subscription_expired')
                      AND (payload#>>'{sender,uuid}'=%s OR payload->>'subscriberUuid'=%s)
                    ORDER BY COALESCE((payload->>'timestamp')::timestamptz,received_at),id""",
                (str(external_uuid), str(external_uuid)),
            )
            return [dict(row) for row in cursor.fetchall()]
