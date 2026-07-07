"""Publishing Automation orchestration read service.

PublishingAutomationService determines publishing readiness and next publishing
actions from existing Creator OS read models. It does not create Publishing
Jobs, upload media, verify Media Links, activate Products, or execute Telegram.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_workflow import CreatorWorkflowSnapshot
from app.models.product_lifecycle import ProductLifecycle, ProductLifecycleStage
from app.models.publishing_automation import (
    PublishingAutomationAction,
    PublishingAutomationRecommendation,
    PublishingAutomationState,
    PublishingAutomationStatus,
)

if TYPE_CHECKING:
    from app.services.product_lifecycle_service import ProductLifecycleService
    from app.services.publishing_service import PublishingService


class PublishingAutomationService:
    """Derive publishing automation status without mutating state."""

    def __init__(
        self,
        *,
        product_lifecycle_service: "ProductLifecycleService | None" = None,
        publishing_service: "PublishingService | None" = None,
    ):
        self._product_lifecycle = product_lifecycle_service
        self._publishing = publishing_service

    @property
    def product_lifecycle(self) -> "ProductLifecycleService":
        if self._product_lifecycle is None:
            from app.services.product_lifecycle_service import ProductLifecycleService

            self._product_lifecycle = ProductLifecycleService()
        return self._product_lifecycle

    @property
    def publishing(self) -> "PublishingService":
        if self._publishing is None:
            from app.services.publishing_service import PublishingService

            self._publishing = PublishingService()
        return self._publishing

    def build_status(
        self,
        *,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> PublishingAutomationStatus:
        resolved_lifecycle = self._resolve_lifecycle(
            lifecycle,
            workflow_snapshot=workflow_snapshot,
        )
        projection = self._resolve_publishing_projection(
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
            lifecycle=resolved_lifecycle,
        )
        publishing_status = self._text(
            self._read(projection, "publishing_status")
            or self._read(publishing_queue_item, "publishing_status")
            or self._read(resolved_lifecycle, "publishing_status")
        )
        media_link_status = self._text(
            self._read(projection, "media_link_status")
            or self._read(publishing_queue_item, "media_link_status")
            or self._read(resolved_lifecycle, "media_link_status")
        )
        provider_status = self._safe_text(
            self._read(projection, "provider_status")
            or self._read(publishing_queue_item, "provider_status")
        )
        provider_error = self._safe_text(
            self._read(projection, "provider_error")
            or self._read(publishing_queue_item, "provider_error")
            or self._read(projection, "failure_reason")
            or self._read(publishing_queue_item, "failure_summary")
        )
        state = self.determine_state(
            lifecycle=resolved_lifecycle,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
            provider_error=provider_error,
            publishing_queue_item=publishing_queue_item,
        )
        recommendation = self.recommend_next_action(
            state,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
        )
        manual_media_link_required = state in {
            PublishingAutomationState.WAITING_FOR_MEDIA_LINK,
            PublishingAutomationState.VERIFY_MEDIA_LINK,
        }
        attention_required = state == PublishingAutomationState.NEEDS_ATTENTION
        telegram_ready = bool(self._read(resolved_lifecycle, "telegram_ready")) or (
            state == PublishingAutomationState.READY_FOR_TELEGRAM
        )
        return PublishingAutomationStatus(
            state=state,
            recommendation=recommendation,
            product_id=self._safe_text(self._read(resolved_lifecycle, "product_id")),
            lifecycle=resolved_lifecycle,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
            provider_status=provider_status,
            provider_error=provider_error,
            manual_media_link_required=manual_media_link_required,
            attention_required=attention_required,
            telegram_ready=telegram_ready,
            evidence={
                "publishing_status": publishing_status,
                "media_link_status": media_link_status,
                "provider_status": provider_status,
                "provider_error": provider_error,
                **dict(metadata or {}),
            },
            compatibility={
                "source": "publishing_automation",
                "owner": "PublishingAutomationService",
                "read_only": True,
                "orchestration_only": True,
                "provider_neutral": True,
                "manual_media_link_creation_preserved": True,
                "does_not_upload": True,
                "does_not_create_jobs": True,
                "does_not_verify_media_links": True,
                "does_not_activate_products": True,
                "does_not_execute_telegram": True,
            },
        )

    def build_from_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any],
        **context: Any,
    ) -> PublishingAutomationStatus:
        return self.build_status(lifecycle=lifecycle, **context)

    def build_from_workflow_snapshot(
        self,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any],
        **context: Any,
    ) -> PublishingAutomationStatus:
        return self.build_status(workflow_snapshot=workflow_snapshot, **context)

    def determine_state(
        self,
        *,
        lifecycle: ProductLifecycle | None,
        publishing_status: str | None,
        media_link_status: str | None,
        provider_error: str | None = None,
        publishing_queue_item: Any | None = None,
    ) -> PublishingAutomationState:
        lifecycle_stage = self._read(lifecycle, "stage")
        if self._bool(self._read(publishing_queue_item, "failed_upload")):
            return PublishingAutomationState.NEEDS_ATTENTION
        if provider_error:
            return PublishingAutomationState.NEEDS_ATTENTION
        if publishing_status in {"FAILED", "RETRY_REQUIRED", "ARCHIVED"}:
            return PublishingAutomationState.NEEDS_ATTENTION
        if self._read(lifecycle, "telegram_ready") or lifecycle_stage == (
            ProductLifecycleStage.TELEGRAM_READY
        ):
            return PublishingAutomationState.READY_FOR_TELEGRAM
        if lifecycle_stage == ProductLifecycleStage.ACTIVE:
            return PublishingAutomationState.PUBLISHING_COMPLETE
        if publishing_status == "PUBLISHING_COMPLETE":
            return PublishingAutomationState.PUBLISHING_COMPLETE
        if media_link_status == "CREATED" or publishing_status == "MEDIA_LINK_VERIFIED":
            return PublishingAutomationState.VERIFY_MEDIA_LINK
        if publishing_status == "WAITING_FOR_MEDIA_LINK" or media_link_status in {
            "REQUIRED",
            "PENDING",
            "WAITING_FOR_MEDIA_LINK",
        }:
            return PublishingAutomationState.WAITING_FOR_MEDIA_LINK
        if publishing_status in {"UPLOADING", "UPLOADED"}:
            return PublishingAutomationState.UPLOAD_IN_PROGRESS
        if publishing_status == "QUEUED":
            return PublishingAutomationState.QUEUED
        if lifecycle_stage in {
            ProductLifecycleStage.APPROVED,
            ProductLifecycleStage.PUBLISHING_READY,
        }:
            return PublishingAutomationState.READY_TO_PUBLISH
        return PublishingAutomationState.NOT_READY

    @staticmethod
    def recommend_next_action(
        state: PublishingAutomationState,
        *,
        publishing_status: str | None = None,
        media_link_status: str | None = None,
    ) -> PublishingAutomationRecommendation:
        mapping = {
            PublishingAutomationState.NOT_READY: (
                PublishingAutomationAction.NO_PUBLISHING_ACTION,
                "Product is not ready for publishing.",
            ),
            PublishingAutomationState.READY_TO_PUBLISH: (
                PublishingAutomationAction.READY_TO_PUBLISH,
                "Approved Product is ready for Publishing-owned queueing.",
            ),
            PublishingAutomationState.QUEUED: (
                PublishingAutomationAction.MONITOR_UPLOAD,
                "Publishing Job is queued for upload tracking.",
            ),
            PublishingAutomationState.UPLOAD_IN_PROGRESS: (
                PublishingAutomationAction.MONITOR_UPLOAD,
                "Upload is in progress or awaiting provider upload completion.",
            ),
            PublishingAutomationState.WAITING_FOR_MEDIA_LINK: (
                PublishingAutomationAction.WAITING_FOR_MEDIA_LINK,
                "Creator must manually create the provider Media Link.",
            ),
            PublishingAutomationState.VERIFY_MEDIA_LINK: (
                PublishingAutomationAction.VERIFY_MEDIA_LINK,
                "Media Link can be verified through the existing Publishing workflow.",
            ),
            PublishingAutomationState.PUBLISHING_COMPLETE: (
                PublishingAutomationAction.PUBLISHING_COMPLETE,
                "Publishing is complete and Product activation can be observed.",
            ),
            PublishingAutomationState.READY_FOR_TELEGRAM: (
                PublishingAutomationAction.READY_FOR_TELEGRAM,
                "Product is active and ready for Telegram commerce.",
            ),
            PublishingAutomationState.NEEDS_ATTENTION: (
                PublishingAutomationAction.REVIEW_PUBLISHING_FAILURE,
                "Publishing requires creator/operator attention.",
            ),
        }
        action, reason = mapping[state]
        evidence = []
        if publishing_status:
            evidence.append(f"publishing_status={publishing_status}")
        if media_link_status:
            evidence.append(f"media_link_status={media_link_status}")
        if evidence:
            reason = f"{reason} ({', '.join(evidence)})"
        return PublishingAutomationRecommendation(
            action=action,
            label=action.value,
            reason=reason,
        )

    def _resolve_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None,
        *,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
    ) -> ProductLifecycle | None:
        if isinstance(lifecycle, ProductLifecycle):
            return lifecycle
        if lifecycle is not None:
            return self.product_lifecycle.build_lifecycle(lifecycle)
        if workflow_snapshot is not None:
            return self.product_lifecycle.build_lifecycle(workflow_snapshot)
        return None

    def _resolve_publishing_projection(
        self,
        *,
        publishing_projection: Any | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
        lifecycle: ProductLifecycle | None,
    ) -> Any | None:
        if publishing_projection is not None:
            return publishing_projection
        if publishing_queue_item is not None:
            return publishing_queue_item
        if publishing_job is not None:
            try:
                return self.publishing.project_publishing_status(publishing_job)
            except Exception:
                return None
        if lifecycle is None:
            return None
        return {
            "publishing_status": lifecycle.publishing_status,
            "media_link_status": lifecycle.media_link_status,
        }

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value)).strip().upper()

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _bool(value: Any) -> bool:
        return bool(value)
