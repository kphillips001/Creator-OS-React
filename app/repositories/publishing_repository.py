"""Publishing persistence plus compatibility projections.

The repository preserves legacy content_items/Product/upload-link projections
into the PublishingRecord contract and also persists durable PublishingJob
execution records for the first-class Publishing domain.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.publishing_job import (
    PublishingJob,
    PublishingJobStatus,
    PublishingMediaLinkStatus,
    build_publishing_status_projection,
)
from app.models.publishing_queue import PublishingQueueItem
from app.models.publishing_record_contract import PUBLISHING_RECORD_FIELDS
from app.models.product import (
    default_product_delivery_type,
    normalize_product_delivery_type,
    product_delivery_type_from_metadata,
)


_CONTENT_ITEM_PUBLISHING_COLUMNS = (
    "id",
    "fanvue_account_id",
    "fanvue_upload_status",
    "fanvue_preview_upload_status",
    "fanvue_full_upload_status",
    "fanvue_media_preview_uuid",
    "fanvue_media_full_uuid",
    "fanvue_ptv_set_id",
    "fanvue_set_status",
    "last_fanvue_message_uuid",
    "fanvue_upload_metadata",
    "fanvue_upload_error",
    "fanvue_uploaded_at",
    "created_at",
)

_PRODUCT_PUBLISHING_COLUMNS = (
    "id",
    "legacy_content_item_id",
    "media_link",
    "fulfillment_status",
    "fulfillment_strategy",
    "metadata",
    "created_at",
    "updated_at",
)

_COLUMN_CACHE: dict[tuple[str, str], set[str]] = {}


def _get(row: Mapping[str, Any] | None, key: str, default: Any = None) -> Any:
    if not row:
        return default
    return row.get(key, default)


def _project_product_delivery_type(row: Mapping[str, Any]) -> str:
    explicit_delivery_type = _get(row, "delivery_type")
    if explicit_delivery_type:
        return normalize_product_delivery_type(explicit_delivery_type).value

    metadata = _get(row, "metadata")
    if isinstance(metadata, Mapping):
        return product_delivery_type_from_metadata(metadata).value

    return default_product_delivery_type().value


class PublishingRepository:
    """Publishing persistence and legacy publishing projections."""

    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    def _existing_columns(
        self,
        connection,
        *,
        table_schema: str,
        table_name: str,
    ) -> set[str]:
        cache_key = (table_schema, table_name)
        if cache_key in _COLUMN_CACHE:
            return _COLUMN_CACHE[cache_key]

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = %s
                  AND table_name = %s
                """,
                (table_schema, table_name),
            )
            _COLUMN_CACHE[cache_key] = {
                row["column_name"] for row in cursor.fetchall()
            }
        return _COLUMN_CACHE[cache_key]

    def _legacy_columns(
        self,
        connection,
        *,
        table_name: str,
        requested_columns: tuple[str, ...],
    ) -> tuple[str, ...]:
        existing = self._existing_columns(
            connection,
            table_schema="public",
            table_name=table_name,
        )
        return tuple(column for column in requested_columns if column in existing)

    def _empty_record(self) -> dict[str, Any]:
        return {field: None for field in PUBLISHING_RECORD_FIELDS}

    def project_content_item(
        self,
        row: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Project a legacy content_items row into PublishingRecord shape."""

        record = self._empty_record()
        preview_media_id = _get(row, "fanvue_media_preview_uuid")
        full_media_id = _get(row, "fanvue_media_full_uuid")
        record.update(
            {
                "asset_id": _get(row, "id"),
                "provider": "fanvue",
                "provider_account_id": _get(row, "fanvue_account_id"),
                "provider_status": _get(row, "fanvue_upload_status"),
                "provider_preview_status": _get(
                    row,
                    "fanvue_preview_upload_status",
                ),
                "provider_full_status": _get(row, "fanvue_full_upload_status"),
                "provider_media_id": full_media_id or preview_media_id,
                "provider_preview_media_id": preview_media_id,
                "provider_full_media_id": full_media_id,
                "provider_set_id": _get(row, "fanvue_ptv_set_id"),
                "provider_set_status": _get(row, "fanvue_set_status"),
                "provider_message_id": _get(row, "last_fanvue_message_uuid"),
                "provider_metadata": _get(row, "fanvue_upload_metadata"),
                "provider_error": _get(row, "fanvue_upload_error"),
                "uploaded_at": _get(row, "fanvue_uploaded_at"),
                "created_at": _get(row, "created_at"),
            }
        )
        return record

    def project_product(
        self,
        row: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Project Product fulfillment compatibility fields."""

        record = self._empty_record()
        record.update(
            {
                "product_id": _get(row, "id"),
                "asset_id": _get(row, "legacy_content_item_id"),
                "provider": "fanvue",
                "provider_status": _get(row, "fulfillment_status"),
                "provider_output_url": _get(row, "media_link"),
                "delivery_method": _get(row, "fulfillment_strategy"),
                "delivery_type": _project_product_delivery_type(row),
                "created_at": _get(row, "created_at"),
                "updated_at": _get(row, "updated_at"),
            }
        )
        return record

    def project_legacy_upload_link(
        self,
        row: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Project a legacy CMS/Fanvue upload-link row.

        No upload-link table is queried in A.3.3 because its persistence shape
        is not defined in the current migrations. Future phases can wire this
        projection to the recovered legacy table or replacement view.
        """

        record = self._empty_record()
        preview_media_id = _get(row, "fanvue_preview_media_uuid")
        full_media_id = _get(row, "fanvue_full_media_uuid")
        record.update(
            {
                "asset_id": _get(row, "content_item_id") or _get(row, "asset_id"),
                "provider": "fanvue",
                "provider_account_id": _get(row, "fanvue_account_id"),
                "provider_status": _get(row, "upload_status"),
                "provider_media_id": _get(row, "fanvue_media_uuid")
                or full_media_id
                or preview_media_id,
                "provider_preview_media_id": preview_media_id,
                "provider_full_media_id": full_media_id,
                "destination": _get(row, "destination"),
                "delivery_method": _get(row, "delivery_method"),
                "provider_folder_id": _get(row, "vault_folder_id"),
                "provider_error": _get(row, "error_message"),
                "created_at": _get(row, "created_at"),
                "updated_at": _get(row, "updated_at"),
            }
        )
        return record

    def project_job(
        self,
        job: PublishingJob | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Project a durable PublishingJob into PublishingRecord shape."""

        record = self._empty_record()
        get_value = _get if isinstance(job, Mapping) else getattr
        status = get_value(job, "status")
        media_link_status = get_value(job, "media_link_status")
        status_projection = build_publishing_status_projection(
            job if isinstance(job, PublishingJob) else PublishingJob.from_row(job)
        )
        record.update(
            {
                "id": get_value(job, "id"),
                "product_id": get_value(job, "product_id"),
                "asset_id": get_value(job, "asset_id"),
                "provider": get_value(job, "provider"),
                "provider_account_id": get_value(job, "provider_account_id"),
                "publishing_status": status_projection.publishing_status,
                "provider_status": getattr(status, "value", status),
                "upload_status": status_projection.upload_status,
                "media_link_status": status_projection.media_link_status,
                "retry_state": status_projection.retry_state,
                "provider_output_url": get_value(job, "provider_output_url"),
                "provider_media_id": get_value(job, "provider_media_id"),
                "provider_preview_media_id": get_value(
                    job,
                    "provider_preview_media_id",
                ),
                "provider_full_media_id": get_value(
                    job,
                    "provider_full_media_id",
                ),
                "provider_metadata": get_value(job, "provider_metadata"),
                "provider_error": get_value(job, "failure_reason"),
                "upload_started_at": status_projection.upload_started_at,
                "upload_completed_at": status_projection.upload_completed_at,
                "last_attempted_at": status_projection.last_attempted_at,
                "retry_scheduled_at": status_projection.retry_scheduled_at,
                "uploaded_at": get_value(job, "uploaded_at"),
                "created_at": get_value(job, "created_at"),
                "updated_at": get_value(job, "updated_at"),
            }
        )
        metadata = dict(record.get("provider_metadata") or {})
        metadata["publishing_job"] = {
            "status": getattr(status, "value", status),
            "publishing_status": status_projection.publishing_status,
            "media_link_status": getattr(
                media_link_status,
                "value",
                media_link_status,
            ),
            "retry_count": get_value(job, "retry_count"),
            "max_retries": get_value(job, "max_retries"),
            "next_retry_at": get_value(job, "next_retry_at"),
            "retry_state": status_projection.retry_state,
        }
        record["provider_metadata"] = metadata
        return record

    def create_job(
        self,
        *,
        product_id: UUID | None = None,
        asset_id: int | None = None,
        provider: str,
        provider_account_id: int | None = None,
        media_link_required: bool = False,
        max_retries: int = 3,
        provider_metadata: Mapping[str, Any] | None = None,
        connection=None,
    ) -> PublishingJob:
        """Create a durable provider execution record."""

        if product_id is None and asset_id is None:
            raise ValueError("PublishingJob requires product_id or asset_id.")
        media_link_status = (
            PublishingMediaLinkStatus.REQUIRED
            if media_link_required
            else PublishingMediaLinkStatus.NOT_REQUIRED
        )
        query = """
            INSERT INTO public.publishing_jobs (
                id, product_id, asset_id, provider, provider_account_id,
                status, media_link_status, provider_metadata, max_retries
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        uuid4(),
                        product_id,
                        asset_id,
                        provider,
                        provider_account_id,
                        PublishingJobStatus.QUEUED.value,
                        media_link_status.value,
                        json.dumps(dict(provider_metadata or {})),
                        max_retries,
                    ),
                )
                row = cursor.fetchone()
        return PublishingJob.from_row(row)

    def get_job_by_id(
        self,
        job_id: UUID,
        *,
        connection=None,
    ) -> PublishingJob | None:
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.publishing_jobs
                    WHERE id = %s
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()
        return PublishingJob.from_row(row) if row else None

    def list_jobs_for_product(
        self,
        product_id: UUID,
        *,
        limit: int = 50,
        connection=None,
    ) -> tuple[PublishingJob, ...]:
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.publishing_jobs
                    WHERE product_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (product_id, limit),
                )
                rows = cursor.fetchall()
        return tuple(PublishingJob.from_row(row) for row in rows)

    def get_open_job_for_product(
        self,
        product_id: UUID,
        *,
        provider: str | None = None,
        connection=None,
    ) -> PublishingJob | None:
        filters = [
            "product_id = %s",
            "status NOT IN ('COMPLETED', 'CANCELLED')",
        ]
        params: list[Any] = [product_id]
        if provider:
            filters.append("provider = %s")
            params.append(provider)
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM public.publishing_jobs
                    WHERE {' AND '.join(filters)}
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    tuple(params),
                )
                row = cursor.fetchone()
        return PublishingJob.from_row(row) if row else None

    def list_queue_items(
        self,
        *,
        limit: int = 500,
        connection=None,
    ) -> tuple[PublishingQueueItem, ...]:
        """Return Publishing Queue read models.

        Product and Asset values here are projection data for display/execution
        context only. Products remain owned by ProductRepository.
        """

        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        pj.*,
                        COALESCE(p.display_name, p.internal_name) AS product_name,
                        ci.file_path AS asset_file_path,
                        ci.classification AS asset_classification
                    FROM public.publishing_jobs pj
                    LEFT JOIN public.products p
                        ON p.id = pj.product_id
                    LEFT JOIN public.content_items ci
                        ON ci.id = pj.asset_id
                    ORDER BY
                        CASE pj.status
                            WHEN 'FAILED' THEN 0
                            WHEN 'RETRY_SCHEDULED' THEN 1
                            WHEN 'QUEUED' THEN 2
                            WHEN 'UPLOADING' THEN 3
                            WHEN 'MEDIA_LINK_REQUIRED' THEN 4
                            ELSE 5
                        END,
                        pj.updated_at DESC
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = cursor.fetchall()
        return tuple(PublishingQueueItem.from_row(row) for row in rows)

    def get_queue_item(
        self,
        job_id: UUID,
        *,
        connection=None,
    ) -> PublishingQueueItem | None:
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        pj.*,
                        COALESCE(p.display_name, p.internal_name) AS product_name,
                        ci.file_path AS asset_file_path,
                        ci.classification AS asset_classification
                    FROM public.publishing_jobs pj
                    LEFT JOIN public.products p
                        ON p.id = pj.product_id
                    LEFT JOIN public.content_items ci
                        ON ci.id = pj.asset_id
                    WHERE pj.id = %s
                    """,
                    (job_id,),
                )
                row = cursor.fetchone()
        return PublishingQueueItem.from_row(row) if row else None

    def mark_job_uploading(
        self,
        job_id: UUID,
        *,
        provider_status: str = "uploading",
        connection=None,
    ) -> PublishingJob | None:
        return self._update_job(
            job_id,
            """
            status = %s,
            provider_status = %s,
            upload_started_at = COALESCE(upload_started_at, NOW()),
            next_retry_at = NULL,
            failure_reason = NULL,
            updated_at = NOW()
            """,
            (
                PublishingJobStatus.UPLOADING.value,
                provider_status,
            ),
            connection=connection,
        )

    def record_job_upload_result(
        self,
        job_id: UUID,
        *,
        upload_payload: Mapping[str, Any],
        media_link_required: bool = False,
        connection=None,
    ) -> PublishingJob | None:
        media_link_status = (
            PublishingMediaLinkStatus.REQUIRED
            if media_link_required
            else PublishingMediaLinkStatus.NOT_REQUIRED
        )
        return self._update_job(
            job_id,
            """
            status = %s,
            media_link_status = %s,
            provider_status = %s,
            provider_media_id = %s,
            provider_preview_media_id = %s,
            provider_full_media_id = %s,
            provider_metadata = %s::jsonb,
            failure_reason = NULL,
            uploaded_at = NOW(),
            updated_at = NOW()
            """,
            (
                PublishingJobStatus.UPLOADED.value,
                media_link_status.value,
                upload_payload.get("provider_status"),
                upload_payload.get("provider_media_id"),
                upload_payload.get("provider_preview_media_id"),
                upload_payload.get("provider_full_media_id"),
                json.dumps(upload_payload.get("provider_metadata") or {}),
            ),
            connection=connection,
        )

    def mark_job_media_link_created(
        self,
        job_id: UUID,
        *,
        media_link: str,
        provider_metadata: Mapping[str, Any] | None = None,
        complete: bool = True,
        connection=None,
    ) -> PublishingJob | None:
        status = (
            PublishingJobStatus.COMPLETED
            if complete
            else PublishingJobStatus.MEDIA_LINK_CREATED
        )
        return self._update_job(
            job_id,
            """
            status = %s,
            media_link_status = %s,
            provider_output_url = %s,
            provider_metadata = provider_metadata || %s::jsonb,
            completed_at = CASE WHEN %s THEN NOW() ELSE completed_at END,
            updated_at = NOW()
            """,
            (
                status.value,
                PublishingMediaLinkStatus.CREATED.value,
                media_link,
                json.dumps(dict(provider_metadata or {})),
                complete,
            ),
            connection=connection,
        )

    def mark_job_failed(
        self,
        job_id: UUID,
        *,
        failure_reason: str,
        provider_status: str = "failed",
        provider_metadata: Mapping[str, Any] | None = None,
        connection=None,
    ) -> PublishingJob | None:
        return self._update_job(
            job_id,
            """
            status = %s,
            provider_status = %s,
            provider_metadata = provider_metadata || %s::jsonb,
            failure_reason = %s,
            updated_at = NOW()
            """,
            (
                PublishingJobStatus.FAILED.value,
                provider_status,
                json.dumps(dict(provider_metadata or {})),
                failure_reason,
            ),
            connection=connection,
        )

    def schedule_job_retry(
        self,
        job_id: UUID,
        *,
        next_retry_at,
        failure_reason: str | None = None,
        connection=None,
    ) -> PublishingJob | None:
        return self._update_job(
            job_id,
            """
            status = %s,
            provider_status = %s,
            retry_count = retry_count + 1,
            next_retry_at = %s,
            failure_reason = COALESCE(%s, failure_reason),
            updated_at = NOW()
            """,
            (
                PublishingJobStatus.QUEUED.value,
                "retry_queued",
                next_retry_at,
                failure_reason,
            ),
            connection=connection,
        )

    def get_by_asset_id(
        self,
        asset_id: int,
        *,
        connection=None,
    ) -> dict[str, Any] | None:
        """Read provider publishing state for one legacy content item."""

        if connection is not None:
            columns = self._legacy_columns(
                connection,
                table_name="content_items",
                requested_columns=_CONTENT_ITEM_PUBLISHING_COLUMNS,
            )
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
            return self.project_content_item(dict(row)) if row else None

        with self._connection_factory() as conn:
            return self.get_by_asset_id(asset_id, connection=conn)

    def get_by_product_id(
        self,
        product_id: UUID,
        *,
        connection=None,
    ) -> dict[str, Any] | None:
        """Read Product fulfillment output plus legacy asset publishing state."""

        if connection is not None:
            columns = self._legacy_columns(
                connection,
                table_name="products",
                requested_columns=_PRODUCT_PUBLISHING_COLUMNS,
            )
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {", ".join(columns)}
                    FROM public.products
                    WHERE id = %s
                    """,
                    (product_id,),
                )
                product_row = cursor.fetchone()
            if not product_row:
                return None

            product_record = self.project_product(dict(product_row))
            asset_id = product_record.get("asset_id")
            if not asset_id:
                return product_record

            asset_record = self.get_by_asset_id(asset_id, connection=connection)
            if not asset_record:
                return product_record

            merged = asset_record | {
                key: value
                for key, value in product_record.items()
                if value is not None
            }
            return merged

        with self._connection_factory() as conn:
            return self.get_by_product_id(product_id, connection=conn)

    @contextmanager
    def _connection(self, connection=None):
        if connection is not None:
            yield connection
            return
        with self._connection_factory() as managed:
            yield managed

    def _update_job(
        self,
        job_id: UUID,
        assignments: str,
        params: tuple[Any, ...],
        *,
        connection=None,
    ) -> PublishingJob | None:
        query = f"""
            UPDATE public.publishing_jobs
            SET {assignments}
            WHERE id = %s
            RETURNING *;
        """
        with self._connection(connection) as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (*params, job_id))
                row = cursor.fetchone()
        return PublishingJob.from_row(row) if row else None
