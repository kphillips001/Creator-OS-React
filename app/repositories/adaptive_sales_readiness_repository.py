"""Durable warm-up projection and explainability evidence repository."""
from datetime import timedelta
from uuid import uuid4

from psycopg.types.json import Json

from app.database import get_db_connection


class AdaptiveSalesReadinessRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active_policy(self, *, creator_profile_id, fanvue_account_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM public.ai_runtime_instructions
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND scope='GLOBAL' AND instruction_type='SALES_RULE'
                  AND policy_key='ADAPTIVE_SALES_READINESS'
                  AND enforcement_mode='BACKEND' AND status='ENABLED'
                ORDER BY priority,instruction_id LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id)))
            row = cursor.fetchone()
        return dict(row) if row else None

    def snapshot(self, *, creator_profile_id, fanvue_account_id, fanvue_user_id,
                 conversation_thread_id, meaningful_inactivity_days=7):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT sent_at FROM public.chat_messages
                WHERE fanvue_account_id=%s AND fanvue_user_id=%s
                  AND direction='inbound' ORDER BY sent_at,id""",
                (int(fanvue_account_id), int(fanvue_user_id)))
            inbound = [row["sent_at"] for row in cursor.fetchall()]
            episode_start = inbound[0] if inbound else None
            for previous, current in zip(inbound, inbound[1:]):
                if current - previous >= timedelta(days=int(meaningful_inactivity_days)):
                    episode_start = current
            cursor.execute("""SELECT
                  MAX(pi.presented_at) offer_boundary,
                  MAX(pi.updated_at) FILTER (WHERE pi.status IN ('PURCHASED','ABANDONED')) outcome_boundary
                FROM public.purchase_intents pi
                WHERE pi.creator_profile_id=%s AND pi.fanvue_account_id=%s
                  AND pi.telegram_user_id=(SELECT telegram_user_id FROM public.telegram_identity_map
                    WHERE fanvue_account_id=%s AND local_fanvue_user_id=%s LIMIT 1)""",
                (int(creator_profile_id), int(fanvue_account_id), int(fanvue_account_id), int(fanvue_user_id)))
            boundaries = dict(cursor.fetchone() or {})
            cursor.execute("""SELECT MAX(started_at) session_boundary
                FROM public.sales_sessions WHERE creator_profile_id=%s
                  AND fanvue_account_id=%s AND fanvue_user_id=%s""",
                (int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)))
            boundaries.update(dict(cursor.fetchone() or {}))
            candidates = [value for value in (episode_start, boundaries.get("offer_boundary"),
                                               boundaries.get("outcome_boundary"),
                                               boundaries.get("session_boundary")) if value]
            window_start = max(candidates) if candidates else None
            warmup = sum(1 for value in inbound if window_start is None or value >= window_start)
            cursor.execute("""SELECT engagement_strategy AS strategy,next_inbound_at,response_latency_seconds,
                    response_attribution
                FROM public.telegram_engagement_teaser_delivery_operations
                WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s
                  AND state IN ('TELEGRAM_ACCEPTED','CONFIRMED')
                ORDER BY telegram_accepted_at DESC LIMIT 1""",
                (int(creator_profile_id), int(fanvue_account_id), int(fanvue_user_id)))
            teaser = dict(cursor.fetchone() or {})
        return {"warmup_depth": warmup, "lifetime_inbound_depth": len(inbound),
                "window_started_at": window_start, "teaser_response": teaser}

    def persist_decision(self, decision, *, correlation_id, creator_profile_id,
                         fanvue_account_id, fanvue_user_id, conversation_thread_id,
                         selected_offering_id=None, selected_publication_id=None,
                         resulting_sales_action=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""INSERT INTO public.sales_readiness_decisions(
                decision_id,correlation_id,creator_profile_id,fanvue_account_id,
                fanvue_user_id,conversation_thread_id,warmup_depth,customer_segment,
                benchmark_position,direct_intent,strong_readiness,decision,reason_code,
                evidence,suppression_evidence,policy_version,selected_offering_id,
                selected_publication_id,resulting_sales_action)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (creator_profile_id,fanvue_account_id,correlation_id)
                DO UPDATE SET resulting_sales_action=EXCLUDED.resulting_sales_action,
                  selected_offering_id=COALESCE(EXCLUDED.selected_offering_id,sales_readiness_decisions.selected_offering_id),
                  selected_publication_id=COALESCE(EXCLUDED.selected_publication_id,sales_readiness_decisions.selected_publication_id)
                RETURNING decision_id""", (
                uuid4(), str(correlation_id), int(creator_profile_id), int(fanvue_account_id),
                int(fanvue_user_id), int(conversation_thread_id), decision.warmup_depth,
                decision.segment, decision.benchmark_position, decision.direct_intent,
                decision.strong_readiness, "AUTHORIZE_COMMERCIAL_PROGRESSION" if decision.authorized else "CONTINUE_CONVERSATION",
                decision.reason_code, Json(decision.evidence), Json(decision.suppression_evidence),
                decision.policy_version, selected_offering_id, selected_publication_id,
                resulting_sales_action))
            return str(cursor.fetchone()["decision_id"])
