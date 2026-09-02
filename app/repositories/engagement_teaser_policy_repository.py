"""PostgreSQL evidence and audit authority for Free Engagement Teaser policy."""
from uuid import uuid4

from psycopg.types.json import Json

from app.database import get_db_connection


class EngagementTeaserPolicyRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active_policy(self, *, creator_profile_id, fanvue_account_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.ai_runtime_instructions
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND scope='GLOBAL' AND instruction_type='ENGAGEMENT_RULE'
                  AND policy_key='INTELLIGENT_FREE_ENGAGEMENT_TEASERS'
                  AND enforcement_mode='BACKEND' AND status='ENABLED'
                ORDER BY priority,instruction_id LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id)))
            row = cursor.fetchone()
        return dict(row) if row else None

    def snapshot(self, *, creator_profile_id, fanvue_account_id,
                 fanvue_user_id, conversation_thread_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT
                  COUNT(*) FILTER (WHERE direction='inbound') inbound_count,
                  COUNT(*) FILTER (WHERE direction='outbound') outbound_count,
                  MAX(sent_at) FILTER (WHERE direction='inbound') last_inbound_at,
                  MAX(sent_at) last_conversation_at
                FROM public.chat_messages WHERE fanvue_account_id=%s
                  AND fanvue_user_id=%s""", (int(fanvue_account_id), int(fanvue_user_id)))
            messages = dict(cursor.fetchone())
            cursor.execute("""SELECT profile_state,purchase_count,lifetime_gross_minor,
                    first_seen_at,last_seen_at,last_purchase_at
                FROM public.customer_commerce_profiles
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND external_fanvue_user_uuid=(SELECT fanvue_user_uuid FROM public.fanvue_users WHERE id=%s)
                LIMIT 1""", (int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)))
            profile = dict(cursor.fetchone() or {})
            cursor.execute("""SELECT COUNT(*) sent_count,MAX(telegram_accepted_at) last_teaser_at,
                  ARRAY_REMOVE(ARRAY_AGG(telegram_accepted_at),NULL) teaser_sent_times,
                  COUNT(*) FILTER (WHERE conversation_thread_id=%s) sent_in_conversation
                FROM public.telegram_engagement_teaser_delivery_operations
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s
                  AND state IN ('TELEGRAM_ACCEPTED','CONFIRMED')""",
                (int(conversation_thread_id), int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)))
            deliveries = dict(cursor.fetchone())
            cursor.execute("""SELECT COUNT(*) inbound_since_teaser FROM public.chat_messages
                WHERE fanvue_account_id=%s AND fanvue_user_id=%s AND direction='inbound'
                  AND sent_at>COALESCE(%s,'-infinity'::timestamptz)""",
                (int(fanvue_account_id), int(fanvue_user_id), deliveries.get("last_teaser_at")))
            messages.update(profile); messages.update(deliveries); messages.update(cursor.fetchone())
            return messages

    def persist_decision(self, decision, *, correlation_id, creator_profile_id,
                         fanvue_account_id, fanvue_user_id,
                         conversation_thread_id, trigger_type,
                         selected_asset_id=None, operation_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.engagement_teaser_policy_decisions(
                    decision_id,correlation_id,creator_profile_id,fanvue_account_id,
                    fanvue_user_id,conversation_thread_id,trigger_type,decision,
                    engagement_strategy,reason_code,evidence,suppression_evidence,
                    policy_version,selected_asset_id,operation_id)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,correlation_id)
                DO UPDATE SET selected_asset_id=COALESCE(EXCLUDED.selected_asset_id,
                    engagement_teaser_policy_decisions.selected_asset_id),
                    operation_id=COALESCE(EXCLUDED.operation_id,
                    engagement_teaser_policy_decisions.operation_id)
                RETURNING decision_id""", (
                    uuid4(), str(correlation_id), int(creator_profile_id), int(fanvue_account_id),
                    int(fanvue_user_id), conversation_thread_id, str(trigger_type),
                    decision.decision, decision.strategy.value if decision.strategy else None,
                    decision.reason_code, Json(decision.evidence), Json(decision.suppression_evidence),
                    decision.policy_version, selected_asset_id, operation_id))
            return str(cursor.fetchone()["decision_id"])
