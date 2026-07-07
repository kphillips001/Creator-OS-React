"""Asset lifecycle transitions for legacy content_items assets."""

from __future__ import annotations

import json

from app.database import get_db_connection
from app.services.media_processing_service import MediaProcessingService


class AssetLifecycleService:
    """Owns Asset review state transitions while content_items remains legacy."""

    def __init__(
        self,
        connection_factory=get_db_connection,
        media_processing_service: MediaProcessingService | None = None,
    ):
        self._connection_factory = connection_factory
        self.media_processing = media_processing_service or MediaProcessingService()

    def update_classification(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int | None = None,
        classification: str,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET classification = %s
                    WHERE id = %s
                    AND (%s IS NULL OR fanvue_account_id = %s)
                    """,
                    (
                        classification,
                        asset_id,
                        fanvue_account_id,
                        fanvue_account_id,
                    ),
                )

    def save_review_edits(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int | None = None,
        suggested_tags: list[str],
        detected_themes: list[str],
        classification: str,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        suggested_tags = %s::jsonb,
                        detected_themes = %s::jsonb,
                        classification = %s
                    WHERE id = %s
                    AND (%s IS NULL OR fanvue_account_id = %s)
                    """,
                    (
                        json.dumps(suggested_tags),
                        json.dumps(detected_themes),
                        classification,
                        asset_id,
                        fanvue_account_id,
                        fanvue_account_id,
                    ),
                )

    def approve_asset(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int | None = None,
        suggested_tags: list[str],
        detected_themes: list[str],
        classification: str,
        blurred_preview_path: str,
        creator_profile_id: int | None = None,
    ) -> None:
        derivative_metadata = self.media_processing.build_derivative_metadata(
            derivative_path=blurred_preview_path,
            derivative_type="blur",
        )
        derivative_updates = {
            "blur": derivative_metadata,
            "blurred_preview": derivative_metadata,
        }
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        suggested_tags = %s::jsonb,
                        detected_themes = %s::jsonb,
                        classification = %s,
                        status = 'approved',
                        blurred_preview_path = %s,
                        media_metadata = jsonb_set(
                            COALESCE(media_metadata, '{}'::jsonb),
                            '{derivatives}',
                            COALESCE(media_metadata->'derivatives', '{}'::jsonb)
                                || %s::jsonb,
                            true
                        ),
                        ready_for_rotation = TRUE,
                        creator_profile_id = COALESCE(
                            creator_profile_id,
                            %s
                        )
                    WHERE id = %s
                    AND (%s IS NULL OR fanvue_account_id = %s)
                    """,
                    (
                        json.dumps(suggested_tags),
                        json.dumps(detected_themes),
                        classification,
                        blurred_preview_path,
                        json.dumps(derivative_updates),
                        creator_profile_id,
                        asset_id,
                        fanvue_account_id,
                        fanvue_account_id,
                    ),
                )

    def approve_review_only(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int | None = None,
        suggested_tags: list[str],
        detected_themes: list[str],
        classification: str,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        suggested_tags = %s::jsonb,
                        detected_themes = %s::jsonb,
                        classification = %s,
                        status = 'approved'
                    WHERE id = %s
                    AND (%s IS NULL OR fanvue_account_id = %s)
                    """,
                    (
                        json.dumps(suggested_tags),
                        json.dumps(detected_themes),
                        classification,
                        asset_id,
                        fanvue_account_id,
                        fanvue_account_id,
                    ),
                )

    def reject_asset(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int | None = None,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET status = 'rejected'
                    WHERE id = %s
                    AND (%s IS NULL OR fanvue_account_id = %s)
                    """,
                    (asset_id, fanvue_account_id, fanvue_account_id),
                )
