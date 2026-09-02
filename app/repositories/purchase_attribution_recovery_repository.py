"""Authoritative unresolved-purchase review and manual resolution persistence."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection


class PurchaseAttributionRecoveryRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def list_unresolved(self, *, creator_profile_id: int, limit: int = 100):
        return self._rows(self._review_sql() + " ORDER BY reconciliation.updated_at DESC LIMIT %s",
                          (creator_profile_id, max(1, min(200, int(limit)))))

    def get_unresolved(self, *, creator_profile_id: int, reconciliation_id: UUID):
        rows = self._rows(self._review_sql() + " AND reconciliation.reconciliation_id=%s",
                          (creator_profile_id, reconciliation_id))
        return rows[0] if rows else None

    def list_candidates(self, *, creator_profile_id: int, fanvue_account_id: int,
                        buyer_uuid: UUID, amount_minor: int, purchased_at,
                        provider_resource_id: str | None = None):
        return self._rows(
            """SELECT intent.*,offering.title AS offering_title,
                      offering.offering_type,publication.external_product_id,
                      operation.state AS telegram_delivery_state,
                      operation.outbound_telegram_message_id,
                      session_link.sales_session_id,
                      offering.source_photoshoot_deliverable_id
               FROM public.purchase_intents intent
               JOIN public.commercial_offerings offering
                 ON offering.offering_id=intent.commercial_offering_id
               JOIN public.commercial_publications publication
                 ON publication.publication_id=intent.commercial_publication_id
                AND publication.commercial_offering_id=offering.offering_id
               LEFT JOIN LATERAL (
                   SELECT delivery.state,delivery.outbound_telegram_message_id,
                          delivery.telegram_accepted_at
                   FROM public.telegram_sales_delivery_operations delivery
                   WHERE delivery.purchase_intent_id=intent.purchase_intent_id
                   ORDER BY CASE delivery.state
                              WHEN 'CONFIRMED' THEN 0
                              WHEN 'TELEGRAM_ACCEPTED' THEN 1
                              ELSE 2 END,
                            delivery.created_at DESC
                   LIMIT 1
               ) operation ON TRUE
               LEFT JOIN public.sales_session_purchase_intents session_link
                 ON session_link.purchase_intent_id=intent.purchase_intent_id
               WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                 AND intent.external_fanvue_user_uuid=%s
                 AND intent.expected_price_minor=%s
                 AND (%s::text IS NULL OR publication.external_product_id=%s
                      OR intent.provider_resource_id=%s)
                 AND COALESCE(intent.presented_at,operation.telegram_accepted_at,
                              intent.created_at)<=%s
                 AND intent.status<>'PURCHASED'
               ORDER BY COALESCE(intent.presented_at,operation.telegram_accepted_at,
                                 intent.created_at) DESC""",
            (creator_profile_id, fanvue_account_id, buyer_uuid, amount_minor,
             provider_resource_id, provider_resource_id,
             provider_resource_id, purchased_at),
        )

    def commit_manual(self, *, creator_profile_id: int, reconciliation_id: UUID,
                      purchase_intent_id: UUID, operator_source: str,
                      operator_note: str | None):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.purchase_attribution_resolution_audit WHERE reconciliation_id=%s FOR UPDATE",
                    (reconciliation_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    if UUID(str(existing["purchase_intent_id"])) != purchase_intent_id:
                        raise ValueError("Transaction is already attributed to a different Purchase Intent.")
                    return dict(existing), True
                cursor.execute(
                    """SELECT reconciliation.*,transaction.gross_minor,
                              transaction.payment_timestamp,
                              profile.customer_commerce_profile_id,
                              profile.external_fanvue_user_uuid,
                              COALESCE(reconciliation.canonical_transaction_order_id,
                                       reconciliation.observed_transaction_id) AS transaction_order_id
                       FROM public.commerce_signal_reconciliations reconciliation
                       JOIN public.customer_commerce_profiles profile
                         ON profile.creator_profile_id=reconciliation.creator_profile_id
                        AND profile.fanvue_account_id=reconciliation.fanvue_account_id
                        AND profile.external_fanvue_user_uuid=reconciliation.external_fanvue_user_uuid
                       JOIN public.customer_commerce_transactions transaction
                         ON transaction.customer_commerce_profile_id=profile.customer_commerce_profile_id
                        AND transaction.fanvue_account_id=reconciliation.fanvue_account_id
                        AND transaction.transaction_order_id=COALESCE(
                            reconciliation.canonical_transaction_order_id,
                            reconciliation.observed_transaction_id)
                       WHERE reconciliation.reconciliation_id=%s
                         AND reconciliation.creator_profile_id=%s FOR UPDATE""",
                    (reconciliation_id, creator_profile_id),
                )
                review = cursor.fetchone()
                if review is None:
                    raise LookupError("Unresolved purchase was not found.")
                # The reconciliation row lock serializes concurrent submissions;
                # recheck the audit after acquiring it for idempotent convergence.
                cursor.execute(
                    "SELECT * FROM public.purchase_attribution_resolution_audit WHERE reconciliation_id=%s",
                    (reconciliation_id,),
                )
                existing = cursor.fetchone()
                if existing:
                    if UUID(str(existing["purchase_intent_id"])) != purchase_intent_id:
                        raise ValueError("Transaction is already attributed to a different Purchase Intent.")
                    return dict(existing), True
                if review["state"] != "VERIFIED" or review.get("attribution_state") not in ("PENDING", "UNKNOWN"):
                    raise ValueError("Only verified unresolved purchases can be manually attributed.")
                cursor.execute(
                    """SELECT intent.*,offering.offering_id,
                              publication.publication_id,
                              publication.external_product_id,
                              EXISTS (
                                  SELECT 1
                                  FROM public.telegram_sales_delivery_operations delivery
                                  WHERE delivery.purchase_intent_id=intent.purchase_intent_id
                                    AND delivery.state IN ('TELEGRAM_ACCEPTED','CONFIRMED')
                              ) AS has_confirmed_telegram_presentation
                       FROM public.purchase_intents intent
                       JOIN public.commercial_offerings offering
                         ON offering.offering_id=intent.commercial_offering_id
                        AND offering.creator_profile_id=intent.creator_profile_id
                       JOIN public.commercial_publications publication
                         ON publication.publication_id=intent.commercial_publication_id
                        AND publication.commercial_offering_id=offering.offering_id
                       WHERE intent.purchase_intent_id=%s FOR UPDATE""",
                    (purchase_intent_id,),
                )
                intent = cursor.fetchone()
                if intent is None:
                    raise LookupError("Purchase Intent or its offering/publication was not found.")
                if int(intent["creator_profile_id"]) != int(review["creator_profile_id"]):
                    raise ValueError("Creator does not match the unresolved transaction.")
                if int(intent["fanvue_account_id"]) != int(review["fanvue_account_id"]):
                    raise ValueError("Fanvue account does not match the unresolved transaction.")
                if intent["external_fanvue_user_uuid"] != review["external_fanvue_user_uuid"]:
                    raise ValueError("Customer does not match the unresolved transaction.")
                if int(intent["expected_price_minor"]) != int(review["gross_minor"]):
                    raise ValueError("Purchase amount does not match the Purchase Intent.")
                currency = self._currency(review.get("earnings_record") or {})
                if currency is None:
                    raise ValueError("Authoritative purchase currency is unavailable.")
                if currency != self._currency_value(intent["expected_currency"]):
                    raise ValueError("Purchase currency does not match the Purchase Intent.")
                if intent["created_at"] > review["payment_timestamp"]:
                    raise ValueError("Purchase Intent was created after the transaction.")
                provider_resource = self._resource(review.get("earnings_record") or {})
                canonical_resource = str(
                    intent.get("external_product_id")
                    or intent.get("provider_resource_id") or ""
                ).strip()
                if provider_resource and canonical_resource != provider_resource:
                    raise ValueError("Fanvue provider resource does not match the Purchase Intent.")
                if not intent["has_confirmed_telegram_presentation"]:
                    raise ValueError(
                        "No confirmed Telegram presentation evidence."
                    )
                transaction_id = str(review["transaction_order_id"])
                cursor.execute(
                    """SELECT purchase_intent_id FROM public.purchase_intents
                       WHERE fanvue_account_id=%s AND provider_transaction_order_id=%s
                         AND purchase_intent_id<>%s""",
                    (review["fanvue_account_id"], transaction_id, purchase_intent_id),
                )
                if cursor.fetchone():
                    raise ValueError("Transaction is already attributed to another Purchase Intent.")
                if intent["status"] == "PURCHASED":
                    if intent.get("provider_transaction_order_id") != transaction_id:
                        raise ValueError("Purchase Intent belongs to a different transaction.")
                else:
                    cursor.execute(
                        """UPDATE public.purchase_intents SET status='PURCHASED',
                               purchased_at=%s,provider_transaction_order_id=%s,
                               attribution_result='ATTRIBUTED',
                               attribution_reason='MANUALLY_ATTRIBUTED: operator resolved verified ambiguity',
                               updated_at=NOW() WHERE purchase_intent_id=%s""",
                        (review["payment_timestamp"], transaction_id, purchase_intent_id),
                    )
                previous = review.get("attribution_state") or review["state"]
                resolution_id = uuid4()
                evidence = {
                    "provider_event_id": review["provider_event_id"],
                    "buyer_uuid": str(review["external_fanvue_user_uuid"]),
                    "amount_minor": int(review["gross_minor"]),
                }
                cursor.execute(
                    """INSERT INTO public.purchase_attribution_resolution_audit (
                           resolution_id,reconciliation_id,fanvue_account_id,
                           creator_profile_id,transaction_order_id,purchase_intent_id,
                           commercial_offering_id,previous_state,new_state,
                           resolution_type,operator_source,operator_note,evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'MANUALLY_ATTRIBUTED',
                               'MANUAL',%s,%s,%s::jsonb) RETURNING *""",
                    (resolution_id, reconciliation_id, review["fanvue_account_id"],
                     creator_profile_id, transaction_id, purchase_intent_id,
                     intent["commercial_offering_id"], previous, operator_source,
                     operator_note, json.dumps(evidence)),
                )
                audit = dict(cursor.fetchone())
                cursor.execute(
                    """UPDATE public.commerce_signal_reconciliations
                       SET attribution_state='MANUALLY_ATTRIBUTED',
                           attribution_reason=%s,attributed_purchase_intent_id=%s,
                           updated_at=NOW() WHERE reconciliation_id=%s""",
                    ("Operator manually resolved verified attribution ambiguity.",
                     purchase_intent_id, reconciliation_id),
                )
                return audit, False

    def mark_downstream_completed(self, resolution_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.purchase_attribution_resolution_audit
                       SET downstream_completed_at=COALESCE(
                           downstream_completed_at,NOW()
                       ) WHERE resolution_id=%s RETURNING *""",
                    (resolution_id,),
                )
                row = cursor.fetchone()
        if row is None:
            raise LookupError("Manual attribution audit was not found.")
        return dict(row)

    def _review_sql(self):
        return """SELECT reconciliation.*,
                         profile.customer_commerce_profile_id,profile.display_name,
                         profile.handle,identity.telegram_user_id,
                         transaction.gross_minor,transaction.net_minor,
                         transaction.payment_status,transaction.purchase_source,
                         transaction.payment_timestamp,
                         COALESCE(reconciliation.canonical_transaction_order_id,
                                  reconciliation.observed_transaction_id) AS transaction_order_id
                  FROM public.commerce_signal_reconciliations reconciliation
                  LEFT JOIN public.customer_commerce_profiles profile
                    ON profile.creator_profile_id=reconciliation.creator_profile_id
                   AND profile.fanvue_account_id=reconciliation.fanvue_account_id
                   AND profile.external_fanvue_user_uuid=reconciliation.external_fanvue_user_uuid
                  LEFT JOIN public.telegram_identity_map identity
                    ON identity.fanvue_account_id=reconciliation.fanvue_account_id
                   AND identity.external_fanvue_user_uuid=reconciliation.external_fanvue_user_uuid
                   AND identity.is_active=TRUE
                  LEFT JOIN public.customer_commerce_transactions transaction
                    ON transaction.customer_commerce_profile_id=profile.customer_commerce_profile_id
                   AND transaction.fanvue_account_id=reconciliation.fanvue_account_id
                   AND transaction.transaction_order_id=COALESCE(
                       reconciliation.canonical_transaction_order_id,
                       reconciliation.observed_transaction_id)
                  WHERE reconciliation.creator_profile_id=%s
                    AND (reconciliation.state='PENDING' OR
                         reconciliation.attribution_state IN ('PENDING','UNKNOWN'))"""

    def _rows(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def _resource(earning):
        for key in ("mediaLinkUuid", "mediaLinkId", "media_link_uuid",
                    "media_link_id", "externalProductId", "external_product_id"):
            if earning.get(key):
                return str(earning[key])
        return None

    @staticmethod
    def _currency(earning):
        for key in ("currency", "currencyCode", "currency_code"):
            value = PurchaseAttributionRecoveryRepository._currency_value(
                earning.get(key)
            )
            if value is not None:
                return value
        return None

    @staticmethod
    def _currency_value(value):
        normalized = str(value or "").strip().upper()
        if len(normalized) != 3 or not normalized.isalpha():
            return None
        return normalized
