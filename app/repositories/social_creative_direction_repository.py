"""Persistence for the account-scoped Social Creative Direction document."""

from collections.abc import Callable

from app.database import get_db_connection


class SocialCreativeDirectionRepository:
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
                    FROM public.social_creative_directions
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
                    INSERT INTO public.social_creative_directions (
                        creator_profile_id,
                        fanvue_account_id,
                        purpose,
                        wardrobe,
                        visual_style,
                        seasonal_guidance,
                        things_to_avoid
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (creator_profile_id)
                    DO UPDATE SET
                        purpose = EXCLUDED.purpose,
                        wardrobe = EXCLUDED.wardrobe,
                        visual_style = EXCLUDED.visual_style,
                        seasonal_guidance = EXCLUDED.seasonal_guidance,
                        things_to_avoid = EXCLUDED.things_to_avoid,
                        updated_at = NOW()
                    WHERE social_creative_directions.fanvue_account_id =
                          EXCLUDED.fanvue_account_id
                    RETURNING *
                    """,
                    (
                        int(creator_profile_id),
                        str(fanvue_account_id),
                        document["purpose"],
                        document["wardrobe"],
                        document["visual_style"],
                        document["seasonal_guidance"],
                        document["things_to_avoid"],
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError(
                        "Social Creative Direction belongs to another creator account."
                    )
                connection.commit()
                return dict(row)
