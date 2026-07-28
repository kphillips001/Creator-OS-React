"""Persistence for the account-scoped Creator Lifestyle document."""

from collections.abc import Callable

from app.database import get_db_connection


class CreatorLifestyleRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def get(
        self,
        *,
        creator_profile_id: int,
        fanvue_account_id: str,
    ) -> dict | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.creator_lifestyles
                    WHERE creator_profile_id = %s
                      AND fanvue_account_id = %s
                    LIMIT 1
                    """,
                    (int(creator_profile_id), str(fanvue_account_id)),
                )
                row = cursor.fetchone()
                return dict(row) if row else None

    def save(
        self,
        *,
        creator_profile_id: int,
        fanvue_account_id: str,
        document: dict,
    ) -> dict:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.creator_lifestyles (
                        creator_profile_id,
                        fanvue_account_id,
                        career,
                        lifestyle_overview,
                        favorite_activities,
                        weekend_escapes,
                        small_town_roots,
                        outdoor_lifestyle,
                        personal_style
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (creator_profile_id)
                    DO UPDATE SET
                        career = EXCLUDED.career,
                        lifestyle_overview = EXCLUDED.lifestyle_overview,
                        favorite_activities = EXCLUDED.favorite_activities,
                        weekend_escapes = EXCLUDED.weekend_escapes,
                        small_town_roots = EXCLUDED.small_town_roots,
                        outdoor_lifestyle = EXCLUDED.outdoor_lifestyle,
                        personal_style = EXCLUDED.personal_style,
                        updated_at = NOW()
                    WHERE creator_lifestyles.fanvue_account_id =
                          EXCLUDED.fanvue_account_id
                    RETURNING *
                    """,
                    (
                        int(creator_profile_id),
                        str(fanvue_account_id),
                        document["career"],
                        document["lifestyle_overview"],
                        document["favorite_activities"],
                        document["weekend_escapes"],
                        document["small_town_roots"],
                        document["outdoor_lifestyle"],
                        document["personal_style"],
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(
                        "Lifestyle document belongs to another creator account."
                    )
                connection.commit()
                return dict(row)
