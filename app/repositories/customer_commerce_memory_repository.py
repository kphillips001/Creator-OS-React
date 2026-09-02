"""Read-only SQL projections for normalized customer commerce memory."""
from __future__ import annotations

from collections.abc import Callable

from app.database import get_db_connection


class CustomerCommerceMemoryRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def verified_purchase_intents(self, identity) -> tuple[dict, ...]:
        clause, value = self._purchase_identity(identity)
        if clause is None:
            return ()
        return self._all(
            f"""SELECT intent.purchase_intent_id,intent.creator_profile_id,
                       intent.fanvue_account_id,intent.purchased_at,
                       intent.commercial_offering_id,intent.expected_price_minor,
                       intent.expected_currency,intent.provider_transaction_order_id,
                       intent.status,intent.attribution_result,
                       offering.offering_type,offering.primary_sales_channel,
                       link.sales_session_id,
                       array_agg(member.asset_id ORDER BY member.position) AS asset_ids,
                       COALESCE(jsonb_agg(profile.profile_data)
                         FILTER (WHERE profile.asset_id IS NOT NULL),'[]'::jsonb)
                         AS intelligence_profiles
                  FROM public.purchase_intents intent
                  JOIN public.commercial_offerings offering
                    ON offering.offering_id=intent.commercial_offering_id
                  JOIN public.commercial_offering_assets member
                    ON member.offering_id=offering.offering_id
             LEFT JOIN public.asset_intelligence_profiles profile
                    ON profile.asset_id=member.asset_id
                   AND profile.creator_profile_id=intent.creator_profile_id
             LEFT JOIN public.sales_session_purchase_intents link
                    ON link.purchase_intent_id=intent.purchase_intent_id
                 WHERE intent.creator_profile_id=%s
                   AND intent.fanvue_account_id=%s
                   AND {clause}
                   AND intent.status='PURCHASED'
                   AND intent.attribution_result='ATTRIBUTED'
              GROUP BY intent.purchase_intent_id,offering.offering_type,
                       offering.primary_sales_channel,link.sales_session_id
              ORDER BY intent.purchased_at,intent.purchase_intent_id""",
            (identity.creator_profile_id, identity.fanvue_account_id, value),
        )

    def valid_entitlements(self, identity) -> tuple[dict, ...]:
        clauses, params = [], []
        if identity.core_user_id is not None:
            clauses.append("entitlement.core_user_id=%s")
            params.append(identity.core_user_id)
        if identity.legacy_fanvue_user_id is not None:
            clauses.append("(entitlement.legacy_fanvue_account_id=%s AND entitlement.legacy_fanvue_user_id=%s)")
            params.extend((identity.fanvue_account_id, identity.legacy_fanvue_user_id))
        if not clauses:
            return ()
        return self._all(
            f"""SELECT entitlement.id,entitlement.product_id,
                       entitlement.status,entitlement.source_type,
                       entitlement.commerce_provider,
                       entitlement.provider_transaction_id,
                       entitlement.granted_at,entitlement.fulfilled_at,
                       product.product_type,
                       COALESCE(array_agg(member.asset_id ORDER BY member.position)
                         FILTER (WHERE member.asset_id IS NOT NULL),ARRAY[]::bigint[])
                         AS asset_ids
                  FROM public.customer_entitlements entitlement
                  JOIN public.products product ON product.id=entitlement.product_id
             LEFT JOIN public.product_assets member ON member.product_id=product.id
                 WHERE product.creator_profile_id=%s
                   AND ({' OR '.join(clauses)})
                   AND entitlement.status IN ('active','fulfilled')
                   AND (entitlement.expires_at IS NULL OR entitlement.expires_at>now())
              GROUP BY entitlement.id,product.product_type
              ORDER BY COALESCE(entitlement.fulfilled_at,entitlement.granted_at),entitlement.id""",
            (identity.creator_profile_id, *params),
        )

    def legacy_asset_purchases(self, identity) -> tuple[dict, ...]:
        if identity.legacy_fanvue_user_id is None:
            return ()
        return self._all(
            """SELECT id,content_item_id,usage_type,content_tag,purchase_amount,
                      fanvue_media_uuid,COALESCE(purchased_at,created_at) AS purchased_at
                 FROM public.content_usage_log
                WHERE fanvue_account_id=%s AND fanvue_user_id=%s
                  AND usage_type=ANY(%s) AND content_item_id IS NOT NULL
                ORDER BY COALESCE(purchased_at,created_at),id""",
            (identity.fanvue_account_id, identity.legacy_fanvue_user_id,
             ["ppv_purchased", "content_unlocked", "content_owned", "purchase", "unlock", "owned"]),
        )

    def unmatched_transactions(self, profile_id) -> tuple[dict, ...]:
        if profile_id is None:
            return ()
        return self._all(
            """SELECT transaction.customer_commerce_transaction_id,
                      transaction.fanvue_account_id,transaction.transaction_order_id,
                      transaction.gross_minor,transaction.net_minor,
                      transaction.payment_status,transaction.purchase_source,
                      transaction.payment_timestamp
                 FROM public.customer_commerce_transactions transaction
            LEFT JOIN public.purchase_intents intent
                   ON intent.fanvue_account_id=transaction.fanvue_account_id
                  AND intent.provider_transaction_order_id=transaction.transaction_order_id
                  AND intent.status='PURCHASED'
                  AND intent.attribution_result='ATTRIBUTED'
                WHERE transaction.customer_commerce_profile_id=%s
                  AND intent.purchase_intent_id IS NULL
                ORDER BY transaction.payment_timestamp,transaction.customer_commerce_transaction_id""",
            (profile_id,),
        )

    @staticmethod
    def _purchase_identity(identity):
        if identity.external_fanvue_user_uuid is not None:
            return "intent.external_fanvue_user_uuid=%s", identity.external_fanvue_user_uuid
        if identity.telegram_user_id is not None:
            return "intent.telegram_user_id=%s", identity.telegram_user_id
        return None, None

    def _all(self, sql, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, tuple(params))
                return tuple(dict(row) for row in cursor.fetchall())

