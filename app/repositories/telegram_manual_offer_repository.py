import hashlib
import json
from uuid import uuid4

from app.database import get_db_connection


class TelegramManualOfferRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def by_key(self, *, context, idempotency_key):
        with self.connection_factory() as c:
            row=c.execute("""SELECT * FROM telegram_manual_offer_operations WHERE creator_profile_id=%s
                AND fanvue_account_id=%s AND telegram_user_id=%s AND idempotency_key=%s""",
                (context['creator_profile_id'],context['fanvue_account_id'],context['telegram_user_id'],idempotency_key)).fetchone()
            return dict(row) if row else None

    DISPATCH_PENDING = 'CAPABILITY_OFFER_DISPATCH_PENDING'

    def get(self, operation_id):
        with self.connection_factory() as c:
            row = c.execute('SELECT * FROM telegram_manual_offer_operations WHERE operation_id=%s',
                            (operation_id,)).fetchone()
            return dict(row) if row else None

    def quarantine_stale_dispatches(self):
        # Only this extension's orphaned claims; never replay or alter older operations.
        with self.connection_factory() as c:
            return c.execute("""UPDATE telegram_manual_offer_operations SET state='AMBIGUOUS',
                ambiguous_at=NOW(),updated_at=NOW(),last_error='Dispatch interrupted; reconcile, never resend.'
                WHERE state='SENDING' AND last_error=%s
                AND sending_at<NOW()-INTERVAL '5 minutes' RETURNING operation_id""",
                (self.DISPATCH_PENDING,)).fetchall()

    def pending_private_dispatches(self, limit=10):
        with self.connection_factory() as c:
            return [dict(row) for row in c.execute("""SELECT * FROM telegram_manual_offer_operations
                WHERE state='PREPARED' AND last_error=%s ORDER BY created_at,operation_id LIMIT %s""",
                (self.DISPATCH_PENDING, max(1, int(limit)))).fetchall()]

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
                message_text, expected_control_version, queued=False):
        canonical=json.dumps({"offering":str(offering["offering_id"]),"publication":str(offering["publication_id"]),
            "connection":business_connection_id,"text":message_text,
            "price_minor":offering["price_minor"],"currency":offering["currency"]},sort_keys=True,separators=(",",":"))
        digest=hashlib.sha256(canonical.encode()).hexdigest()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",(f"manual-offer:{context['creator_profile_id']}:{context['fanvue_account_id']}:{context['telegram_user_id']}",))
            cursor.execute("""SELECT * FROM telegram_manual_offer_operations WHERE creator_profile_id=%s
                AND fanvue_account_id=%s AND telegram_user_id=%s AND idempotency_key=%s""",
                (context['creator_profile_id'],context['fanvue_account_id'],context['telegram_user_id'],idempotency_key))
            existing=cursor.fetchone()
            if existing:
                if existing['request_sha256']!=digest:raise ValueError('Idempotency key was already used for a different offer.')
                return dict(existing)
            cursor.execute("""SELECT 1 FROM telegram_manual_offer_operations WHERE creator_profile_id=%s
                AND fanvue_account_id=%s AND telegram_user_id=%s AND state IN ('PREPARED','SENDING','AMBIGUOUS')""",
                (context['creator_profile_id'],context['fanvue_account_id'],context['telegram_user_id']))
            if cursor.fetchone():raise ValueError('An unresolved manual offer already exists; reconciliation is required.')
            cursor.execute("""INSERT INTO telegram_manual_offer_operations (
                operation_id,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,
                telegram_identity_mapping_id,local_fanvue_user_id,conversation_thread_id,
                commercial_offering_id,commercial_publication_id,business_connection_id,
                idempotency_key,message_text,request_sha256,relationship_control_version,last_error)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,telegram_user_id,idempotency_key)
                DO UPDATE SET updated_at=telegram_manual_offer_operations.updated_at RETURNING *""",
                (uuid4(),context['creator_profile_id'],context['fanvue_account_id'],context['telegram_user_id'],
                 context['telegram_chat_id'],context.get('telegram_identity_mapping_id'),context.get('local_fanvue_user_id'),
                 context['conversation_thread_id'],offering['offering_id'],offering['publication_id'],
                 business_connection_id,idempotency_key,message_text,digest,expected_control_version,
                 self.DISPATCH_PENDING if queued else None))
            row=dict(cursor.fetchone())
        if row['request_sha256'] != digest:
            raise ValueError('Idempotency key was already used for a different offer.')
        return row

    def claim(self, operation_id, expected_version):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_manual_offer_operations operation SET state='SENDING',sending_at=NOW(),updated_at=NOW(),send_attempt_count=send_attempt_count+1
                FROM telegram_relationship_controls control WHERE operation.operation_id=%s
                  AND operation.state='PREPARED'
                  AND control.communication_disposition='ACTIVE' AND control.content_selling_enabled=TRUE
                  AND control.creator_profile_id=operation.creator_profile_id AND control.fanvue_account_id=operation.fanvue_account_id
                  AND control.telegram_user_id=operation.telegram_user_id AND control.mode='HUMAN_OPERATOR'
                  AND control.control_version=%s AND operation.relationship_control_version=control.control_version
                RETURNING operation.*""",(operation_id,expected_version))
            row=cursor.fetchone()
        return dict(row) if row else None

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
