"""Creator Workflow orchestration read service.

CreatorWorkflowService assembles provider-neutral workflow snapshots from
existing domain read models. It does not own import, intelligence, strategy,
review, catalog, publishing, or Telegram business logic.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_intent import CreatorIntent
from app.models.creator_workflow import (
    CreatorWorkflowSnapshot,
    CreatorWorkflowStage,
    CreatorWorkflowStageStatus,
    WORKFLOW_STAGE_ORDER,
)

if TYPE_CHECKING:
    from app.services.creator_review_service import CreatorReviewService
    from app.services.product_review_service import ProductReviewService
    from app.services.publishing_service import PublishingService


class CreatorWorkflowService:
    """Assemble read-only Creator Workflow status from existing domains."""

    def __init__(
        self,
        *,
        creator_review_service: "CreatorReviewService | None" = None,
        product_review_service: "ProductReviewService | None" = None,
        publishing_service: "PublishingService | None" = None,
    ):
        self._creator_review = creator_review_service
        self._product_review = product_review_service
        self._publishing = publishing_service

    @property
    def creator_review(self) -> "CreatorReviewService":
        if self._creator_review is None:
            from app.services.creator_review_service import CreatorReviewService

            self._creator_review = CreatorReviewService()
        return self._creator_review

    @property
    def product_review(self) -> "ProductReviewService":
        if self._product_review is None:
            from app.services.product_review_service import ProductReviewService

            self._product_review = ProductReviewService()
        return self._product_review

    @property
    def publishing(self) -> "PublishingService":
        if self._publishing is None:
            from app.services.publishing_service import PublishingService

            self._publishing = PublishingService()
        return self._publishing

    def build_snapshot(
        self,
        *,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        workflow_result: Any | None = None,
        product_display: Any | None = None,
        creator_review: Any | None = None,
        product_review: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorWorkflowSnapshot:
        resolved_intent = self._resolve_creator_intent(
            creator_intent,
            workflow_result=workflow_result,
        )
        resolved_creator_review = self._resolve_creator_review(
            creator_review,
            workflow_result=workflow_result,
        )
        resolved_product_review = self._resolve_product_review(
            product_review,
            product_display=product_display,
        )
        product = self._attribute(product_display, "product")
        publishing_status = self._publishing_status(
            product=product,
            product_display=product_display,
            product_review=resolved_product_review,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
        )
        media_link_status = self._media_link_status(
            product=product,
            product_display=product_display,
            publishing_status=publishing_status,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
        )
        asset_ids = self._asset_ids(
            workflow_result=workflow_result,
            product_display=product_display,
        )
        product_status = self._product_status(product, resolved_product_review)
        approval_status = self._approval_status(product, resolved_product_review)
        telegram_ready = self._telegram_ready(
            product=product,
            product_status=product_status,
            approval_status=approval_status,
        )

        completed = self._completed_stage_map(
            workflow_result=workflow_result,
            creator_review=resolved_creator_review,
            product_review=resolved_product_review,
            product=product,
            product_status=product_status,
            approval_status=approval_status,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
            telegram_ready=telegram_ready,
        )
        stages = self._stage_statuses(
            completed,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
            product_status=product_status,
            approval_status=approval_status,
        )
        completed_stages = tuple(
            stage for stage, value in completed.items() if value is True
        )
        blocked_stages = tuple(
            item.stage for item in stages if item.status == "blocked"
        )
        pending_stages = tuple(
            item.stage for item in stages if item.status in {"pending", "blocked"}
        )
        current_stage = self._current_stage(stages)
        workflow_metadata = {
            "source": "creator_workflow",
            "owner": "CreatorWorkflowService",
            "read_only": True,
            "orchestration_only": True,
            "provider_neutral": True,
            **dict(metadata or {}),
        }
        return CreatorWorkflowSnapshot(
            workflow_id=self._workflow_id(
                workflow_result=workflow_result,
                product=product,
            ),
            current_stage=current_stage,
            stages=stages,
            creator_intent=resolved_intent,
            asset_ids=asset_ids,
            product_id=self._safe_text(
                self._attribute(product, "id")
                or self._attribute(resolved_product_review, "product_id")
            ),
            experience_id=self._experience_id(product_display, workflow_result),
            content_type=(
                resolved_intent.content_type.value if resolved_intent else None
            ),
            product_status=product_status,
            approval_status=approval_status,
            publishing_status=publishing_status,
            media_link_status=media_link_status,
            telegram_ready=telegram_ready,
            completed_stages=completed_stages,
            pending_stages=pending_stages,
            blocked_stages=blocked_stages,
            metadata=workflow_metadata,
        )

    def build_from_import_result(
        self,
        workflow_result: Any,
        *,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorWorkflowSnapshot:
        return self.build_snapshot(
            creator_intent=creator_intent,
            workflow_result=workflow_result,
            metadata=metadata,
        )

    def build_from_product_display(
        self,
        product_display: Any,
        *,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorWorkflowSnapshot:
        return self.build_snapshot(
            creator_intent=creator_intent,
            product_display=product_display,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
            metadata=metadata,
        )

    def build_for_product(
        self,
        product_id: Any,
        *,
        creator_profile_id: int,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorWorkflowSnapshot:
        review = self.product_review.build_review(
            product_id,
            creator_profile_id=creator_profile_id,
        )
        return self.build_snapshot(
            creator_intent=creator_intent,
            product_review=review,
            metadata=metadata,
        )

    def _resolve_creator_intent(
        self,
        creator_intent: CreatorIntent | Mapping[str, Any] | str | None,
        *,
        workflow_result: Any | None,
    ) -> CreatorIntent | None:
        if creator_intent is not None:
            return CreatorIntent.from_value(creator_intent)
        value = self._attribute(workflow_result, "creator_intent")
        if value is not None:
            return CreatorIntent.from_value(value)
        upload_intent = self._attribute(workflow_result, "upload_intent")
        return CreatorIntent.from_legacy(upload_intent) if upload_intent else None

    def _resolve_creator_review(
        self,
        creator_review: Any | None,
        *,
        workflow_result: Any | None,
    ) -> Any | None:
        if creator_review is not None:
            return creator_review
        if workflow_result is None:
            return None
        try:
            return self.creator_review.build_review(workflow_result)
        except Exception:
            return None

    def _resolve_product_review(
        self,
        product_review: Any | None,
        *,
        product_display: Any | None,
    ) -> Any | None:
        if product_review is not None:
            return product_review
        if product_display is None:
            return None
        try:
            return self.product_review.build_review_from_display(product_display)
        except Exception:
            return None

    def _completed_stage_map(
        self,
        *,
        workflow_result: Any | None,
        creator_review: Any | None,
        product_review: Any | None,
        product: Any | None,
        product_status: str | None,
        approval_status: str | None,
        publishing_status: str | None,
        media_link_status: str | None,
        telegram_ready: bool,
    ) -> dict[CreatorWorkflowStage, bool]:
        imported = (
            bool(self._attribute(workflow_result, "success"))
            or product is not None
            or product_review is not None
        )
        content_analyzed = bool(
            self._attribute(workflow_result, "content_intelligence")
            or self._attribute(workflow_result, "asset_understanding")
            or product is not None
            or product_review is not None
        )
        experience_created = bool(
            self._attribute(workflow_result, "experience_recommendation")
            or self._attribute(product_review, "experience")
            or product is not None
        )
        product_strategy = bool(
            self._attribute(workflow_result, "product_strategy_result")
            or self._attribute(product_review, "product")
            or product is not None
        )
        commerce_strategy = bool(
            self._attribute(workflow_result, "commerce_strategy_result")
            or self._attribute(product_review, "commerce")
            or self._commerce_metadata(product)
        )
        in_review = bool(creator_review or product_review or product is not None)
        approved = approval_status in {"APPROVED", "READY_TO_PUBLISH"} or (
            product_status == "ACTIVE"
        )
        publishing = bool(
            publishing_status
            and publishing_status not in {"NOT_QUEUED", "Unavailable", "Unknown"}
        )
        active = product_status == "ACTIVE"
        waiting_for_media_link = media_link_status in {"REQUIRED", "PENDING"} or (
            publishing_status == "WAITING_FOR_MEDIA_LINK"
        ) or media_link_status == "CREATED" or active or telegram_ready
        return {
            CreatorWorkflowStage.IMPORTED: imported,
            CreatorWorkflowStage.CONTENT_ANALYZED: content_analyzed,
            CreatorWorkflowStage.EXPERIENCE_CREATED: experience_created,
            CreatorWorkflowStage.PRODUCT_STRATEGY_READY: product_strategy,
            CreatorWorkflowStage.COMMERCE_STRATEGY_READY: commerce_strategy,
            CreatorWorkflowStage.IN_CREATOR_REVIEW: in_review,
            CreatorWorkflowStage.APPROVED: approved,
            CreatorWorkflowStage.PUBLISHING: publishing,
            CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK: waiting_for_media_link,
            CreatorWorkflowStage.ACTIVE: active,
            CreatorWorkflowStage.TELEGRAM_READY: telegram_ready,
        }

    def _stage_statuses(
        self,
        completed: Mapping[CreatorWorkflowStage, bool],
        *,
        publishing_status: str | None,
        media_link_status: str | None,
        product_status: str | None,
        approval_status: str | None,
    ) -> tuple[CreatorWorkflowStageStatus, ...]:
        first_incomplete_seen = False
        items: list[CreatorWorkflowStageStatus] = []
        for stage in WORKFLOW_STAGE_ORDER:
            is_complete = bool(completed.get(stage))
            if is_complete:
                status = "complete"
            elif not first_incomplete_seen:
                status = self._blocked_or_current(
                    stage,
                    publishing_status=publishing_status,
                    media_link_status=media_link_status,
                    product_status=product_status,
                    approval_status=approval_status,
                )
                first_incomplete_seen = True
            else:
                status = "pending"
            items.append(
                CreatorWorkflowStageStatus(
                    stage=stage,
                    status=status,
                    summary=self._stage_summary(
                        stage,
                        status,
                        publishing_status=publishing_status,
                        media_link_status=media_link_status,
                    ),
                    source=self._stage_source(stage),
                    compatibility={"read_model_only": True},
                )
            )
        return tuple(items)

    @staticmethod
    def _blocked_or_current(
        stage: CreatorWorkflowStage,
        *,
        publishing_status: str | None,
        media_link_status: str | None,
        product_status: str | None,
        approval_status: str | None,
    ) -> str:
        if stage == CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK and (
            publishing_status == "WAITING_FOR_MEDIA_LINK"
            or media_link_status in {"REQUIRED", "PENDING"}
        ):
            return "current"
        if stage == CreatorWorkflowStage.ACTIVE and approval_status == "REJECTED":
            return "blocked"
        if stage == CreatorWorkflowStage.TELEGRAM_READY and product_status != "ACTIVE":
            return "pending"
        return "current"

    @staticmethod
    def _current_stage(
        stages: tuple[CreatorWorkflowStageStatus, ...],
    ) -> CreatorWorkflowStage:
        for item in stages:
            if item.status in {"current", "blocked", "pending"}:
                return item.stage
        return CreatorWorkflowStage.TELEGRAM_READY

    @staticmethod
    def _stage_summary(
        stage: CreatorWorkflowStage,
        status: str,
        *,
        publishing_status: str | None,
        media_link_status: str | None,
    ) -> str:
        if stage == CreatorWorkflowStage.PUBLISHING and publishing_status:
            return f"Publishing status: {publishing_status}"
        if stage == CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK and media_link_status:
            return f"Media link status: {media_link_status}"
        return f"{stage.value} is {status}."

    @staticmethod
    def _stage_source(stage: CreatorWorkflowStage) -> str:
        mapping = {
            CreatorWorkflowStage.IMPORTED: "AIImportWorkflowService",
            CreatorWorkflowStage.CONTENT_ANALYZED: "ContentIntelligenceService",
            CreatorWorkflowStage.EXPERIENCE_CREATED: "ExperienceIntelligenceService",
            CreatorWorkflowStage.PRODUCT_STRATEGY_READY: "ProductStrategyService",
            CreatorWorkflowStage.COMMERCE_STRATEGY_READY: "CommerceStrategyService",
            CreatorWorkflowStage.IN_CREATOR_REVIEW: "CreatorReviewService",
            CreatorWorkflowStage.APPROVED: "ProductCatalogService",
            CreatorWorkflowStage.PUBLISHING: "PublishingService",
            CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK: "PublishingService",
            CreatorWorkflowStage.ACTIVE: "ProductCatalogService",
            CreatorWorkflowStage.TELEGRAM_READY: "TelegramCommerceService",
        }
        return mapping[stage]

    def _publishing_status(
        self,
        *,
        product: Any | None,
        product_display: Any | None,
        product_review: Any | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
    ) -> str | None:
        value = self._attribute(publishing_queue_item, "publishing_status")
        if value:
            return str(value)
        if publishing_job is not None:
            try:
                return self.publishing.project_publishing_status(
                    publishing_job
                ).publishing_status
            except Exception:
                pass
        section = self._attribute(product_review, "publishing")
        value = self._attribute(section, "status")
        if value:
            return str(value)
        publishing = self._attribute(product_display, "publishing")
        value = self._attribute(publishing, "status")
        if value:
            return str(value)
        if self._attribute(product, "media_link"):
            return "PUBLISHING_COMPLETE"
        return None

    def _media_link_status(
        self,
        *,
        product: Any | None,
        product_display: Any | None,
        publishing_status: str | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
    ) -> str | None:
        value = self._attribute(publishing_queue_item, "media_link_status")
        if value:
            return str(value)
        if publishing_job is not None:
            try:
                return self.publishing.project_publishing_status(
                    publishing_job
                ).media_link_status
            except Exception:
                pass
        if self._attribute(product, "media_link"):
            return "CREATED"
        publishing = self._attribute(product_display, "publishing")
        status = self._attribute(publishing, "status")
        if status and str(status).lower() in {"ready", "provider url available"}:
            return "CREATED"
        if publishing_status == "WAITING_FOR_MEDIA_LINK":
            return "PENDING"
        return None

    @staticmethod
    def _telegram_ready(
        *,
        product: Any | None,
        product_status: str | None,
        approval_status: str | None,
    ) -> bool:
        if product_status != "ACTIVE":
            return False
        if approval_status not in {None, "APPROVED", "READY_TO_PUBLISH"}:
            return False
        media_link = CreatorWorkflowService._attribute(product, "media_link")
        delivery_type = CreatorWorkflowService._enum_value(
            CreatorWorkflowService._attribute(product, "delivery_type")
        )
        if delivery_type == "FREE":
            return True
        return bool(media_link)

    @staticmethod
    def _asset_ids(*, workflow_result: Any | None, product_display: Any | None) -> tuple[int, ...]:
        values = CreatorWorkflowService._attribute(workflow_result, "content_ids")
        if values:
            return tuple(int(value) for value in values if value is not None)
        content_id = CreatorWorkflowService._attribute(workflow_result, "content_id")
        if content_id is not None:
            return (int(content_id),)
        assets = CreatorWorkflowService._attribute(product_display, "ordered_assets") or ()
        asset_ids: list[int] = []
        for asset in assets:
            asset_id = CreatorWorkflowService._attribute(asset, "id")
            if asset_id is not None:
                asset_ids.append(int(asset_id))
        return tuple(asset_ids)

    @staticmethod
    def _experience_id(product_display: Any | None, workflow_result: Any | None) -> str | None:
        experience = CreatorWorkflowService._attribute(
            product_display,
            "experience_presentation",
        ) or CreatorWorkflowService._attribute(product_display, "experience")
        value = CreatorWorkflowService._attribute(experience, "experience_id")
        if value:
            return str(value)
        recommendation = CreatorWorkflowService._attribute(
            workflow_result,
            "experience_recommendation",
        )
        value = CreatorWorkflowService._attribute(recommendation, "experience_id")
        return str(value) if value else None

    @staticmethod
    def _workflow_id(*, workflow_result: Any | None, product: Any | None) -> str | None:
        product_id = CreatorWorkflowService._attribute(product, "id")
        if product_id:
            return f"product:{product_id}"
        content_id = CreatorWorkflowService._attribute(workflow_result, "content_id")
        if content_id:
            return f"asset:{content_id}"
        content_ids = CreatorWorkflowService._attribute(workflow_result, "content_ids")
        if content_ids:
            return "asset_batch:" + "-".join(str(value) for value in content_ids)
        return None

    @staticmethod
    def _product_status(product: Any | None, product_review: Any | None) -> str | None:
        return CreatorWorkflowService._enum_value(
            CreatorWorkflowService._attribute(product, "status")
            or CreatorWorkflowService._attribute(product_review, "product_status")
        )

    @staticmethod
    def _approval_status(product: Any | None, product_review: Any | None) -> str | None:
        value = CreatorWorkflowService._attribute(product_review, "approval_status")
        if value:
            return str(value)
        metadata = CreatorWorkflowService._attribute(product, "metadata") or {}
        approval = metadata.get("approval") if isinstance(metadata, Mapping) else None
        if isinstance(approval, Mapping):
            return CreatorWorkflowService._safe_text(approval.get("status"))
        return None

    @staticmethod
    def _commerce_metadata(product: Any | None) -> Mapping[str, Any]:
        metadata = CreatorWorkflowService._attribute(product, "metadata") or {}
        if not isinstance(metadata, Mapping):
            return {}
        commerce = metadata.get("commerce_intelligence") or {}
        return commerce if isinstance(commerce, Mapping) else {}

    @staticmethod
    def _attribute(value: Any, name: str, default: Any = None) -> Any:
        if value is None:
            return default
        if isinstance(value, Mapping):
            return value.get(name, default)
        return getattr(value, name, default)

    @staticmethod
    def _enum_value(value: Any) -> str | None:
        if value is None:
            return None
        return str(getattr(value, "value", value))

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(value)
