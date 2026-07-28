"""Persistence for the account-scoped Creator World Model document."""

from collections.abc import Callable

from app.database import get_db_connection


class CreatorWorldModelRepository:
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
                    FROM public.creator_world_models
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
                    INSERT INTO public.creator_world_models (
                        creator_profile_id,
                        fanvue_account_id,
                        internal_home_base,
                        public_location_description,
                        home_and_indoor_environments,
                        coastal_environments,
                        mountains_lakes_and_small_town_escapes,
                        climate_and_seasonal_behavior,
                        seasonal_activities,
                        holiday_rhythm,
                        travel_and_variety_guidance
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (creator_profile_id)
                    DO UPDATE SET
                        internal_home_base = EXCLUDED.internal_home_base,
                        public_location_description =
                            EXCLUDED.public_location_description,
                        home_and_indoor_environments =
                            EXCLUDED.home_and_indoor_environments,
                        coastal_environments = EXCLUDED.coastal_environments,
                        mountains_lakes_and_small_town_escapes =
                            EXCLUDED.mountains_lakes_and_small_town_escapes,
                        climate_and_seasonal_behavior =
                            EXCLUDED.climate_and_seasonal_behavior,
                        seasonal_activities = EXCLUDED.seasonal_activities,
                        holiday_rhythm = EXCLUDED.holiday_rhythm,
                        travel_and_variety_guidance =
                            EXCLUDED.travel_and_variety_guidance,
                        updated_at = NOW()
                    WHERE creator_world_models.fanvue_account_id =
                          EXCLUDED.fanvue_account_id
                    RETURNING *
                    """,
                    (
                        int(creator_profile_id),
                        str(fanvue_account_id),
                        document["internal_home_base"],
                        document["public_location_description"],
                        document["home_and_indoor_environments"],
                        document["coastal_environments"],
                        document["mountains_lakes_and_small_town_escapes"],
                        document["climate_and_seasonal_behavior"],
                        document["seasonal_activities"],
                        document["holiday_rhythm"],
                        document["travel_and_variety_guidance"],
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(
                        "World Model belongs to another creator account."
                    )
                connection.commit()
                return dict(row)
