import hashlib
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

    def claim(self, operation_id, *, expected_version):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.telegram_operator_message_operations operation
                SET state='SENDING',send_attempt_count=send_attempt_count+1,sending_at=NOW(),updated_at=NOW()
                FROM public.telegram_relationship_controls control
                WHERE operation.operation_id=%s AND operation.state IN ('PREPARED','FAILED')
                  AND control.creator_profile_id=operation.creator_profile_id
                  AND control.fanvue_account_id=operation.fanvue_account_id
                  AND control.telegram_user_id=operation.telegram_user_id
                  AND control.mode='HUMAN_OPERATOR' AND control.control_version=%s
                  AND operation.relationship_control_version=control.control_version
                RETURNING operation.*""",(operation_id,expected_version))
            row=cursor.fetchone()
        return dict(row) if row else None

    def confirmed(self, operation_id, message_id): return self._state(operation_id,"CONFIRMED",message_id=message_id)
    def failed(self, operation_id, error): return self._state(operation_id,"FAILED",error=error)
    def ambiguous(self, operation_id, error): return self._state(operation_id,"AMBIGUOUS",error=error)

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

    def _state(self, operation_id, state, *, message_id=None, error=None):
        column={"CONFIRMED":"confirmed_at","FAILED":"failed_at","AMBIGUOUS":"ambiguous_at"}[state]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""UPDATE public.telegram_operator_message_operations SET state=%s,
                outbound_telegram_message_id=COALESCE(%s,outbound_telegram_message_id),last_error=%s,
                {column}=NOW(),updated_at=NOW() WHERE operation_id=%s RETURNING *""",
                (state,message_id,str(error)[:500] if error else None,operation_id))
            return dict(cursor.fetchone())
