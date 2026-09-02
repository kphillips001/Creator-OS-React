"""Telethon-bound consumer for safely scheduled RE_ENGAGE teaser work."""
from uuid import uuid4

from app.database import get_db_connection


class ScheduledEngagementTeaserWorker:
    def __init__(self, *, orchestrator, connection_factory=get_db_connection,
                 worker_id=None):
        self.orchestrator = orchestrator
        self.connection_factory = connection_factory
        self.worker_id = worker_id or f"telegram-engagement-{uuid4()}"

    async def process_one(self, *, transport):
        item = self._claim()
        if item is None: return None
        try:
            result = await self.orchestrator.handle_scheduled_reengagement(
                queue_item=item, transport=transport)
            status = result.get("status")
            if status in {"CONFIRMED", "TELEGRAM_ACCEPTED"}:
                self._complete(item["id"])
            elif status == "SEND_NONE":
                self._complete(item["id"])
            else:
                self._fail(item["id"], str(result.get("reason") or status), retry=False)
            return result
        except Exception as error:
            self._fail(item["id"], type(error).__name__, retry=False)
            return {"status": "FAILED", "reason": type(error).__name__}

    def _claim(self):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""WITH candidate AS (
                  SELECT queue.id FROM public.outreach_queue queue
                  WHERE queue.outreach_type='free_engagement_teaser_reengage'
                    AND queue.queue_status='pending' AND queue.scheduled_for<=NOW()
                    AND (queue.next_retry_at IS NULL OR queue.next_retry_at<=NOW())
                  ORDER BY queue.scheduled_for,queue.id FOR UPDATE SKIP LOCKED LIMIT 1)
                UPDATE public.outreach_queue queue SET queue_status='processing',
                  worker_instance_id=%s,claim_expires_at=NOW()+INTERVAL '5 minutes',
                  started_at=NOW(),updated_at=NOW()
                FROM candidate WHERE queue.id=candidate.id RETURNING queue.*""", (self.worker_id,))
            row = cursor.fetchone()
            if row is None: return None
            cursor.execute("""SELECT identity.telegram_user_id,identity.telegram_chat_id,
                    instruction.creator_profile_id,thread.id conversation_thread_id
                FROM public.telegram_identity_map identity
                JOIN public.ai_runtime_instructions instruction
                  ON instruction.fanvue_account_id=identity.fanvue_account_id
                 AND instruction.instruction_type='ENGAGEMENT_RULE'
                 AND instruction.policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS'
                 AND instruction.status='ENABLED'
                JOIN public.chat_threads thread ON thread.fanvue_account_id=identity.fanvue_account_id
                 AND thread.fanvue_user_id=identity.local_fanvue_user_id
                WHERE identity.fanvue_account_id=%s AND identity.local_fanvue_user_id=%s
                  AND identity.is_active=TRUE AND identity.verification_status='VERIFIED'
                ORDER BY thread.id LIMIT 1""", (row["fanvue_account_id"], row["fanvue_user_id"]))
            context = cursor.fetchone()
            if context is None:
                cursor.execute("""UPDATE public.outreach_queue SET queue_status='failed',
                    error_message='IDENTITY_UNRESOLVED',failed_at=NOW(),updated_at=NOW()
                    WHERE id=%s""", (row["id"],)); return None
            return {**dict(row), **dict(context)}

    def _complete(self, queue_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.outreach_queue SET queue_status='completed',
                completed_at=NOW(),worker_instance_id=NULL,claim_expires_at=NULL,updated_at=NOW()
                WHERE id=%s AND worker_instance_id=%s""", (queue_id,self.worker_id))

    def _fail(self, queue_id, reason, *, retry):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.outreach_queue SET queue_status=%s,error_message=%s,
                failed_at=CASE WHEN %s='failed' THEN NOW() ELSE failed_at END,
                worker_instance_id=NULL,claim_expires_at=NULL,updated_at=NOW()
                WHERE id=%s AND worker_instance_id=%s""",
                ('pending' if retry else 'failed', str(reason)[:500],
                 'pending' if retry else 'failed', queue_id,self.worker_id))
