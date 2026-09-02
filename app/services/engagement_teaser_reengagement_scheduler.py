"""Safe outreach-queue scheduling for dormant Free Engagement Teaser candidates."""
from datetime import datetime, timezone

from app.database import get_db_connection


class EngagementTeaserReengagementScheduler:
    """Schedules policy-qualified work; it never calls Telegram or a provider."""
    OUTREACH_TYPE = "free_engagement_teaser_reengage"

    def __init__(self, *, policy_service, connection_factory=get_db_connection,
                 clock=None):
        self.policy = policy_service
        self.connection_factory = connection_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def schedule_due(self, *, limit=25):
        scheduled = []
        for candidate in self._candidates(limit):
            correlation = f"reengage:{candidate['fanvue_account_id']}:{candidate['fanvue_user_id']}:{candidate['last_inbound_at'].date()}"
            decision = self.policy.evaluate(
                creator_profile_id=candidate["creator_profile_id"],
                fanvue_account_id=candidate["fanvue_account_id"],
                fanvue_user_id=candidate["fanvue_user_id"],
                conversation_thread_id=candidate["conversation_thread_id"],
                correlation_id=correlation, trigger_type="SCHEDULED_REENGAGEMENT")
            if decision.decision != "SEND_FREE_ENGAGEMENT_TEASER":
                continue
            with self.connection_factory() as connection, connection.cursor() as cursor:
                cursor.execute("""INSERT INTO public.outreach_queue(
                        fanvue_account_id,fanvue_user_id,outreach_type,queue_status,scheduled_for)
                    SELECT %s,%s,%s,'pending',%s WHERE NOT EXISTS(
                        SELECT 1 FROM public.outreach_queue WHERE fanvue_account_id=%s
                          AND fanvue_user_id=%s AND outreach_type=%s
                          AND queue_status IN ('pending','processing')) RETURNING *""",
                    (candidate["fanvue_account_id"], candidate["fanvue_user_id"],
                     self.OUTREACH_TYPE, self.clock(), candidate["fanvue_account_id"],
                     candidate["fanvue_user_id"], self.OUTREACH_TYPE))
                row = cursor.fetchone()
            if row: scheduled.append(dict(row))
        return scheduled

    def _candidates(self, limit):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT DISTINCT ON (customer.id)
                    instruction.creator_profile_id,identity.fanvue_account_id,
                    customer.id fanvue_user_id,thread.id conversation_thread_id,
                    thread.last_inbound_at
                FROM public.ai_runtime_instructions instruction
                JOIN public.telegram_identity_map identity
                  ON identity.fanvue_account_id=instruction.fanvue_account_id
                 AND identity.is_active=TRUE AND identity.verification_status='VERIFIED'
                JOIN public.fanvue_users customer ON customer.id=identity.local_fanvue_user_id
                JOIN public.chat_threads thread ON thread.fanvue_account_id=identity.fanvue_account_id
                 AND thread.fanvue_user_id=customer.id
                WHERE instruction.status='ENABLED' AND instruction.instruction_type='ENGAGEMENT_RULE'
                  AND instruction.policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS'
                  AND thread.last_inbound_at<=NOW()-(COALESCE(
                    (instruction.policy_configuration->>'dormant_inactivity_days')::integer,21)*INTERVAL '1 day')
                  AND (SELECT COUNT(*) FROM public.chat_messages message
                       WHERE message.fanvue_account_id=identity.fanvue_account_id
                         AND message.fanvue_user_id=customer.id AND message.direction='inbound')
                      >=COALESCE((instruction.policy_configuration->>'meaningful_history_minimum_inbound_messages')::integer,8)
                ORDER BY customer.id,thread.last_inbound_at DESC LIMIT %s""", (int(limit),))
            return [dict(row) for row in cursor.fetchall()]
