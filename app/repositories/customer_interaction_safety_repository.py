from uuid import uuid4

from app.database import get_db_connection


class CustomerInteractionSafetyRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get(self, *, creator_profile_id: int, fanvue_account_id: int, fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.customer_interaction_safety_states
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s""",
                (creator_profile_id, fanvue_account_id, fanvue_user_id),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def set_status(self, *, creator_profile_id: int, fanvue_account_id: int,
                   fanvue_user_id: int, safety_status: str, reason: str,
                   actor_identifier: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.customer_interaction_safety_states
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s
                   FOR UPDATE""", (creator_profile_id, fanvue_account_id, fanvue_user_id),
            )
            previous = cursor.fetchone()
            state_id = previous["safety_state_id"] if previous else uuid4()
            cursor.execute(
                """INSERT INTO public.customer_interaction_safety_states(
                       safety_state_id,creator_profile_id,fanvue_account_id,fanvue_user_id,
                       safety_status,reason,source)
                   VALUES(%s,%s,%s,%s,%s,%s,'OPERATOR')
                   ON CONFLICT(creator_profile_id,fanvue_account_id,fanvue_user_id)
                   DO UPDATE SET safety_status=EXCLUDED.safety_status,reason=EXCLUDED.reason,
                     source='OPERATOR',effective_at=NOW(),updated_at=NOW()
                   RETURNING *""",
                (state_id, creator_profile_id, fanvue_account_id, fanvue_user_id,
                 safety_status, reason),
            )
            row = cursor.fetchone()
            cursor.execute(
                """INSERT INTO public.customer_interaction_safety_history(
                       history_id,safety_state_id,creator_profile_id,fanvue_account_id,
                       fanvue_user_id,previous_status,new_status,reason,source,actor_identifier)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,'OPERATOR',%s)""",
                (uuid4(), row["safety_state_id"], creator_profile_id, fanvue_account_id,
                 fanvue_user_id, previous["safety_status"] if previous else None,
                 safety_status, reason, actor_identifier),
            )
            return dict(row)

    def history(self, *, creator_profile_id: int, fanvue_account_id: int, fanvue_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.customer_interaction_safety_history
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s AND fanvue_user_id=%s
                   ORDER BY created_at DESC""", (creator_profile_id, fanvue_account_id, fanvue_user_id),
            )
            return [dict(row) for row in cursor.fetchall()]
