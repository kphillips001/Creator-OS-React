"""Durable, idempotent authority for customer-image safety decisions."""
from __future__ import annotations

from datetime import timedelta
from uuid import NAMESPACE_URL, uuid5

from app.database import get_db_connection


class CustomerInboundImageSafetyRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def schedule_and_claim(self, operation_id, *, grouped: bool, window_ms: int,
                           safety_lease_seconds: int = 300):
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""UPDATE telegram_inbound_media_operations SET
              album_finalize_after=COALESCE(album_finalize_after,NOW()+(%s*INTERVAL '1 millisecond')),
              updated_at=NOW() WHERE operation_id=%s RETURNING *""",
              (window_ms if grouped else 0, operation_id))
            operation=q.fetchone()
            if not operation or operation['album_finalize_after'] > __import__('datetime').datetime.now(__import__('datetime').timezone.utc):
                return operation,False
            q.execute("""UPDATE telegram_inbound_media_operations SET state='SAFETY_ANALYZING',
              safety_started_at=COALESCE(safety_started_at,NOW()),finalized_at=COALESCE(finalized_at,NOW()),updated_at=NOW()
              WHERE operation_id=%s AND (state='READY_FOR_ANALYSIS' OR
                (state='SAFETY_ANALYZING' AND safety_started_at<=NOW()-(%s*INTERVAL '1 second')))
              RETURNING *""",(operation_id,safety_lease_seconds))
            return operation,bool(q.fetchone())

    def ready_attachments(self, operation_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""SELECT attachment_id,position,normalized_path FROM telegram_inbound_media_attachments
              WHERE operation_id=%s AND state='READY_FOR_ANALYSIS' ORDER BY position,telegram_message_id,telegram_media_id""",(operation_id,));return q.fetchall()

    def attachment_states(self, operation_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("SELECT state FROM telegram_inbound_media_attachments WHERE operation_id=%s",(operation_id,));return tuple(row['state'] for row in q.fetchall())

    def existing_results(self, operation_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("SELECT * FROM telegram_inbound_media_safety_results WHERE operation_id=%s ORDER BY position,attachment_id",(operation_id,));return q.fetchall()

    def save_result(self, *, operation_id, position, result):
        result_id=uuid5(NAMESPACE_URL,f"telegram-media-safety:{result.attachment_id}")
        labels=self.serialized_labels(result.labels)
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""INSERT INTO telegram_inbound_media_safety_results(
              safety_result_id,operation_id,attachment_id,position,safety_state,classifier,classifier_version,relevant_labels,classified_at)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
              ON CONFLICT(attachment_id) DO NOTHING RETURNING *""",
              (result_id,operation_id,result.attachment_id,position,result.state.value,result.classifier,result.classifier_version,__import__('json').dumps(labels),result.classified_at))
            return q.fetchone()

    @staticmethod
    def serialized_labels(items):
        return [{'label':item.label,'confidence':item.confidence,
                 'threshold':item.threshold} for item in items]

    def boundary_count(self, *, creator_profile_id, fanvue_account_id, telegram_user_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""SELECT count(*) n FROM telegram_explicit_boundary_events WHERE
              creator_profile_id=%s AND fanvue_account_id=%s AND telegram_user_id=%s AND delivered_at>=NOW()-INTERVAL '30 days'""",
              (creator_profile_id,fanvue_account_id,telegram_user_id));return q.fetchone()['n']

    def finish(self, operation_id, *, state, solicitation, policy, partial_failure):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""UPDATE telegram_inbound_media_operations SET state='SAFETY_CLASSIFIED',
              safety_state=%s,solicitation_state=%s,response_policy=%s,partial_failure=%s,
              safety_classified_at=NOW(),updated_at=NOW() WHERE operation_id=%s RETURNING *""",
              (state,solicitation,policy,partial_failure,operation_id));return q.fetchone()

    def fail(self, operation_id, category):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("UPDATE telegram_inbound_media_operations SET state='SAFETY_FAILED',failure_category=%s,updated_at=NOW() WHERE operation_id=%s",(category,operation_id))

    def response_recovery_candidates(self, *, account_scope, limit=25):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""SELECT operation.*,
              MIN(attachment.telegram_message_id) AS canonical_message_id
              FROM telegram_inbound_media_operations operation
              JOIN telegram_inbound_media_attachments attachment USING(operation_id)
              WHERE operation.state='SAFETY_CLASSIFIED' AND (NOT EXISTS(
                SELECT 1 FROM ordinary_chat_reply_operations reply
                WHERE reply.telegram_account_scope=%s
                  AND reply.telegram_chat_id=operation.telegram_chat_id
                  AND reply.inbound_telegram_message_id=(SELECT MIN(a.telegram_message_id)
                    FROM telegram_inbound_media_attachments a WHERE a.operation_id=operation.operation_id)
                  AND reply.state IN ('SENT_CONFIRMED','SEND_UNCERTAIN','TERMINAL_FAILED','SUPPRESSED','SENDING'))
                OR (operation.response_policy IN ('POLITE_EXPLICIT_BOUNDARY','FIRM_EXPLICIT_BOUNDARY')
                  AND NOT EXISTS(SELECT 1 FROM telegram_explicit_boundary_events event
                    WHERE event.operation_id=operation.operation_id)
                  AND EXISTS(SELECT 1 FROM ordinary_chat_reply_operations reply
                    WHERE reply.telegram_account_scope=%s
                      AND reply.telegram_chat_id=operation.telegram_chat_id
                      AND reply.inbound_telegram_message_id=(SELECT MIN(a.telegram_message_id)
                        FROM telegram_inbound_media_attachments a WHERE a.operation_id=operation.operation_id)
                      AND reply.state='SENT_CONFIRMED')))
              GROUP BY operation.operation_id ORDER BY operation.safety_classified_at
              LIMIT %s""",(account_scope,account_scope,max(1,int(limit))));return q.fetchall()

    def record_boundary_delivered(self, *, operation_id, creator_profile_id,
                                  fanvue_account_id, telegram_user_id, policy,
                                  delivered_at):
        event_id=uuid5(NAMESPACE_URL,f"telegram-explicit-boundary:{operation_id}")
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""INSERT INTO telegram_explicit_boundary_events(
              boundary_event_id,operation_id,creator_profile_id,fanvue_account_id,
              telegram_user_id,policy,delivered_at) VALUES(%s,%s,%s,%s,%s,%s,%s)
              ON CONFLICT(operation_id) DO NOTHING RETURNING *""",
              (event_id,operation_id,creator_profile_id,fanvue_account_id,
               telegram_user_id,policy,delivered_at));return q.fetchone()
