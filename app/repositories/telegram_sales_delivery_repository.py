"""PostgreSQL persistence and atomic claims for Telegram commercial sends."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.telegram_sales_delivery_operation import (
    TelegramSalesDeliveryOperation, TelegramSalesDeliveryState,
)


class TelegramSalesDeliveryRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_or_create(self, **values):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.telegram_sales_delivery_operations (
                       operation_id,correlation_id,creator_profile_id,fanvue_account_id,
                       conversation_thread_id,fanvue_user_id,telegram_chat_id,
                       inbound_telegram_message_id,purchase_intent_id,
                       commercial_offering_id,commercial_publication_id,response_text,
                       delivery_payload,state)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'CREATED')
                       ON CONFLICT (correlation_id) DO NOTHING RETURNING *""",
                    (uuid4(), values["correlation_id"], values["creator_profile_id"],
                     values["fanvue_account_id"], values["conversation_thread_id"],
                     values["fanvue_user_id"], values["telegram_chat_id"],
                     values["inbound_telegram_message_id"], values["purchase_intent_id"],
                     values["commercial_offering_id"], values["commercial_publication_id"],
                     values["response_text"], json.dumps(values["delivery_payload"])),
                )
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        "SELECT * FROM public.telegram_sales_delivery_operations WHERE correlation_id=%s",
                        (values["correlation_id"],),
                    )
                    row = cursor.fetchone()
                return self._item(row), created

    def get_by_correlation(self, correlation_id: str):
        return self._one("SELECT * FROM public.telegram_sales_delivery_operations WHERE correlation_id=%s", (correlation_id,))

    def get_by_purchase_intent(self, purchase_intent_id):
        return self._one(
            """SELECT * FROM public.telegram_sales_delivery_operations
               WHERE purchase_intent_id=%s ORDER BY created_at DESC LIMIT 1""",
            (purchase_intent_id,),
        )

    def claim_created(self, operation_id: UUID):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='SENDING',sending_at=NOW(),updated_at=NOW()
               WHERE operation_id=%s AND state IN ('CREATED','RETRYABLE') RETURNING *""", (operation_id,),
        )

    def mark_accepted(self, operation_id: UUID, message_id: int):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='TELEGRAM_ACCEPTED',outbound_telegram_message_id=%s,
                   telegram_accepted_at=NOW(),updated_at=NOW(),failure_reason=NULL
               WHERE operation_id=%s AND state='SENDING' RETURNING *""",
            (message_id, operation_id),
        )

    def record_provider_evidence(self, operation_id: UUID, evidence):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET delivery_payload=delivery_payload || %s::jsonb,updated_at=NOW()
               WHERE operation_id=%s AND state='SENDING' RETURNING *""",
            (json.dumps({"provider_delivery_evidence": dict(evidence)}), operation_id),
        )

    def mark_confirmed(self, operation_id: UUID):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='CONFIRMED',confirmed_at=NOW(),updated_at=NOW()
               WHERE operation_id=%s AND state IN ('TELEGRAM_ACCEPTED','CONFIRMED') RETURNING *""",
            (operation_id,),
        )

    def confirm_purchase_acknowledgement(self, operation_id: UUID):
        """Atomically confirm an acknowledgement delivery and its PurchaseIntent."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT operation.*,intent.status AS intent_status,
                              intent.purchase_acknowledged_at
                       FROM public.telegram_sales_delivery_operations operation
                       JOIN public.purchase_intents intent
                         ON intent.purchase_intent_id=operation.purchase_intent_id
                       WHERE operation.operation_id=%s
                       FOR UPDATE OF operation,intent""",
                    (operation_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LookupError("Acknowledgement delivery operation was not found.")
                payload = dict(row.get("delivery_payload") or {})
                metadata = dict(payload.get("metadata") or {})
                if metadata.get("message_purpose") != "PURCHASE_ACKNOWLEDGEMENT":
                    raise ValueError("Delivery operation is not a purchase acknowledgement.")
                if row["state"] not in {"TELEGRAM_ACCEPTED", "CONFIRMED"}:
                    raise ValueError("Acknowledgement delivery is not provider-accepted.")
                if row["intent_status"] != "PURCHASED":
                    raise ValueError("Only a purchased PurchaseIntent can be acknowledged.")
                confirmed_at = row.get("confirmed_at") or datetime.now(timezone.utc)
                cursor.execute(
                    """UPDATE public.telegram_sales_delivery_operations
                       SET state='CONFIRMED',confirmed_at=COALESCE(confirmed_at,%s),
                           updated_at=NOW()
                       WHERE operation_id=%s RETURNING *""",
                    (confirmed_at, operation_id),
                )
                confirmed = cursor.fetchone()
                cursor.execute(
                    """UPDATE public.purchase_intents
                       SET purchase_acknowledged_at=COALESCE(
                               purchase_acknowledged_at,%s
                           ),updated_at=NOW()
                       WHERE purchase_intent_id=%s AND status='PURCHASED'
                       RETURNING purchase_intent_id""",
                    (confirmed_at, row["purchase_intent_id"]),
                )
                if cursor.fetchone() is None:
                    raise RuntimeError("Purchase acknowledgement persistence failed.")
                return self._item(confirmed)

    def mark_failed(self, operation_id: UUID, reason: str):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='FAILED',failure_reason=%s,failed_at=NOW(),updated_at=NOW()
               WHERE operation_id=%s AND state='SENDING' RETURNING *""", (reason, operation_id),
        )

    def mark_ambiguous(self, operation_id: UUID, reason: str):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='AMBIGUOUS',failure_reason=%s,updated_at=NOW()
               WHERE operation_id=%s AND state='SENDING' RETURNING *""", (reason, operation_id),
        )

    def mark_retryable(self, operation_id: UUID, reason: str):
        return self._one(
            """UPDATE public.telegram_sales_delivery_operations
               SET state='RETRYABLE',failure_reason=%s,updated_at=NOW()
               WHERE operation_id=%s AND state='SENDING' RETURNING *""", (reason, operation_id),
        )

    def mark_sending_ambiguous(self):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.telegram_sales_delivery_operations
                       SET state='AMBIGUOUS',failure_reason='worker_restarted_during_provider_send',updated_at=NOW()
                       WHERE state='SENDING' RETURNING *"""
                )
                return [self._item(row) for row in cursor.fetchall()]

    def list_accepted(self, *, creator_profile_id=None, fanvue_account_id=None, external_fanvue_user_uuid=None):
        # Buyer ownership stays authoritative on purchase_intents.
        clauses = ["operation.state='TELEGRAM_ACCEPTED'"]
        params = []
        if creator_profile_id is not None:
            clauses.append("operation.creator_profile_id=%s"); params.append(creator_profile_id)
        if fanvue_account_id is not None:
            clauses.append("operation.fanvue_account_id=%s"); params.append(fanvue_account_id)
        if external_fanvue_user_uuid is not None:
            clauses.append("intent.external_fanvue_user_uuid=%s"); params.append(external_fanvue_user_uuid)
        return self._many(
            "SELECT operation.* FROM public.telegram_sales_delivery_operations operation JOIN public.purchase_intents intent ON intent.purchase_intent_id=operation.purchase_intent_id WHERE " + " AND ".join(clauses) + " ORDER BY operation.created_at",
            tuple(params),
        )

    def list_confirmed_unacknowledged_acknowledgements(self):
        return self._many(
            """SELECT operation.*
               FROM public.telegram_sales_delivery_operations operation
               JOIN public.purchase_intents intent
                 ON intent.purchase_intent_id=operation.purchase_intent_id
               WHERE operation.state='CONFIRMED'
                 AND intent.status='PURCHASED'
                 AND intent.purchase_acknowledged_at IS NULL
                 AND operation.delivery_payload->'metadata'->>'message_purpose'
                     ='PURCHASE_ACKNOWLEDGEMENT'
               ORDER BY operation.confirmed_at,operation.created_at""",
            (),
        )

    def _one(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params); row = cursor.fetchone()
        return self._item(row) if row else None

    def _many(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params); rows = cursor.fetchall()
        return [self._item(row) for row in rows]

    @staticmethod
    def _item(row):
        if row is None: return None
        values = dict(row)
        values["operation_id"] = UUID(str(values["operation_id"]))
        values["purchase_intent_id"] = UUID(str(values["purchase_intent_id"]))
        values["commercial_offering_id"] = UUID(str(values["commercial_offering_id"]))
        values["commercial_publication_id"] = UUID(str(values["commercial_publication_id"]))
        values["delivery_payload"] = dict(values.get("delivery_payload") or {})
        values["state"] = TelegramSalesDeliveryState(values["state"])
        return TelegramSalesDeliveryOperation(**values)
