"""Atomic operator attestation for historically uncertain commercial sends."""
from __future__ import annotations

import json
from uuid import UUID, uuid4

from app.database import get_db_connection


class OperatorDeliveryResolutionRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_for_operation(self, operation_id: UUID):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM public.operator_delivery_resolutions "
                "WHERE ordinary_operation_id=%s", (operation_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def resolve(self, *, operation_id: UUID, creator_profile_id: int,
                fanvue_account_id: int, relationship_key: str,
                telegram_user_id: int, telegram_chat_id: int,
                purchase_intent_id: UUID | None, outcome: str,
                presentation_mode: str, provider_acceptance_evidence: bool,
                provider_readback_evidence: bool, resolved_by: str,
                evidence: dict | None = None):
        """Resolve once while preserving SEND_UNCERTAIN and locking commerce state."""
        if outcome not in {"DELIVERED", "NOT_DELIVERED"}:
            raise ValueError("Unsupported delivery resolution outcome.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                           (f"operator-delivery:{operation_id}",))
            cursor.execute("SELECT * FROM public.ordinary_chat_reply_operations "
                           "WHERE operation_id=%s FOR UPDATE", (operation_id,))
            operation = cursor.fetchone()
            if not operation:
                raise LookupError("Ordinary reply operation was not found.")
            if (int(operation["telegram_chat_id"]) != int(telegram_chat_id)
                    or int(operation["inbound_sender_telegram_user_id"]) != int(telegram_user_id)):
                raise PermissionError("Delivery resolution relationship scope mismatch.")
            cursor.execute("SELECT * FROM public.operator_delivery_resolutions "
                           "WHERE ordinary_operation_id=%s FOR UPDATE", (operation_id,))
            existing = cursor.fetchone()
            if existing:
                if existing["outcome"] != outcome:
                    raise ValueError("A conflicting delivery resolution already exists.")
                return dict(existing), True
            if operation["state"] != "SEND_UNCERTAIN":
                raise ValueError("Only a current SEND_UNCERTAIN operation can be resolved.")
            if operation.get("sent_confirmed_at") or operation.get("outbound_telegram_message_id"):
                raise ValueError("Provider-confirmed delivery evidence blocks operator attestation.")

            intent = None
            prior = corrected = None
            if purchase_intent_id:
                cursor.execute("SELECT * FROM public.purchase_intents "
                               "WHERE purchase_intent_id=%s FOR UPDATE", (purchase_intent_id,))
                intent = cursor.fetchone()
                if not intent:
                    raise LookupError("Purchase Intent was not found.")
                if (int(intent["creator_profile_id"]) != int(creator_profile_id)
                        or int(intent["fanvue_account_id"]) != int(fanvue_account_id)
                        or int(intent["telegram_user_id"]) != int(telegram_user_id)
                        or int(intent["telegram_chat_id"]) != int(telegram_chat_id)):
                    raise PermissionError("Purchase Intent scope mismatch.")
                if (intent.get("purchased_at") or intent.get("provider_transaction_order_id")
                        or intent.get("provider_payment_id") or intent.get("provider_event_id")):
                    raise ValueError("Purchased or settled authority blocks delivery resolution.")
                prior = str(intent["status"])
                corrected = prior
                if outcome == "DELIVERED" and prior == "CLICKED":
                    corrected = "PRESENTED"
                    cursor.execute("""UPDATE public.purchase_intents SET
                        status='PRESENTED',clicked_at=NULL,
                        presented_at=%s,updated_at=NOW()
                        WHERE purchase_intent_id=%s""",
                        (operation["uncertain_at"], purchase_intent_id))

            presentation_at = operation["uncertain_at"] if outcome == "DELIVERED" else None
            resolution_id = uuid4()
            cursor.execute("""INSERT INTO public.operator_delivery_resolutions(
                resolution_id,ordinary_operation_id,creator_profile_id,fanvue_account_id,
                relationship_key,telegram_user_id,telegram_chat_id,purchase_intent_id,
                outcome,provenance,original_operation_state,original_uncertainty_reason,
                presentation_mode,provider_acceptance_evidence,provider_readback_evidence,
                telegram_message_id,attested_presentation_at,resolved_by,
                prior_purchase_intent_state,corrected_purchase_intent_state,evidence)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'OPERATOR_ATTESTED',
                       'SEND_UNCERTAIN',%s,%s,%s,%s,NULL,%s,%s,%s,%s,%s::jsonb)
                RETURNING *""", (
                resolution_id, operation_id, creator_profile_id, fanvue_account_id,
                relationship_key, telegram_user_id, telegram_chat_id, purchase_intent_id,
                outcome, str(operation.get("last_error") or "UNKNOWN"), presentation_mode,
                bool(provider_acceptance_evidence), bool(provider_readback_evidence),
                presentation_at, resolved_by, prior, corrected,
                json.dumps(evidence or {}, default=str),
            ))
            return dict(cursor.fetchone()), False
