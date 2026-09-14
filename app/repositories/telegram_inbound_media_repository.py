"""Durable authority for private Telegram customer-media processing."""
from uuid import NAMESPACE_URL, uuid5

from app.database import get_db_connection


class TelegramInboundMediaRepository:
    TERMINAL = frozenset({"READY_FOR_ANALYSIS", "UNSUPPORTED", "OVERSIZED", "DOWNLOAD_FAILED", "DECODE_FAILED", "FAILED"})

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def receive(self, *, creator_profile_id, fanvue_account_id, payload):
        grouped = next((a.grouped_id for a in payload.attachments if a.grouped_id), None)
        logical = f"group:{grouped}" if grouped else f"message:{payload.message_id}"
        operation_id = uuid5(NAMESPACE_URL, f"telegram-inbound-media:{creator_profile_id}:{fanvue_account_id}:{payload.telegram_chat_id}:{logical}")
        with self.connection_factory() as c, c.cursor() as q:
            q.execute("""INSERT INTO telegram_inbound_media_operations(operation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,telegram_user_id,logical_turn_key,grouped_id,caption_text,state,received_at)
              VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'RECEIVED',%s)
              ON CONFLICT(creator_profile_id,fanvue_account_id,logical_turn_key) DO UPDATE SET
                caption_text=CASE WHEN EXCLUDED.caption_text<>'' THEN EXCLUDED.caption_text ELSE telegram_inbound_media_operations.caption_text END,
                updated_at=NOW() RETURNING *""", (operation_id,creator_profile_id,fanvue_account_id,payload.telegram_chat_id,payload.telegram_user_id,logical,grouped,payload.message_text,payload.received_at))
            operation=q.fetchone()
            for position, attachment in enumerate(sorted(payload.attachments,key=lambda item:item.telegram_message_id)):
                q.execute("""INSERT INTO telegram_inbound_media_attachments(attachment_id,operation_id,telegram_message_id,telegram_media_id,media_kind,grouped_id,position,telegram_mime_type,original_filename,reported_size_bytes,reported_width,reported_height,state)
                  VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'RECEIVED')
                  ON CONFLICT(operation_id,telegram_message_id,telegram_media_id) DO NOTHING""",(attachment.attachment_id,operation['operation_id'],attachment.telegram_message_id,attachment.telegram_media_id,attachment.media_kind,attachment.grouped_id,position,attachment.mime_type,attachment.original_filename,attachment.reported_size_bytes,attachment.width,attachment.height))
            return operation

    def attachments(self, operation_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("SELECT * FROM telegram_inbound_media_attachments WHERE operation_id=%s ORDER BY telegram_message_id,telegram_media_id",(operation_id,));return q.fetchall()

    def transition_attachment(self, attachment_id, state, **values):
        allowed={"actual_size_bytes","detected_format","detected_mime_type","decoded_width","decoded_height","normalized_path","content_sha256","failure_category","downloaded_at","validated_at","ready_at"}
        updates={k:v for k,v in values.items() if k in allowed}
        assignments=["state=%s","updated_at=NOW()"]+[f"{key}=%s" for key in updates]
        params=[state,*updates.values(),attachment_id]
        with self.connection_factory() as c,c.cursor() as q:
            q.execute(f"UPDATE telegram_inbound_media_attachments SET {','.join(assignments)} WHERE attachment_id=%s RETURNING *",params);return q.fetchone()

    def refresh_operation(self, operation_id, *, retention_hours=24):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""UPDATE telegram_inbound_media_operations operation SET state=CASE
              WHEN operation.state IN ('SAFETY_ANALYZING','SAFETY_CLASSIFIED') THEN operation.state
              ELSE summary.state END,
              failure_category=summary.failure,ready_at=CASE WHEN summary.state='READY_FOR_ANALYSIS' THEN NOW() ELSE ready_at END,
              retention_expires_at=CASE WHEN summary.terminal THEN NOW()+(%s*INTERVAL '1 hour') ELSE NULL END,updated_at=NOW()
              FROM (SELECT operation_id,
                CASE WHEN bool_and(state='READY_FOR_ANALYSIS') THEN 'READY_FOR_ANALYSIS'
                     WHEN bool_or(state NOT IN ('READY_FOR_ANALYSIS','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')) THEN 'DOWNLOADING'
                     WHEN bool_or(state='READY_FOR_ANALYSIS') THEN 'READY_FOR_ANALYSIS' ELSE 'FAILED' END state,
                bool_and(state IN ('READY_FOR_ANALYSIS','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')) terminal,
                string_agg(DISTINCT failure_category,',' ORDER BY failure_category) FILTER(WHERE failure_category IS NOT NULL) failure
                FROM telegram_inbound_media_attachments WHERE operation_id=%s GROUP BY operation_id) summary
              WHERE operation.operation_id=summary.operation_id RETURNING operation.*""",(retention_hours,operation_id));return q.fetchone()

    def expired_artifacts(self):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""SELECT attachment_id,normalized_path FROM telegram_inbound_media_attachments attachment JOIN telegram_inbound_media_operations operation USING(operation_id)
              WHERE operation.retention_expires_at<=NOW()
                AND operation.state IN ('SAFETY_CLASSIFIED','SAFETY_FAILED','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')
                AND attachment.state IN ('READY_FOR_ANALYSIS','UNSUPPORTED','OVERSIZED','DOWNLOAD_FAILED','DECODE_FAILED','FAILED')
                AND attachment.normalized_path IS NOT NULL""");return q.fetchall()

    def clear_artifact(self, attachment_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("UPDATE telegram_inbound_media_attachments SET normalized_path=NULL,updated_at=NOW() WHERE attachment_id=%s",(attachment_id,))
