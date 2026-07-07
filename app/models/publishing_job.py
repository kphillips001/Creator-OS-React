"""Provider-neutral Publishing Job domain model.

Publishing Jobs are durable execution records owned by PublishingService.
They track provider execution only; Product remains the source of truth for
commerce, approval, delivery type, product lifecycle, and media_link.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


class PublishingJobStatus(str, Enum):
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    MEDIA_LINK_REQUIRED = "MEDIA_LINK_REQUIRED"
    MEDIA_LINK_CREATED = "MEDIA_LINK_CREATED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    RETRY_SCHEDULED = "RETRY_SCHEDULED"
    CANCELLED = "CANCELLED"


class PublishingLifecycleStatus(str, Enum):
    NOT_QUEUED = "NOT_QUEUED"
    QUEUED = "QUEUED"
    UPLOADING = "UPLOADING"
    UPLOADED = "UPLOADED"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    MEDIA_LINK_VERIFIED = "MEDIA_LINK_VERIFIED"
    PUBLISHING_COMPLETE = "PUBLISHING_COMPLETE"
    FAILED = "FAILED"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    ARCHIVED = "ARCHIVED"


class PublishingMediaLinkStatus(str, Enum):
    NOT_REQUIRED = "NOT_REQUIRED"
    REQUIRED = "REQUIRED"
    PENDING = "PENDING"
    CREATED = "CREATED"
    FAILED = "FAILED"


@dataclass(frozen=True)
class PublishingStatusProjection:
    publishing_status: str
    provider: str
    provider_status: str
    upload_status: str
    media_link_status: str
    retry_state: str
    provider_media_id: str | None
    provider_output_url: str | None
    provider_error: str | None
    upload_started_at: datetime | None
    upload_completed_at: datetime | None
    last_attempted_at: datetime | None
    retry_count: int
    retry_scheduled_at: datetime | None
    failure_reason: str | None


@dataclass(frozen=True)
class PublishingJob:
    id: UUID
    product_id: UUID | None
    asset_id: int | None
    provider: str
    provider_account_id: int | None
    status: PublishingJobStatus
    media_link_status: PublishingMediaLinkStatus
    provider_status: str | None
    provider_output_url: str | None
    provider_media_id: str | None
    provider_preview_media_id: str | None
    provider_full_media_id: str | None
    provider_metadata: Mapping[str, Any]
    failure_reason: str | None
    retry_count: int
    max_retries: int
    next_retry_at: datetime | None
    upload_started_at: datetime | None
    uploaded_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_row(cls, row: Mapping[str, Any]) -> "PublishingJob":
        return cls(
            id=row["id"],
            product_id=row.get("product_id"),
            asset_id=row.get("asset_id"),
            provider=row["provider"],
            provider_account_id=row.get("provider_account_id"),
            status=PublishingJobStatus(row["status"]),
            media_link_status=PublishingMediaLinkStatus(
                row["media_link_status"]
            ),
            provider_status=row.get("provider_status"),
            provider_output_url=row.get("provider_output_url"),
            provider_media_id=row.get("provider_media_id"),
            provider_preview_media_id=row.get("provider_preview_media_id"),
            provider_full_media_id=row.get("provider_full_media_id"),
            provider_metadata=row.get("provider_metadata") or {},
            failure_reason=row.get("failure_reason"),
            retry_count=int(row.get("retry_count") or 0),
            max_retries=int(row.get("max_retries") or 0),
            next_retry_at=row.get("next_retry_at"),
            upload_started_at=row.get("upload_started_at"),
            uploaded_at=row.get("uploaded_at"),
            completed_at=row.get("completed_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries

    @property
    def is_terminal(self) -> bool:
        return self.status in {
            PublishingJobStatus.COMPLETED,
            PublishingJobStatus.CANCELLED,
        }


def build_publishing_status_projection(
    job: PublishingJob | None,
) -> PublishingStatusProjection:
    if job is None:
        return PublishingStatusProjection(
            publishing_status=PublishingLifecycleStatus.NOT_QUEUED.value,
            provider="",
            provider_status=PublishingLifecycleStatus.NOT_QUEUED.value,
            upload_status=PublishingLifecycleStatus.NOT_QUEUED.value,
            media_link_status=PublishingMediaLinkStatus.NOT_REQUIRED.value,
            retry_state="NOT_RETRYABLE",
            provider_media_id=None,
            provider_output_url=None,
            provider_error=None,
            upload_started_at=None,
            upload_completed_at=None,
            last_attempted_at=None,
            retry_count=0,
            retry_scheduled_at=None,
            failure_reason=None,
        )
    lifecycle = _publishing_lifecycle_status(job)
    return PublishingStatusProjection(
        publishing_status=lifecycle.value,
        provider=job.provider,
        provider_status=job.provider_status or lifecycle.value,
        upload_status=_upload_status(job, lifecycle),
        media_link_status=_media_link_status(job, lifecycle),
        retry_state=_retry_state(job, lifecycle),
        provider_media_id=(
            job.provider_media_id
            or job.provider_full_media_id
            or job.provider_preview_media_id
        ),
        provider_output_url=job.provider_output_url,
        provider_error=job.failure_reason,
        upload_started_at=job.upload_started_at,
        upload_completed_at=job.uploaded_at,
        last_attempted_at=(
            job.uploaded_at
            or job.upload_started_at
            or (job.updated_at if job.retry_count else None)
        ),
        retry_count=job.retry_count,
        retry_scheduled_at=job.next_retry_at,
        failure_reason=job.failure_reason,
    )


def _publishing_lifecycle_status(job: PublishingJob) -> PublishingLifecycleStatus:
    if job.status == PublishingJobStatus.QUEUED:
        return PublishingLifecycleStatus.QUEUED
    if job.status == PublishingJobStatus.UPLOADING:
        return PublishingLifecycleStatus.UPLOADING
    if job.status == PublishingJobStatus.UPLOADED:
        if job.media_link_status in {
            PublishingMediaLinkStatus.REQUIRED,
            PublishingMediaLinkStatus.PENDING,
        }:
            return PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK
        return PublishingLifecycleStatus.UPLOADED
    if job.status == PublishingJobStatus.MEDIA_LINK_REQUIRED:
        return PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK
    if job.status == PublishingJobStatus.MEDIA_LINK_CREATED:
        return PublishingLifecycleStatus.MEDIA_LINK_VERIFIED
    if job.status == PublishingJobStatus.COMPLETED:
        return PublishingLifecycleStatus.PUBLISHING_COMPLETE
    if job.status == PublishingJobStatus.FAILED:
        return (
            PublishingLifecycleStatus.RETRY_REQUIRED
            if job.can_retry
            else PublishingLifecycleStatus.FAILED
        )
    if job.status == PublishingJobStatus.RETRY_SCHEDULED:
        return PublishingLifecycleStatus.RETRY_REQUIRED
    if job.status == PublishingJobStatus.CANCELLED:
        return PublishingLifecycleStatus.ARCHIVED
    return PublishingLifecycleStatus.NOT_QUEUED


def _upload_status(
    job: PublishingJob,
    lifecycle: PublishingLifecycleStatus,
) -> str:
    if lifecycle in {
        PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK,
        PublishingLifecycleStatus.MEDIA_LINK_VERIFIED,
        PublishingLifecycleStatus.PUBLISHING_COMPLETE,
    }:
        return PublishingLifecycleStatus.UPLOADED.value
    if lifecycle == PublishingLifecycleStatus.RETRY_REQUIRED:
        return PublishingLifecycleStatus.RETRY_REQUIRED.value
    if lifecycle == PublishingLifecycleStatus.FAILED:
        return PublishingLifecycleStatus.FAILED.value
    if lifecycle in {
        PublishingLifecycleStatus.UPLOADING,
        PublishingLifecycleStatus.UPLOADED,
        PublishingLifecycleStatus.QUEUED,
    }:
        return lifecycle.value
    if job.provider_status:
        return job.provider_status
    return lifecycle.value


def _media_link_status(
    job: PublishingJob,
    lifecycle: PublishingLifecycleStatus,
) -> str:
    if lifecycle == PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK:
        return PublishingLifecycleStatus.WAITING_FOR_MEDIA_LINK.value
    if lifecycle == PublishingLifecycleStatus.MEDIA_LINK_VERIFIED:
        return PublishingLifecycleStatus.MEDIA_LINK_VERIFIED.value
    return job.media_link_status.value


def _retry_state(
    job: PublishingJob,
    lifecycle: PublishingLifecycleStatus,
) -> str:
    if lifecycle == PublishingLifecycleStatus.RETRY_REQUIRED:
        return "RETRY_REQUIRED"
    if job.retry_count > 0 and job.status == PublishingJobStatus.QUEUED:
        return "RETRY_QUEUED"
    if job.retry_count > 0:
        return "RETRIED"
    return "NOT_RETRIED"
