"""Publishing Queue read models.

These models are presentation-facing projections owned by Publishing. They do
not replace Product, Product Catalog, or Product Review ownership.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID

from app.models.publishing_job import (
    PublishingJob,
    PublishingJobStatus,
    build_publishing_status_projection,
)


@dataclass(frozen=True)
class PublishingQueueItem:
    job: PublishingJob
    product_name: str
    publishing_status: str
    publishing_priority: str
    upload_status: str
    provider_status: str
    provider_metadata_summary: str
    failure_summary: str | None
    ready_to_upload: bool
    waiting_for_media_link: bool
    failed_upload: bool
    retry_visible: bool
    retry_state: str
    provider_media_id: str | None = None
    provider_output_url: str | None = None
    provider_error: str | None = None
    upload_completed_at: datetime | None = None
    last_attempted_at: datetime | None = None
    retry_scheduled_at: datetime | None = None
    asset_file_path: str | None = None
    asset_classification: str | None = None

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "PublishingQueueItem":
        job = PublishingJob.from_row(row)
        product_name = (
            row.get("product_name")
            or row.get("display_name")
            or row.get("internal_name")
            or (
                f"Product {job.product_id}"
                if job.product_id
                else f"Asset {job.asset_id}"
            )
        )
        metadata = job.provider_metadata or {}
        metadata_summary = _metadata_summary(metadata)
        failure = job.failure_reason or row.get("failure_summary")
        status_projection = build_publishing_status_projection(job)
        ready_to_upload = job.status in {
            PublishingJobStatus.QUEUED,
            PublishingJobStatus.RETRY_SCHEDULED,
        } and bool(row.get("asset_file_path"))
        waiting_for_media_link = (
            status_projection.publishing_status == "WAITING_FOR_MEDIA_LINK"
        )
        failed_upload = job.status == PublishingJobStatus.FAILED
        retry_visible = failed_upload and job.can_retry
        return cls(
            job=job,
            product_name=str(product_name),
            publishing_status=status_projection.publishing_status,
            publishing_priority=_priority_for_job(
                job,
                ready_to_upload=ready_to_upload,
                waiting_for_media_link=waiting_for_media_link,
            ),
            upload_status=status_projection.upload_status,
            provider_status=status_projection.provider_status,
            provider_metadata_summary=metadata_summary,
            failure_summary=str(failure) if failure else None,
            ready_to_upload=ready_to_upload,
            waiting_for_media_link=waiting_for_media_link,
            failed_upload=failed_upload,
            retry_visible=retry_visible,
            retry_state=status_projection.retry_state,
            provider_media_id=status_projection.provider_media_id,
            provider_output_url=status_projection.provider_output_url,
            provider_error=status_projection.provider_error,
            upload_completed_at=status_projection.upload_completed_at,
            last_attempted_at=status_projection.last_attempted_at,
            retry_scheduled_at=status_projection.retry_scheduled_at,
            asset_file_path=row.get("asset_file_path"),
            asset_classification=row.get("asset_classification"),
        )

    @property
    def id(self) -> UUID:
        return self.job.id

    @property
    def product_id(self) -> UUID | None:
        return self.job.product_id

    @property
    def provider(self) -> str:
        return self.job.provider

    @property
    def status(self) -> str:
        return self.publishing_status

    @property
    def media_link_status(self) -> str:
        return build_publishing_status_projection(self.job).media_link_status

    @property
    def retry_count(self) -> int:
        return self.job.retry_count

    @property
    def upload_timestamp(self) -> datetime | None:
        return self.upload_completed_at or self.job.upload_started_at

    @property
    def updated_at(self) -> datetime:
        return self.job.updated_at

    def build_upload_item(
        self,
        *,
        allow_retry: bool = False,
    ) -> dict[str, Any] | None:
        can_upload = self.ready_to_upload or (allow_retry and self.retry_visible)
        if not can_upload or not self.asset_file_path:
            return None
        return {
            "id": self.job.asset_id,
            "file_path": self.asset_file_path,
            "classification": self.asset_classification,
        }


@dataclass(frozen=True)
class PublishingQueueSummary:
    total_jobs: int
    ready_to_upload: int
    waiting_for_media_link: int
    failed_uploads: int
    retryable: int
    uploading: int
    completed: int
    providers: tuple[str, ...]


def build_publishing_queue_summary(
    items: tuple[PublishingQueueItem, ...],
) -> PublishingQueueSummary:
    return PublishingQueueSummary(
        total_jobs=len(items),
        ready_to_upload=sum(1 for item in items if item.ready_to_upload),
        waiting_for_media_link=sum(
            1 for item in items if item.waiting_for_media_link
        ),
        failed_uploads=sum(1 for item in items if item.failed_upload),
        retryable=sum(1 for item in items if item.retry_visible),
        uploading=sum(
            1 for item in items if item.job.status == PublishingJobStatus.UPLOADING
        ),
        completed=sum(
            1 for item in items if item.status == "PUBLISHING_COMPLETE"
        ),
        providers=tuple(sorted({item.provider for item in items})),
    )


def _metadata_summary(metadata: Mapping[str, Any]) -> str:
    if not metadata:
        return "No provider metadata"
    keys = sorted(str(key) for key in metadata.keys())
    visible = ", ".join(keys[:4])
    if len(keys) > 4:
        return f"{visible}, +{len(keys) - 4} more"
    return visible


def _priority_for_job(
    job: PublishingJob,
    *,
    ready_to_upload: bool,
    waiting_for_media_link: bool,
) -> str:
    if job.status == PublishingJobStatus.FAILED:
        return "high"
    if job.status == PublishingJobStatus.RETRY_SCHEDULED:
        return "high" if job.next_retry_at else "medium"
    if ready_to_upload:
        return "medium"
    if waiting_for_media_link:
        return "medium"
    return "normal"
