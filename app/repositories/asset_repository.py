"""Access to legacy content through the normalized Asset model."""

import json
from collections.abc import Callable, Iterable
from typing import Any, Mapping

from app.database import get_db_connection
from app.models.asset import ASSET_OWNED_FIELDS, Asset


# A.2 ownership boundary:
# Asset-owned fields describe imported media, Local Vault metadata, derivatives,
# AI analysis, safety metadata, and review/archive state.
#
# Product-owned compatibility fields still selected here:
# ready_for_rotation, upload_intent, content_tier, distribution_type.
#
# Publishing-owned compatibility fields still selected here:
# fanvue_media_preview_uuid, fanvue_media_full_uuid, fanvue_upload_status,
# fanvue_upload_error.
#
# Keep this read model broad until Product readiness and provider publishing
# state are extracted from content_items in later A.2 phases.
_ASSET_COLUMNS = """
    id, file_path, file_name, classification, confidence, status, is_active, is_test,
    ready_for_rotation, upload_intent, content_tier, distribution_type,
    blurred_preview_path, suggested_tags, detected_themes, is_explicit,
    fanvue_media_preview_uuid, fanvue_media_full_uuid, fanvue_upload_status,
    fanvue_upload_error, created_at,
    short_safe_summary, risk_flags, analysis_reasoning, analysis_provenance,
    media_metadata, local_vault_path, creator_profile_id, nudity_labels, nudity_level,
    sexual_intensity, gpt_vision_result, nudenet_result, classification_result
"""

_CONTENT_ITEM_COLUMN_CACHE: set[str] | None = None


class AssetRepository:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    def _existing_content_item_columns(self, connection) -> set[str]:
        global _CONTENT_ITEM_COLUMN_CACHE
        if _CONTENT_ITEM_COLUMN_CACHE is not None:
            return _CONTENT_ITEM_COLUMN_CACHE

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'content_items'
                """
            )
            _CONTENT_ITEM_COLUMN_CACHE = {
                row["column_name"] for row in cursor.fetchall()
            }
        return _CONTENT_ITEM_COLUMN_CACHE

    def _asset_owned_columns(self, connection) -> tuple[str, ...]:
        existing_columns = self._existing_content_item_columns(connection)
        return tuple(
            column
            for column in ASSET_OWNED_FIELDS
            if column in existing_columns
        )

    def get_asset_owned_row(
        self,
        asset_id: int,
        *,
        connection=None,
    ) -> dict | None:
        """
        Return only Asset-owned content_items fields.

        This is the A.2 Asset-focused read boundary. It intentionally returns a
        dict instead of the broad Asset compatibility model because Asset still
        exposes Product and Publishing fields for existing workflows.
        """

        if connection is not None:
            columns = self._asset_owned_columns(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {", ".join(columns)}
                    FROM public.content_items
                    WHERE id = %s
                    """,
                    (asset_id,),
                )
                row = cursor.fetchone()
            return dict(row) if row else None
        with self._connection_factory() as conn:
            return self.get_asset_owned_row(asset_id, connection=conn)

    def list_asset_owned_rows(
        self,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> list[dict]:
        """
        Return only Asset-owned fields for the requested assets.

        Existing list_by_ids remains the compatibility method for Product and
        Publishing consumers that still need mixed lifecycle fields.
        """

        ids = list(asset_ids)
        if not ids:
            return []
        if connection is not None:
            columns = self._asset_owned_columns(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {", ".join(columns)}
                    FROM public.content_items
                    WHERE id = ANY(%s)
                    """,
                    (ids,),
                )
                by_id = {row["id"]: dict(row) for row in cursor.fetchall()}
            return [by_id[asset_id] for asset_id in ids if asset_id in by_id]
        with self._connection_factory() as conn:
            return self.list_asset_owned_rows(ids, connection=conn)

    def get_by_id(self, asset_id: int, *, connection=None) -> Asset | None:
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT {_ASSET_COLUMNS} FROM public.content_items WHERE id = %s",
                    (asset_id,),
                )
                row = cursor.fetchone()
            return Asset.from_row(row) if row else None
        with self._connection_factory() as conn:
            return self.get_by_id(asset_id, connection=conn)

    def list_by_ids(
        self,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> list[Asset]:
        ids = list(asset_ids)
        if not ids:
            return []
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_ASSET_COLUMNS} FROM public.content_items
                    WHERE id = ANY(%s)
                    """,
                    (ids,),
                )
                by_id = {row["id"]: Asset.from_row(row) for row in cursor.fetchall()}
            return [by_id[asset_id] for asset_id in ids if asset_id in by_id]
        with self._connection_factory() as conn:
            return self.list_by_ids(ids, connection=conn)

    def list_all(self) -> list[Asset]:
        return self.search_assets(limit=5000, eligible_only=False)

    def search_assets(
        self,
        *,
        search: str | None = None,
        media_type: str | None = None,
        classification: str | None = None,
        eligible_only: bool = True,
        limit: int = 500,
        tags: Iterable[str] | None = None,
        themes: Iterable[str] | None = None,
        status: str | None = None,
        created_after=None,
        created_before=None,
        creator_profile_id: int | None = None,
        product_id: str | None = None,
        experience_id: str | None = None,
        publishing_status: str | None = None,
        has_local_vault_original: bool | None = None,
        has_derivative_preview: bool | None = None,
        is_reference_image: bool | None = None,
        legacy_content_id: int | None = None,
    ) -> list[Asset]:
        filters = []
        params: list = []
        if eligible_only:
            filters.extend(
                [
                    "COALESCE(is_active, TRUE) = TRUE",
                    "COALESCE(is_test, FALSE) = FALSE",
                    "COALESCE(status, '') = 'approved'",
                ]
            )
        if search:
            filters.append("(file_name ILIKE %s OR file_path ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        if classification:
            filters.append("classification = %s")
            params.append(classification)
        if status:
            filters.append("status = %s")
            params.append(status)
        if creator_profile_id is not None:
            filters.append("creator_profile_id = %s")
            params.append(creator_profile_id)
        if legacy_content_id is not None:
            filters.append("id = %s")
            params.append(legacy_content_id)
        if created_after is not None:
            filters.append("created_at >= %s")
            params.append(created_after)
        if created_before is not None:
            filters.append("created_at <= %s")
            params.append(created_before)
        if media_type == "image":
            filters.append(
                "("
                "LOWER(COALESCE(media_metadata->>'media_type', '')) = 'image' "
                "OR LOWER(COALESCE(file_path, '')) ~ '\\.(gif|jpe?g|png|webp)$'"
                ")"
            )
        elif media_type == "video":
            filters.append(
                "("
                "LOWER(COALESCE(media_metadata->>'media_type', '')) = 'video' "
                "OR LOWER(COALESCE(file_path, '')) ~ '\\.(m4v|mov|mp4|webm)$'"
                ")"
            )
        tags = tuple(tag for tag in (tags or ()) if str(tag).strip())
        if tags:
            filters.append("suggested_tags && %s")
            params.append(list(tags))
        themes = tuple(theme for theme in (themes or ()) if str(theme).strip())
        if themes:
            filters.append("detected_themes && %s")
            params.append(list(themes))
        if product_id:
            filters.append(
                "EXISTS ("
                "SELECT 1 FROM public.product_assets pa "
                "WHERE pa.asset_id = content_items.id "
                "AND pa.product_id = %s"
                ")"
            )
            params.append(str(product_id))
        if experience_id:
            if str(experience_id).startswith("product:"):
                filters.append(
                    "EXISTS ("
                    "SELECT 1 FROM public.product_assets pa "
                    "WHERE pa.asset_id = content_items.id "
                    "AND pa.product_id = %s"
                    ")"
                )
                params.append(str(experience_id).replace("product:", "", 1))
            else:
                filters.append("FALSE")
        if publishing_status:
            filters.append("COALESCE(fanvue_upload_status, '') = %s")
            params.append(publishing_status)
        if has_local_vault_original is True:
            filters.append(
                "("
                "local_vault_path IS NOT NULL "
                "OR media_metadata ? 'local_vault_path'"
                ")"
            )
        elif has_local_vault_original is False:
            filters.append(
                "("
                "local_vault_path IS NULL "
                "AND NOT (media_metadata ? 'local_vault_path')"
                ")"
            )
        if has_derivative_preview is True:
            filters.append(
                "("
                "blurred_preview_path IS NOT NULL "
                "OR media_metadata->'derivatives' ? 'blurred_preview' "
                "OR media_metadata->'derivatives' ? 'blur'"
                ")"
            )
        elif has_derivative_preview is False:
            filters.append(
                "("
                "blurred_preview_path IS NULL "
                "AND NOT (media_metadata->'derivatives' ? 'blurred_preview') "
                "AND NOT (media_metadata->'derivatives' ? 'blur')"
                ")"
            )
        if is_reference_image is True:
            filters.append(
                "COALESCE(media_metadata->'reference_library'->>'is_reference', 'false') = 'true'"
            )
        elif is_reference_image is False:
            filters.append(
                "COALESCE(media_metadata->'reference_library'->>'is_reference', 'false') <> 'true'"
            )
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_ASSET_COLUMNS} FROM public.content_items
                    {where}
                    ORDER BY created_at DESC NULLS LAST, id DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cursor.fetchall()
        return [Asset.from_row(row) for row in rows]

    def update_media_metadata(
        self,
        asset_id: int,
        media_metadata: Mapping[str, Any],
        *,
        connection=None,
    ) -> None:
        query = """
            UPDATE public.content_items
            SET media_metadata = %s::jsonb
            WHERE id = %s
        """
        payload = json.dumps(dict(media_metadata or {}), default=str)
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(query, (payload, asset_id))
            return
        with self._connection_factory() as conn:
            self.update_media_metadata(
                asset_id,
                media_metadata,
                connection=conn,
            )

    def update_reference_metadata(
        self,
        asset_id: int,
        reference_metadata: Mapping[str, Any],
        *,
        connection=None,
    ) -> None:
        asset = self.get_by_id(asset_id, connection=connection)
        if not asset:
            return
        media_metadata = dict(asset.media_metadata or {})
        media_metadata["reference_library"] = dict(reference_metadata or {})
        self.update_media_metadata(
            asset_id,
            media_metadata,
            connection=connection,
        )

    def archive_assets(
        self,
        asset_ids: Iterable[int],
        *,
        connection=None,
    ) -> int:
        ids = list(asset_ids)
        if not ids:
            return 0
        query = """
            UPDATE public.content_items
            SET status = 'archived',
                is_active = FALSE,
                ready_for_rotation = FALSE
            WHERE id = ANY(%s)
        """
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(query, (ids,))
                return cursor.rowcount
        with self._connection_factory() as conn:
            return self.archive_assets(ids, connection=conn)
