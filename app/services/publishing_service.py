"""Provider-neutral publishing domain service.

PublishingService is the canonical Publishing orchestration boundary. It keeps
legacy publishing projections compatible while owning durable Publishing Job
execution state and provider result normalization.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any
from urllib.parse import urlparse
from uuid import UUID

from app.database import get_db_connection
from app.models.experience import ExperiencePublishingReadiness
from app.models.publishing_job import (
    PublishingJob,
    PublishingMediaLinkStatus,
    PublishingStatusProjection,
    build_publishing_status_projection,
)
from app.models.publishing_queue import (
    PublishingQueueItem,
    PublishingQueueSummary,
    build_publishing_queue_summary,
)
from app.models.product import (
    ProductApprovalStatus,
    product_approval_status_from_metadata,
)
from app.providers.publishing import FanvuePublishingProvider, PublishingProvider
from app.repositories.publishing_repository import PublishingRepository


PROVIDER_STATUS_UPLOADED = "Uploaded to {provider}"
PROVIDER_STATUS_FAILED = "Failed {provider} upload"
PROVIDER_STATUS_NOT_UPLOADED = "Not uploaded to {provider}"
PROVIDER_STATUS_URL_AVAILABLE = "{provider} URL available"


class PublishingService:
    """Business facade over provider publishing state."""

    def __init__(
        self,
        publishing_repository: PublishingRepository | None = None,
        *,
        connection_factory=get_db_connection,
        publishing_provider: PublishingProvider | None = None,
        media_upload_service_factory=None,
    ):
        self.publishing_repository = (
            publishing_repository or PublishingRepository()
        )
        self._connection_factory = connection_factory
        self._publishing_provider = publishing_provider or FanvuePublishingProvider(
            **(
                {"media_upload_service_factory": media_upload_service_factory}
                if media_upload_service_factory is not None
                else {}
            )
        )

    def get_by_asset_id(self, asset_id: int) -> dict[str, Any] | None:
        return self.publishing_repository.get_by_asset_id(asset_id)

    def get_by_product_id(self, product_id: UUID) -> dict[str, Any] | None:
        return self.publishing_repository.get_by_product_id(product_id)

    def create_publishing_job(
        self,
        *,
        product_id: UUID | None = None,
        asset_id: int | None = None,
        provider: str | None = None,
        provider_account_id: int | None = None,
        media_link_required: bool = False,
        max_retries: int = 3,
        provider_metadata: Mapping[str, Any] | None = None,
    ) -> PublishingJob:
        """Create a durable provider execution record.

        Publishing Jobs are execution state only. They intentionally reference
        Products and Assets without copying Product lifecycle, approval,
        commerce, delivery type, or media_link ownership.
        """

        return self.publishing_repository.create_job(
            product_id=product_id,
            asset_id=asset_id,
            provider=provider or self._publishing_provider.provider_name,
            provider_account_id=provider_account_id,
            media_link_required=media_link_required,
            max_retries=max_retries,
            provider_metadata=provider_metadata,
        )

    def get_publishing_job(self, job_id: UUID) -> PublishingJob | None:
        return self.publishing_repository.get_job_by_id(job_id)

    def list_product_publishing_jobs(
        self,
        product_id: UUID,
        *,
        limit: int = 50,
    ) -> tuple[PublishingJob, ...]:
        return self.publishing_repository.list_jobs_for_product(
            product_id,
            limit=limit,
        )

    def list_publishing_queue_items(
        self,
        *,
        limit: int = 500,
    ) -> tuple[PublishingQueueItem, ...]:
        return self.publishing_repository.list_queue_items(limit=limit)

    def get_publishing_queue_item(
        self,
        job_id: UUID,
    ) -> PublishingQueueItem | None:
        return self.publishing_repository.get_queue_item(job_id)

    def build_publishing_queue_summary(
        self,
        items: tuple[PublishingQueueItem, ...],
    ) -> PublishingQueueSummary:
        return build_publishing_queue_summary(items)

    def ensure_product_publishing_job(
        self,
        *,
        product_id: UUID,
        asset_id: int | None = None,
        provider: str | None = None,
        provider_account_id: int | None = None,
        media_link_required: bool = True,
        max_retries: int = 3,
        provider_metadata: Mapping[str, Any] | None = None,
    ) -> PublishingJob:
        """Create one open Publishing Job for an approved Product if needed."""

        provider_name = provider or self._publishing_provider.provider_name
        existing = self.publishing_repository.get_open_job_for_product(
            product_id,
            provider=provider_name,
        )
        if existing:
            return existing
        return self.create_publishing_job(
            product_id=product_id,
            asset_id=asset_id,
            provider=provider_name,
            provider_account_id=provider_account_id,
            media_link_required=media_link_required,
            max_retries=max_retries,
            provider_metadata=provider_metadata,
        )

    def ensure_asset_publishing_job(
        self,
        *,
        asset_id: int,
        provider: str | None = None,
        provider_account_id: int | None = None,
        media_link_required: bool = True,
        max_retries: int = 3,
        provider_metadata: Mapping[str, Any] | None = None,
        route_owner: str | None = None,
    ) -> PublishingJob:
        """Create one open asset-only PublishingJob for a fulfillment route."""

        provider_name = provider or self._publishing_provider.provider_name
        metadata_filter = {}
        if route_owner:
            metadata_filter["route_owner"] = route_owner
        existing = self.publishing_repository.get_open_job_for_asset(
            int(asset_id),
            provider=provider_name,
            provider_metadata_filter=metadata_filter,
        )
        if existing:
            return existing
        metadata = dict(provider_metadata or {})
        if route_owner:
            metadata.setdefault("route_owner", route_owner)
        return self.create_publishing_job(
            asset_id=int(asset_id),
            provider=provider_name,
            provider_account_id=provider_account_id,
            media_link_required=media_link_required,
            max_retries=max_retries,
            provider_metadata=metadata,
        )

    def project_publishing_job_record(
        self,
        job: PublishingJob | Mapping[str, Any],
    ) -> dict[str, Any]:
        return self.publishing_repository.project_job(job)

    def project_publishing_status(
        self,
        job: PublishingJob | None,
    ) -> PublishingStatusProjection:
        return build_publishing_status_projection(job)

    def get_provider_capabilities(self) -> dict[str, Any]:
        capabilities = self._publishing_provider.get_capabilities()
        return dict(capabilities.__dict__)

    def build_provider_execution_metadata(
        self,
        job: PublishingJob | Mapping[str, Any] | None,
    ) -> dict[str, Any]:
        if job is None:
            status_projection = build_publishing_status_projection(None)
            provider_metadata = {}
            provider_account_id = None
        else:
            status_job = job if isinstance(job, PublishingJob) else PublishingJob.from_row(job)
            status_projection = build_publishing_status_projection(status_job)
            provider_metadata = dict(status_job.provider_metadata or {})
            provider_account_id = status_job.provider_account_id
        return {
            "provider": status_projection.provider,
            "provider_account_id": provider_account_id,
            "provider_status": status_projection.provider_status,
            "upload_status": status_projection.upload_status,
            "provider_media_id": status_projection.provider_media_id,
            "provider_output_url": status_projection.provider_output_url,
            "provider_error": status_projection.provider_error,
            "upload_started_at": status_projection.upload_started_at,
            "upload_completed_at": status_projection.upload_completed_at,
            "last_attempted_at": status_projection.last_attempted_at,
            "retry_state": status_projection.retry_state,
            "retry_count": status_projection.retry_count,
            "retry_scheduled_at": status_projection.retry_scheduled_at,
            "failure_reason": status_projection.failure_reason,
            "provider_metadata": self.normalize_provider_metadata(provider_metadata),
            "capabilities": self.get_provider_capabilities(),
        }

    def mark_publishing_job_uploading(
        self,
        job_id: UUID,
        *,
        provider_status: str = "uploading",
    ) -> PublishingJob | None:
        return self.publishing_repository.mark_job_uploading(
            job_id,
            provider_status=provider_status,
        )

    def record_publishing_job_upload_result(
        self,
        job_id: UUID,
        *,
        upload_payload: Mapping[str, Any],
        media_link_required: bool = False,
    ) -> PublishingJob | None:
        return self.publishing_repository.record_job_upload_result(
            job_id,
            upload_payload=upload_payload,
            media_link_required=media_link_required,
        )

    def record_publishing_job_media_link(
        self,
        job_id: UUID,
        *,
        media_link: str,
        provider_metadata: Mapping[str, Any] | None = None,
        complete: bool = True,
    ) -> PublishingJob | None:
        return self.publishing_repository.mark_job_media_link_created(
            job_id,
            media_link=media_link,
            provider_metadata=provider_metadata,
            complete=complete,
        )

    def validate_publishing_media_link(
        self,
        media_link: str | None,
        *,
        product_id: UUID | None = None,
        creator_profile_id: int | None = None,
        product_catalog_service: Any = None,
    ) -> dict[str, Any]:
        normalized_link = (media_link or "").strip()
        errors: list[str] = []
        warnings: list[str] = []
        if not normalized_link:
            errors.append("missing_media_link")
        elif not self._valid_media_link_url(normalized_link):
            errors.append("invalid_media_link_url")

        product = None
        existing_product = None
        if normalized_link and product_id and creator_profile_id:
            catalog = product_catalog_service or self._product_catalog_service()
            try:
                product = catalog.validate_media_link_ownership(
                    product_id=product_id,
                    creator_profile_id=creator_profile_id,
                    media_link=normalized_link,
                )
                existing_product = catalog.find_product_by_media_link(
                    normalized_link,
                    creator_profile_id=creator_profile_id,
                )
                if existing_product and existing_product.id == product_id:
                    warnings.append("media_link_already_on_product")
            except Exception as error:
                errors.append(str(error))

        return {
            "valid": not errors,
            "media_link": normalized_link,
            "errors": tuple(errors),
            "warnings": tuple(warnings),
            "product": product,
            "existing_product": existing_product,
        }

    def complete_publishing_media_link_workflow(
        self,
        job_id: UUID,
        *,
        creator_profile_id: int,
        media_link: str | None,
        product_catalog_service: Any = None,
    ) -> dict[str, Any]:
        job = self.get_publishing_job(job_id)
        if not job:
            return {
                "success": False,
                "reason": "publishing_job_not_found",
                "errors": ("publishing_job_not_found",),
                "job_id": str(job_id),
            }
        status = self.project_publishing_status(job)
        if status.publishing_status != "WAITING_FOR_MEDIA_LINK":
            return {
                "success": False,
                "reason": "publishing_job_not_waiting_for_media_link",
                "errors": ("publishing_job_not_waiting_for_media_link",),
                "job_id": str(job_id),
                "publishing_status": status.publishing_status,
            }
        catalog = (
            product_catalog_service or self._product_catalog_service()
            if job.product_id
            else None
        )
        validation = self.validate_publishing_media_link(
            media_link,
            product_id=job.product_id,
            creator_profile_id=creator_profile_id,
            product_catalog_service=catalog,
        )
        if not validation["valid"]:
            return {
                "success": False,
                "reason": "invalid_media_link",
                "job_id": str(job_id),
                **validation,
            }

        normalized_link = validation["media_link"]
        metadata = {
            "media_link_workflow": {
                "source": "PublishingService.complete_publishing_media_link_workflow",
                "validated": True,
                "manual_provider_step": True,
                "asset_only": not bool(job.product_id),
            }
        }
        verified_job = self.record_publishing_job_media_link(
            job_id,
            media_link=normalized_link,
            provider_metadata=metadata,
            complete=False,
        )
        completed_job = self.record_publishing_job_media_link(
            job_id,
            media_link=normalized_link,
            provider_metadata=metadata,
            complete=True,
        )
        product = None
        if job.product_id and catalog is not None:
            product = catalog.complete_publishing_media_link(
                product_id=job.product_id,
                creator_profile_id=creator_profile_id,
                media_link=normalized_link,
            )
        return {
            "success": True,
            "job_id": job_id,
            "verified_job": verified_job,
            "job": completed_job,
            "product": product,
            "media_link": normalized_link,
            "warnings": validation["warnings"],
        }

    @staticmethod
    def _valid_media_link_url(media_link: str) -> bool:
        parsed = urlparse(media_link)
        return parsed.scheme in {"http", "https"} and bool(parsed.netloc)

    @staticmethod
    def _product_catalog_service():
        from app.services.product_catalog_service import ProductCatalogService

        return ProductCatalogService()

    def record_publishing_job_failure(
        self,
        job_id: UUID,
        *,
        failure_reason: Any,
        provider_status: str = "failed",
        provider_metadata: Mapping[str, Any] | None = None,
    ) -> PublishingJob | None:
        return self.publishing_repository.mark_job_failed(
            job_id,
            failure_reason=self.normalize_provider_error(failure_reason) or "",
            provider_status=provider_status,
            provider_metadata=provider_metadata,
        )

    def schedule_publishing_job_retry(
        self,
        job_id: UUID,
        *,
        next_retry_at: datetime,
        failure_reason: Any = None,
    ) -> PublishingJob | None:
        return self.publishing_repository.schedule_job_retry(
            job_id,
            next_retry_at=next_retry_at,
            failure_reason=self.normalize_provider_error(failure_reason),
        )

    def build_product_publishing_result(
        self,
        job: PublishingJob | Mapping[str, Any],
    ) -> dict[str, Any]:
        """Return Product-consumable execution output without mutating Product."""

        record = self.project_publishing_job_record(job)
        status_job = job if isinstance(job, PublishingJob) else PublishingJob.from_row(job)
        status_projection = build_publishing_status_projection(status_job)
        return {
            "product_id": record.get("product_id"),
            "asset_id": record.get("asset_id"),
            "provider": record.get("provider"),
            "publishing_status": status_projection.publishing_status,
            "provider_status": record.get("provider_status"),
            "upload_status": status_projection.upload_status,
            "media_link_status": status_projection.media_link_status,
            "retry_state": status_projection.retry_state,
            "provider_execution": self.build_provider_execution_metadata(status_job),
            "provider_output_url": record.get("provider_output_url"),
            "provider_media_id": record.get("provider_media_id"),
            "provider_preview_media_id": record.get("provider_preview_media_id"),
            "provider_full_media_id": record.get("provider_full_media_id"),
            "provider_metadata": record.get("provider_metadata") or {},
            "failure_reason": record.get("provider_error"),
            "upload_started_at": status_projection.upload_started_at,
            "upload_completed_at": status_projection.upload_completed_at,
            "last_attempted_at": status_projection.last_attempted_at,
            "retry_count": status_projection.retry_count,
            "retry_scheduled_at": status_projection.retry_scheduled_at,
        }

    def upload_asset_media_item_for_job(
        self,
        *,
        job_id: UUID,
        fanvue_account_id: int,
        item: Mapping[str, Any],
        media_link_required: bool = False,
        persist_legacy_asset_state: bool = True,
    ) -> dict[str, Any]:
        """Execute one asset upload through a durable PublishingJob."""

        self.mark_publishing_job_uploading(job_id)
        upload_result = self.upload_asset_media_item(
            fanvue_account_id=fanvue_account_id,
            item=item,
        )
        asset_id = item.get("id")
        if upload_result.get("success"):
            payload = self.build_upload_success_payload(
                upload_result,
                default_status="uploaded",
            )
            updated_job = self.record_publishing_job_upload_result(
                job_id,
                upload_payload=payload,
                media_link_required=media_link_required,
            )
            if persist_legacy_asset_state and asset_id is not None:
                self.record_asset_upload_payload(
                    asset_id=int(asset_id),
                    upload_payload=payload,
                )
        else:
            payload = self.build_upload_failure_payload(upload_result)
            updated_job = self.record_publishing_job_failure(
                job_id,
                failure_reason=payload.get("provider_error") or upload_result,
                provider_metadata=payload.get("provider_metadata"),
            )
            if persist_legacy_asset_state and asset_id is not None:
                self.record_asset_upload_payload(
                    asset_id=int(asset_id),
                    upload_payload=payload,
                )
        return {
            "job_id": job_id,
            "job": updated_job,
            "upload_result": upload_result,
        }

    def upload_publishing_queue_item(
        self,
        job_id: UUID,
        *,
        provider_account_id: int,
    ) -> dict[str, Any]:
        """Upload a queued job using its Publishing-owned execution context."""

        item = self.get_publishing_queue_item(job_id)
        if not item:
            return {
                "success": False,
                "reason": "publishing_job_not_found",
                "job_id": str(job_id),
            }
        upload_item = item.build_upload_item()
        if not upload_item:
            return {
                "success": False,
                "reason": "publishing_job_not_ready_to_upload",
                "job_id": str(job_id),
            }
        result = self.upload_asset_media_item_for_job(
            job_id=job_id,
            fanvue_account_id=provider_account_id,
            item=upload_item,
            media_link_required=item.job.media_link_status
            in {
                PublishingMediaLinkStatus.REQUIRED,
                PublishingMediaLinkStatus.PENDING,
            },
        )
        return {
            "success": bool(result.get("upload_result", {}).get("success")),
            **result,
        }

    def retry_publishing_queue_item(
        self,
        job_id: UUID,
        *,
        provider_account_id: int,
        next_retry_at: datetime | None = None,
    ) -> dict[str, Any]:
        """Requeue and upload an existing failed PublishingJob."""

        item = self.get_publishing_queue_item(job_id)
        if not item:
            return {
                "success": False,
                "reason": "publishing_job_not_found",
                "job_id": str(job_id),
            }
        upload_item = item.build_upload_item(allow_retry=True)
        if not upload_item:
            return {
                "success": False,
                "reason": "publishing_job_not_retryable",
                "job_id": str(job_id),
            }
        self.schedule_publishing_job_retry(
            job_id,
            next_retry_at=next_retry_at or datetime.now(),
            failure_reason=item.failure_summary,
        )
        result = self.upload_asset_media_item_for_job(
            job_id=job_id,
            fanvue_account_id=provider_account_id,
            item=upload_item,
            media_link_required=item.job.media_link_status
            in {
                PublishingMediaLinkStatus.REQUIRED,
                PublishingMediaLinkStatus.PENDING,
            },
        )
        return {
            "success": bool(result.get("upload_result", {}).get("success")),
            **result,
        }

    def get_provider_status(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        return self._publishing_provider.get_publishing_status(
            publishing_record
        )

    def has_provider_media(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> bool:
        if not publishing_record:
            return False
        return bool(
            publishing_record.get("provider_media_id")
            or publishing_record.get("provider_preview_media_id")
            or publishing_record.get("provider_full_media_id")
        )

    def get_provider_output(
        self,
        publishing_record: Mapping[str, Any] | None,
    ) -> str | None:
        return self._publishing_provider.retrieve_provider_output(
            publishing_record
        )

    def get_asset_provider_status(self, asset_id: int) -> str | None:
        return self.get_provider_status(self.get_by_asset_id(asset_id))

    def get_product_provider_status(self, product_id: UUID) -> str | None:
        return self.get_provider_status(self.get_by_product_id(product_id))

    def asset_has_provider_media(self, asset_id: int) -> bool:
        return self.has_provider_media(self.get_by_asset_id(asset_id))

    def product_has_provider_media(self, product_id: UUID) -> bool:
        return self.has_provider_media(self.get_by_product_id(product_id))

    def get_product_provider_output(self, product_id: UUID) -> str | None:
        return self.get_provider_output(self.get_by_product_id(product_id))

    def project_legacy_asset_record(
        self,
        asset: Any,
    ) -> dict[str, Any] | None:
        if not asset:
            return None
        return self.publishing_repository.project_content_item(
            {
                "id": getattr(asset, "id", None),
                "fanvue_account_id": getattr(asset, "fanvue_account_id", None),
                "fanvue_upload_status": getattr(
                    asset,
                    "fanvue_upload_status",
                    None,
                ),
                "fanvue_upload_error": getattr(
                    asset,
                    "fanvue_upload_error",
                    None,
                ),
                "fanvue_media_preview_uuid": getattr(
                    asset,
                    "fanvue_media_preview_uuid",
                    None,
                ),
                "fanvue_media_full_uuid": getattr(
                    asset,
                    "fanvue_media_full_uuid",
                    None,
                ),
                "created_at": getattr(asset, "created_at", None),
            }
        )

    def project_legacy_product_record(
        self,
        product: Any,
    ) -> dict[str, Any] | None:
        if not product:
            return None
        return self.publishing_repository.project_product(
            {
                "id": getattr(product, "id", None),
                "legacy_content_item_id": getattr(
                    product,
                    "legacy_content_item_id",
                    None,
                ),
                "media_link": getattr(product, "media_link", None),
                "fulfillment_status": getattr(
                    product,
                    "fulfillment_status",
                    None,
                ),
                "fulfillment_strategy": getattr(
                    product,
                    "fulfillment_strategy",
                    None,
                ),
                "delivery_type": getattr(product, "delivery_type", None),
                "approval_status": product_approval_status_from_metadata(
                    getattr(product, "metadata", None)
                ).value,
                "metadata": getattr(product, "metadata", None),
                "created_at": getattr(product, "created_at", None),
                "updated_at": getattr(product, "updated_at", None),
            }
        )

    def project_experience_readiness(
        self,
        experience: Any,
        *,
        asset_records: list[Mapping[str, Any]] | tuple[Mapping[str, Any], ...] = (),
    ) -> ExperiencePublishingReadiness:
        """Return read-only publishing readiness for an Experience.

        Publishing does not own Experience state; this projection only interprets
        the supplied Experience and optional asset publishing records.
        """

        asset_ids = tuple(getattr(experience, "ordered_asset_ids", None) or ())
        if not asset_ids:
            asset_ids = tuple(getattr(experience, "asset_ids", None) or ())
        records = tuple(asset_records or ())
        ready_count = sum(1 for record in records if self.has_provider_media(record))
        if not asset_ids:
            status = "missing_assets"
            detail = "Experience has no attached Assets."
        elif records and ready_count == len(asset_ids):
            status = "ready"
            detail = "All Experience Assets have provider media."
        elif records and ready_count:
            status = "partial"
            detail = "Some Experience Assets have provider media."
        elif records:
            status = "not_ready"
            detail = "Experience Assets are not provider-ready."
        else:
            status = "unknown"
            detail = "Experience Asset publishing records were not supplied."
        missing_count = max(0, len(asset_ids) - len(records))
        readiness_ratio = (
            round(ready_count / len(asset_ids), 2)
            if asset_ids
            else 0.0
        )
        return ExperiencePublishingReadiness(
            experience_id=str(getattr(experience, "experience_id", "unknown")),
            status=status,
            detail=detail,
            asset_count=len(asset_ids),
            ready_asset_count=ready_count,
            source="PublishingService",
            compatibility=False,
            metadata={
                "projection": "experience_readiness",
                "relationship_source": "experience",
                "ordered_asset_ids": asset_ids,
                "asset_records_supplied": len(records),
                "missing_record_count": missing_count,
                "readiness_ratio": readiness_ratio,
                "owns_experience_state": False,
            },
        )

    def get_provider_status_display(
        self,
        publishing_record: Mapping[str, Any] | None,
        *,
        provider_name: str = "Provider",
        missing_detail: str = "No local asset is attached.",
        local_detail: str = "Local asset only",
    ) -> tuple[str, str]:
        not_uploaded = PROVIDER_STATUS_NOT_UPLOADED.format(
            provider=provider_name
        )
        if not publishing_record:
            return not_uploaded, missing_detail

        status = str(publishing_record.get("provider_status") or "").lower()
        error = publishing_record.get("provider_error")
        media_id = (
            publishing_record.get("provider_media_id")
            or publishing_record.get("provider_full_media_id")
            or publishing_record.get("provider_preview_media_id")
        )
        if error or status in {"failed", "error"}:
            return (
                PROVIDER_STATUS_FAILED.format(provider=provider_name),
                str(error or status),
            )
        if media_id:
            return (
                PROVIDER_STATUS_UPLOADED.format(provider=provider_name),
                media_id,
            )
        return not_uploaded, local_detail

    def get_product_provider_status_display(
        self,
        product_record: Mapping[str, Any] | None,
        asset_records: list[Mapping[str, Any] | None]
        | tuple[Mapping[str, Any] | None, ...],
        *,
        provider_name: str = "Provider",
    ) -> tuple[str, str]:
        approval_status = self._product_approval_status(product_record)
        if approval_status == ProductApprovalStatus.REJECTED.value:
            return "Not Approved", "Product was rejected during creator review."
        if approval_status == ProductApprovalStatus.NEEDS_REVIEW.value:
            return "Needs Approval", "Product must be approved before publishing."

        output_url = self.get_provider_output(product_record)
        if output_url and str(output_url).startswith(("http://", "https://")):
            return (
                PROVIDER_STATUS_URL_AVAILABLE.format(provider=provider_name),
                output_url,
            )

        uploaded = PROVIDER_STATUS_UPLOADED.format(provider=provider_name)
        failed = PROVIDER_STATUS_FAILED.format(provider=provider_name)
        not_uploaded = PROVIDER_STATUS_NOT_UPLOADED.format(
            provider=provider_name
        )
        statuses = [
            self.get_provider_status_display(
                record,
                provider_name=provider_name,
            )[0]
            for record in asset_records
        ]
        if any(status == failed for status in statuses):
            return failed, "At least one asset failed upload."
        if statuses and all(status == uploaded for status in statuses):
            return uploaded, f"All attached assets have {provider_name} media IDs."
        if any(status == uploaded for status in statuses):
            return uploaded, f"Some attached assets have {provider_name} media IDs."
        return not_uploaded, "Local asset only"

    @staticmethod
    def _product_approval_status(
        product_record: Mapping[str, Any] | None,
    ) -> str | None:
        if not product_record:
            return None
        explicit_status = product_record.get("approval_status")
        if explicit_status:
            return str(explicit_status).upper()
        if "approval" not in (product_record.get("metadata") or {}):
            return None
        return product_approval_status_from_metadata(
            product_record.get("metadata")
        ).value

    def normalize_provider_metadata(self, metadata: Any) -> dict[str, Any]:
        if metadata is None:
            return {}
        if isinstance(metadata, Mapping):
            return dict(metadata)
        return {"raw": metadata}

    def normalize_provider_error(self, error: Any) -> str | None:
        if error is None:
            return None
        return str(error)

    def build_provider_status_update(
        self,
        *,
        provider_status: str,
        provider_error: Any = None,
        provider_metadata: Any = None,
    ) -> dict[str, Any]:
        return {
            "provider_status": provider_status,
            "provider_error": self.normalize_provider_error(provider_error),
            "provider_metadata": self.normalize_provider_metadata(
                provider_metadata
            ),
        }

    def build_upload_success_payload(
        self,
        upload_result: Mapping[str, Any],
        *,
        default_status: str = "uploaded",
    ) -> dict[str, Any]:
        return self._publishing_provider.normalize_provider_response(
            upload_result,
            default_status=default_status,
            provider_error=None,
            fallback_media_ids=True,
        )

    def build_upload_failure_payload(
        self,
        upload_result: Mapping[str, Any] | None = None,
        *,
        error: Any = None,
        default_status: str = "failed",
    ) -> dict[str, Any]:
        upload_result = upload_result or {}
        provider_error = (
            error
            if error is not None
            else str(upload_result.get("error"))
            if "error" in upload_result
            else None
        )
        return self._publishing_provider.normalize_provider_response(
            upload_result,
            default_status=default_status,
            provider_error=provider_error,
            fallback_media_ids=False,
        )

    def upload_asset_media_pair(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
        preview_path: str,
        full_path: str,
        classification: str,
    ) -> dict[str, Any]:
        return self._publishing_provider.publish(
            asset_id=asset_id,
            provider_account_id=fanvue_account_id,
            preview_path=preview_path,
            full_path=full_path,
            classification=classification,
        )

    def upload_asset_media_item(
        self,
        *,
        fanvue_account_id: int,
        item: Mapping[str, Any],
    ) -> dict[str, Any]:
        return self._publishing_provider.publish_media_item(
            provider_account_id=fanvue_account_id,
            item=item,
        )

    def create_wall_post(
        self,
        *,
        fanvue_account_id: int,
        text: str,
        media_ids: list[str] | None = None,
        audience: str = "followers-and-subscribers",
        execution_origin: str = "operator",
    ) -> dict[str, Any]:
        return self._publishing_provider.create_wall_post(
            provider_account_id=fanvue_account_id,
            text=text,
            media_ids=media_ids,
            audience=audience,
            execution_origin=execution_origin,
        )

    def record_asset_upload_payload(
        self,
        *,
        asset_id: int,
        upload_payload: Mapping[str, Any],
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                preview_uuid = upload_payload.get("provider_preview_media_id")
                full_uuid = upload_payload.get("provider_full_media_id")
                upload_status = upload_payload.get("provider_status")
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        fanvue_media_preview_uuid = %s,
                        fanvue_media_full_uuid = %s,
                        fanvue_preview_upload_status = %s,
                        fanvue_full_upload_status = %s,
                        fanvue_upload_status = %s,
                        fanvue_upload_error = %s,
                        fanvue_upload_metadata = %s::jsonb,
                        fanvue_uploaded_at = NOW()
                    WHERE id = %s
                    """,
                    (
                        preview_uuid,
                        full_uuid,
                        upload_status if preview_uuid else None,
                        upload_status if full_uuid else None,
                        upload_status,
                        upload_payload.get("provider_error"),
                        json.dumps(upload_payload.get("provider_metadata") or {}),
                        asset_id,
                    ),
                )
            if hasattr(conn, "commit"):
                conn.commit()

    def mark_asset_upload_not_requested(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        fanvue_upload_status = 'not_requested',
                        fanvue_upload_error = NULL
                    WHERE id = %s
                    AND fanvue_account_id = %s
                    """,
                    (asset_id, fanvue_account_id),
                )

    def record_asset_upload_success(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
        preview_result: Mapping[str, Any],
        full_result: Mapping[str, Any],
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        upload_status = 'pending',
                        fanvue_media_preview_uuid = %s,
                        fanvue_media_full_uuid = %s,
                        fanvue_upload_status = 'completed',
                        fanvue_upload_error = NULL,
                        fanvue_uploaded_at = NOW()
                    WHERE id = %s
                    AND fanvue_account_id = %s
                    """,
                    (
                        preview_result.get("preview_uuid")
                        or preview_result.get("media_uuid"),
                        full_result.get("full_uuid")
                        or full_result.get("media_uuid"),
                        asset_id,
                        fanvue_account_id,
                    ),
                )

    def record_asset_upload_failure(
        self,
        *,
        asset_id: int,
        fanvue_account_id: int,
        error: Any,
    ) -> None:
        with self._connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE content_items
                    SET
                        fanvue_upload_status = 'failed',
                        fanvue_upload_error = %s
                    WHERE id = %s
                    AND fanvue_account_id = %s
                    """,
                    (
                        self.normalize_provider_error(error),
                        asset_id,
                        fanvue_account_id,
                    ),
                )
