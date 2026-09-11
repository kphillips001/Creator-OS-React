"""Account-scoped visibility boundary for the operator-facing AI Training History."""
from uuid import uuid4

from app.database import get_db_connection


class AiTrainingHistoryBaselineRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get(self, *, creator_profile_id, fanvue_account_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT baseline.*,
                          COALESCE(ARRAY_AGG(retained.instruction_id)
                            FILTER (WHERE retained.instruction_id IS NOT NULL),'{}') AS retained_instruction_ids
                   FROM public.ai_training_history_baselines baseline
                   LEFT JOIN public.ai_training_history_baseline_retained_instructions retained
                     USING (baseline_id)
                   WHERE baseline.creator_profile_id=%s AND baseline.fanvue_account_id=%s
                   GROUP BY baseline.baseline_id""",
                (creator_profile_id, fanvue_account_id),
            )
            return cursor.fetchone()

    def establish(self, *, creator_profile_id, fanvue_account_id, baseline_at, retained_instruction_ids):
        baseline_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.ai_training_history_baselines(
                       baseline_id,creator_profile_id,fanvue_account_id,baseline_at)
                   VALUES(%s,%s,%s,%s)
                   ON CONFLICT (creator_profile_id,fanvue_account_id) DO NOTHING
                   RETURNING baseline_id""",
                (baseline_id, creator_profile_id, fanvue_account_id, baseline_at),
            )
            inserted = cursor.fetchone()
            if inserted:
                for instruction_id in retained_instruction_ids:
                    cursor.execute(
                        """INSERT INTO public.ai_training_history_baseline_retained_instructions(
                               baseline_id,instruction_id) VALUES(%s,%s)""",
                        (baseline_id, instruction_id),
                    )
        return self.get(creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id)
