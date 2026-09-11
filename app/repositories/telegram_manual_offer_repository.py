import hashlib
import json
from uuid import uuid4

from app.database import get_db_connection


class TelegramManualOfferRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def customer_state(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT intent.commercial_offering_id,intent.purchase_intent_id,
                       intent.status,intent.presented_at,
                       EXISTS(SELECT 1 FROM telegram_sales_delivery_operations delivery
                         WHERE delivery.purchase_intent_id=intent.purchase_intent_id
                           AND delivery.state='CONFIRMED' AND delivery.confirmed_at IS NOT NULL)
                         AS confirmed_delivery,
                       COALESCE((SELECT delivery.delivery_payload#>>'{metadata,presentation_origin}'
                         FROM telegram_sales_delivery_operations delivery
                         WHERE delivery.purchase_intent_id=intent.purchase_intent_id
                           AND delivery.state='CONFIRMED' ORDER BY delivery.confirmed_at DESC LIMIT 1),
                         'AI_PRESENTED') presentation_origin
                  FROM purchase_intents intent
                 WHERE intent.creator_profile_id=%s AND intent.fanvue_account_id=%s
                   AND intent.telegram_user_id=%s ORDER BY intent.created_at DESC""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            intents=[dict(row) for row in cursor.fetchall()]
            cursor.execute("""SELECT DISTINCT commercial_offering_id FROM purchase_intents
                 WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s
                   AND status='PURCHASED' AND attribution_result='ATTRIBUTED'""",
                (creator_profile_id,fanvue_account_id,telegram_user_id))
            owned={str(row['commercial_offering_id']) for row in cursor.fetchall()}
        return intents,owned

    def reserve(self, *, context, offering, business_connection_id, idempotency_key,
                message_text, expected_control_version):
        canonical=json.dumps({"offering":str(offering["offering_id"]),"publication":str(offering["publication_id"]),
            "connection":business_connection_id,"text":message_text},sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO telegram_manual_offer_operations (
                operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
                telegram_identity_mapping_id,local_fanvue_user_id,conversation_thread_id,
                commercial_offering_id,commercial_publication_id,business_connection_id,
                idempotency_key,message_text,request_sha256,relationship_control_version)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
                DO UPDATE SET updated_at=telegram_manual_offer_operations.updated_at RETURNING *""",
                (uuid4(),context['creator_profile_id'],context['fanvue_account_id'],context['telegram_user_id'],
                 context['telegram_chat_id'],context['telegram_identity_mapping_id'],context['local_fanvue_user_id'],
                 context['conversation_thread_id'],offering['offering_id'],offering['publication_id'],
                 business_connection_id,idempotency_key,message_text,digest,expected_control_version))
            row=dict(cursor.fetchone())
        if row['request_sha256'] != digest:
            raise ValueError('Idempotency key was already used for a different offer.')
        return row

    def claim(self, operation_id, expected_version):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_manual_offer_operations operation SET state='SENDING',sending_at=NOW(),updated_at=NOW()
                FROM telegram_relationship_controls control WHERE operation.operation_id=%s
                  AND operation.state IN ('PREPARED','FAILED')
                  AND control.creator_profile_id=operation.creator_profile_id AND control.fanvue_account_id=operation.fanvue_account_id
                  AND control.telegram_user_id=operation.telegram_user_id AND control.mode='HUMAN_OPERATOR'
                  AND control.control_version=%s AND operation.relationship_control_version=control.control_version
                RETURNING operation.*""",(operation_id,expected_version))
            row=cursor.fetchone()
        return dict(row) if row else None

    def attach(self, operation_id, **values):
        allowed={'purchase_intent_id','sales_delivery_operation_id'}
        updates={key:value for key,value in values.items() if key in allowed}
        if not updates:return None
        assignments=','.join(f"{key}=%s" for key in updates)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"UPDATE telegram_manual_offer_operations SET {assignments},updated_at=NOW() WHERE operation_id=%s RETURNING *",
                (*updates.values(),operation_id))
            return dict(cursor.fetchone())

    def finish(self, operation_id, state, *, message_id=None, error=None):
        column={'CONFIRMED':'confirmed_at','FAILED':'failed_at','AMBIGUOUS':'ambiguous_at'}[state]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""UPDATE telegram_manual_offer_operations SET state=%s,
                outbound_telegram_message_id=COALESCE(%s,outbound_telegram_message_id),last_error=%s,
                {column}=NOW(),updated_at=NOW() WHERE operation_id=%s RETURNING *""",
                (state,message_id,str(error)[:500] if error else None,operation_id))
            return dict(cursor.fetchone())

    def attach(self, operation_id, *, purchase_intent_id=None, sales_delivery_operation_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_manual_offer_operations SET purchase_intent_id=COALESCE(%s,purchase_intent_id),
                sales_delivery_operation_id=COALESCE(%s,sales_delivery_operation_id),updated_at=NOW()
                WHERE operation_id=%s RETURNING *""",(purchase_intent_id,sales_delivery_operation_id,operation_id))
            return dict(cursor.fetchone())

    def finish(self, operation_id, state, *, message_id=None, error=None):
        column={'CONFIRMED':'confirmed_at','FAILED':'failed_at','AMBIGUOUS':'ambiguous_at'}[state]
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""UPDATE telegram_manual_offer_operations SET state=%s,outbound_telegram_message_id=COALESCE(%s,outbound_telegram_message_id),
                last_error=%s,{column}=NOW(),updated_at=NOW() WHERE operation_id=%s RETURNING *""",
                (state,message_id,str(error)[:500] if error else None,operation_id))
            return dict(cursor.fetchone())
