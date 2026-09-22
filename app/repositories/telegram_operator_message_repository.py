import hashlib
import json
from datetime import datetime
from uuid import uuid4
from app.database import get_db_connection


class TelegramOperatorMessageRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def reserve(self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id, telegram_identity_mapping_id, local_fanvue_user_id,
                conversation_thread_id, idempotency_key, message_text,
                relationship_control_version, changed_by):
        digest=hashlib.sha256(message_text.encode("utf-8")).hexdigest()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.telegram_operator_message_operations (
                operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                telegram_chat_id,telegram_identity_mapping_id,local_fanvue_user_id,
                conversation_thread_id,idempotency_key,message_text,message_sha256,
                relationship_control_version,changed_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
                DO UPDATE SET updated_at=telegram_operator_message_operations.updated_at
                RETURNING *""",(uuid4(),creator_profile_id,fanvue_account_id,telegram_user_id,
                    telegram_chat_id,telegram_identity_mapping_id,local_fanvue_user_id,
                    conversation_thread_id,idempotency_key,message_text,digest,
                    relationship_control_version,changed_by))
            row=dict(cursor.fetchone())
        if row["message_sha256"]!=digest: raise ValueError("Idempotency key was already used for different text.")
        return row

    def reconcile_confirmed_history(
        self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
        telegram_chat_id, telegram_message_id, message_text, confirmed_at,
        relationship_control_version, changed_by,
    ):
        """Persist a provider-observed historical manual outbound without sending."""
        if not isinstance(telegram_message_id, int) or isinstance(telegram_message_id, bool):
            raise ValueError("A real Telegram message ID is required.")
        if not isinstance(confirmed_at, datetime) or confirmed_at.tzinfo is None:
            raise ValueError("The provider-observed timestamp must be timezone-aware.")
        text = str(message_text or "").strip()
        if not text:
            raise ValueError("Historical message text is required.")
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        key = f"telegram-history-reconciliation:{telegram_chat_id}:{telegram_message_id}"
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.telegram_operator_message_operations(
                operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                telegram_chat_id,idempotency_key,message_text,message_sha256,
                relationship_control_version,origin,state,outbound_telegram_message_id,
                send_attempt_count,changed_by,confirmed_at,created_at,updated_at)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,'HUMAN_OPERATOR','CONFIRMED',
                       %s,0,%s,%s,%s,NOW())
                ON CONFLICT(creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
                DO UPDATE SET updated_at=telegram_operator_message_operations.updated_at
                RETURNING *""", (uuid4(),creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,key,text,digest,
                    relationship_control_version,telegram_message_id,changed_by,
                    confirmed_at,confirmed_at))
            row = dict(cursor.fetchone())
        if (row["message_sha256"] != digest
                or int(row["outbound_telegram_message_id"] or 0) != telegram_message_id
                or row["state"] != "CONFIRMED"):
            raise ValueError("Historical Telegram reconciliation conflicts with durable state.")
        return row

    PRIVATE_DISPATCH_MARKER = "PRIVATE_RUNTIME_DISPATCH_PENDING"

    def claim(self, operation_id, *, expected_version, route="TELEGRAM_BUSINESS"):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_operator_message_operations operation
                SET state='SENDING',send_attempt_count=send_attempt_count+1,sending_at=NOW(),
                    last_error=%s,transport_evidence='{}'::jsonb,updated_at=NOW()
                FROM public.telegram_relationship_controls control
                WHERE operation.operation_id=%s AND operation.state IN ('PREPARED','FAILED')
                  AND operation.outbound_telegram_message_id IS NULL
                  AND NOT (operation.transport_evidence ? 'telegram_message_id')
                  AND control.creator_profile_id=operation.creator_profile_id
                  AND control.fanvue_account_id=operation.fanvue_account_id
                  AND control.telegram_user_id=operation.telegram_user_id
                  AND control.mode='HUMAN_OPERATOR' AND control.control_version=%s
                  AND operation.relationship_control_version=control.control_version
                RETURNING operation.*""",(
                    self.PRIVATE_DISPATCH_MARKER if route == "AVA_TELETHON_PRIVATE" else None,
                    operation_id,expected_version))
            row=cursor.fetchone()
        return dict(row) if row else None

    def get(self, operation_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.telegram_operator_message_operations
                WHERE operation_id=%s""", (operation_id,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def pending_private_dispatches(self, limit=10):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.telegram_operator_message_operations
                WHERE state='SENDING' AND last_error=%s
                ORDER BY sending_at,operation_id LIMIT %s""",
                (self.PRIVATE_DISPATCH_MARKER, max(1, int(limit))))
            rows = cursor.fetchall()
        return [dict(row) for row in rows]

    def begin_invocation(self, operation_id, *, owner, evidence):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_operator_message_operations
                SET last_error='PROVIDER_INVOCATION_BEGUN',
                    transport_evidence=%s::jsonb || jsonb_build_object(
                      'invocation_owner',%s::text,'lease_expires_at',NOW()+INTERVAL '5 minutes'),
                    updated_at=NOW()
                WHERE operation_id=%s AND state='SENDING'
                  AND NOT (transport_evidence ? 'invocation_owner')
                RETURNING *""", (json.dumps(evidence),str(owner),operation_id))
            row=cursor.fetchone()
        return dict(row) if row else None

    def record_transport_evidence(self, operation_id, *, owner, evidence):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_operator_message_operations
                SET transport_evidence=transport_evidence || %s::jsonb,updated_at=NOW()
                WHERE operation_id=%s AND state='SENDING'
                  AND transport_evidence->>'invocation_owner'=%s
                  AND (NOT (%s::jsonb ? 'telegram_message_id')
                    OR transport_evidence->>'telegram_message_id' IS NULL
                    OR transport_evidence->>'telegram_message_id'=%s::jsonb->>'telegram_message_id')
                RETURNING *""",
                (json.dumps(evidence),operation_id,str(owner),json.dumps(evidence),json.dumps(evidence)))
            row=cursor.fetchone()
        return dict(row) if row else None

    def recover_expired_invocations(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_operator_message_operations
                SET state='AMBIGUOUS',ambiguous_at=NOW(),updated_at=NOW(),
                    last_error='transport_invocation_lease_expired'
                WHERE state='SENDING' AND transport_evidence ? 'invocation_owner'
                  AND (transport_evidence->>'lease_expires_at')::timestamptz<=NOW()
                RETURNING operation_id""")
            return cursor.fetchall()

    def confirmed(self, operation_id, message_id, *, owner=None):
        return self._state(operation_id,"CONFIRMED",message_id=message_id,owner=owner)
    def failed(self, operation_id, error, *, owner=None):
        return self._state(operation_id,"FAILED",error=error,owner=owner)
    def ambiguous(self, operation_id, error, *, owner=None):
        return self._state(operation_id,"AMBIGUOUS",error=error,owner=owner)

    def recent_confirmed_history(self, *, creator_profile_id, fanvue_account_id,
                                 telegram_user_id, telegram_chat_id, limit=10):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT message_text FROM public.telegram_operator_message_operations
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s
                  AND telegram_chat_id=%s AND state='CONFIRMED'
                ORDER BY confirmed_at DESC LIMIT %s""",
                (creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,limit))
            rows=cursor.fetchall()
        return [{"role":"assistant","content":row["message_text"],
                 "origin":"HUMAN_OPERATOR"} for row in reversed(rows)]

    def recent_confirmed_events(self, *, creator_profile_id, fanvue_account_id,
                                telegram_user_id, telegram_chat_id, limit=20):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT operation_id,telegram_chat_id,
                    outbound_telegram_message_id,message_text,confirmed_at
                FROM public.telegram_operator_message_operations
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND state='CONFIRMED' AND confirmed_at IS NOT NULL
                ORDER BY confirmed_at DESC,outbound_telegram_message_id DESC
                LIMIT %s""", (creator_profile_id,fanvue_account_id,
                    telegram_user_id,telegram_chat_id,max(1,int(limit))))
            rows=cursor.fetchall()
        return [{
            "event_id":f"operator:{row['operation_id']}",
            "occurred_at":row["confirmed_at"],
            "telegram_chat_id":int(row["telegram_chat_id"]),
            "telegram_message_id":row["outbound_telegram_message_id"],
            "role":"assistant","text":row["message_text"],
            "origin":"HUMAN_OPERATOR",
        } for row in reversed(rows)]

    def _state(self, operation_id, state, *, message_id=None, error=None, owner=None):
        column={"CONFIRMED":"confirmed_at","FAILED":"failed_at","AMBIGUOUS":"ambiguous_at"}[state]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""UPDATE public.telegram_operator_message_operations SET state=%s,
                outbound_telegram_message_id=COALESCE(%s,outbound_telegram_message_id),last_error=%s,
                {column}=NOW(),updated_at=NOW() WHERE operation_id=%s AND state='SENDING'
                AND transport_evidence->>'invocation_owner' IS NOT DISTINCT FROM %s
                AND (%s<>'CONFIRMED' OR (%s::text IS NOT NULL AND
                     transport_evidence->>'telegram_message_id'=%s::text))
                AND (%s<>'FAILED' OR NOT (transport_evidence ? 'telegram_message_id')) RETURNING *""",
                (state,message_id,str(error)[:500] if error else None,operation_id,
                 str(owner) if owner is not None else None,state,owner,str(message_id),state))
            row=cursor.fetchone()
            return dict(row) if row else None
