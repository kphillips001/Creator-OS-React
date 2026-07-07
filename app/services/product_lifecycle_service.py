"""Product Lifecycle orchestration read service.

ProductLifecycleService determines lifecycle stage and next recommended action
from existing Creator OS read models. It does not create Products, approve
Products, publish Products, or execute Telegram behavior.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_workflow import CreatorWorkflowSnapshot, CreatorWorkflowStage
from app.models.product_lifecycle import (
    ProductLifecycle,
    ProductLifecycleAction,
    ProductLifecycleRecommendation,
    ProductLifecycleStage,
)

if TYPE_CHECKING:
    from app.services.creator_workflow_service import CreatorWorkflowService


class ProductLifecycleService:
    """Derive Product lifecycle status without mutating domain state."""

    def __init__(
        self,
        *,
        creator_workflow_service: "CreatorWorkflowService | None" = None,
    ):
        self._creator_workflow = creator_workflow_service

    @property
    def creator_workflow(self) -> "CreatorWorkflowService":
        if self._creator_workflow is None:
            from app.services.creator_workflow_service import CreatorWorkflowService

            self._creator_workflow = CreatorWorkflowService()
        return self._creator_workflow

    def build_lifecycle(
        self,
        snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
        **workflow_context: Any,
    ) -> ProductLifecycle:
        resolved_snapshot = self._resolve_snapshot(snapshot, workflow_context)
        stage = self.determine_stage(resolved_snapshot)
        recommendation = self.recommend_next_action(
            stage,
            snapshot=resolved_snapshot,
        )
        return ProductLifecycle(
            product_id=resolved_snapshot.product_id,
            stage=stage,
            recommendation=recommendation,
            workflow_snapshot=resolved_snapshot,
            approval_status=resolved_snapshot.approval_status,
            product_status=resolved_snapshot.product_status,
            publishing_status=resolved_snapshot.publishing_status,
            media_link_status=resolved_snapshot.media_link_status,
            telegram_ready=resolved_snapshot.telegram_ready,
            compatibility={
                "source": "product_lifecycle",
                "owner": "ProductLifecycleService",
                "read_only": True,
                "orchestration_only": True,
                "provider_neutral": True,
                "does_not_create_products": True,
                "does_not_publish": True,
                "does_not_execute_telegram": True,
            },
        )

    def build_from_workflow_snapshot(
        self,
        snapshot: CreatorWorkflowSnapshot | Mapping[str, Any],
    ) -> ProductLifecycle:
        return self.build_lifecycle(snapshot)

    def determine_stage(
        self,
        snapshot: CreatorWorkflowSnapshot | Mapping[str, Any],
    ) -> ProductLifecycleStage:
        data = self._snapshot_data(snapshot)
        if self._bool(data.get("telegram_ready")):
            return ProductLifecycleStage.TELEGRAM_READY
        if self._stage_complete(data, CreatorWorkflowStage.TELEGRAM_READY):
            return ProductLifecycleStage.TELEGRAM_READY
        if self._text(data.get("product_status")) == "ACTIVE":
            return ProductLifecycleStage.ACTIVE
        if self._stage_complete(data, CreatorWorkflowStage.ACTIVE):
            return ProductLifecycleStage.ACTIVE

        publishing_status = self._text(data.get("publishing_status"))
        media_link_status = self._text(data.get("media_link_status"))
        if publishing_status == "WAITING_FOR_MEDIA_LINK" or media_link_status in {
            "REQUIRED",
            "PENDING",
            "WAITING_FOR_MEDIA_LINK",
        }:
            return ProductLifecycleStage.WAITING_FOR_MEDIA_LINK
        if publishing_status in {
            "QUEUED",
            "UPLOADING",
            "UPLOADED",
            "MEDIA_LINK_VERIFIED",
            "PUBLISHING_COMPLETE",
            "RETRY_REQUIRED",
        }:
            return ProductLifecycleStage.PUBLISHING

        approval_status = self._text(data.get("approval_status"))
        if approval_status == "READY_TO_PUBLISH":
            return ProductLifecycleStage.PUBLISHING_READY
        if approval_status == "APPROVED":
            return ProductLifecycleStage.APPROVED

        if self._stage_complete(data, CreatorWorkflowStage.IN_CREATOR_REVIEW):
            return ProductLifecycleStage.REVIEW_READY
        if (
            self._stage_complete(data, CreatorWorkflowStage.PRODUCT_STRATEGY_READY)
            and self._stage_complete(data, CreatorWorkflowStage.COMMERCE_STRATEGY_READY)
        ):
            return ProductLifecycleStage.STRATEGY_READY
        return ProductLifecycleStage.DRAFT

    def recommend_next_action(
        self,
        stage: ProductLifecycleStage,
        *,
        snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
    ) -> ProductLifecycleRecommendation:
        mapping = {
            ProductLifecycleStage.DRAFT: (
                ProductLifecycleAction.COMPLETE_STRATEGY,
                ProductLifecycleStage.STRATEGY_READY,
                "Product still needs strategy and review context.",
            ),
            ProductLifecycleStage.STRATEGY_READY: (
                ProductLifecycleAction.READY_FOR_REVIEW,
                ProductLifecycleStage.REVIEW_READY,
                "Product Strategy and Commerce Strategy are available.",
            ),
            ProductLifecycleStage.REVIEW_READY: (
                ProductLifecycleAction.APPROVE_PRODUCT,
                ProductLifecycleStage.APPROVED,
                "Creator review is ready for approval.",
            ),
            ProductLifecycleStage.APPROVED: (
                ProductLifecycleAction.PUBLISH_PRODUCT,
                ProductLifecycleStage.PUBLISHING_READY,
                "Product is approved and should enter Publishing.",
            ),
            ProductLifecycleStage.PUBLISHING_READY: (
                ProductLifecycleAction.PUBLISH_PRODUCT,
                ProductLifecycleStage.PUBLISHING,
                "Product is ready for provider publishing.",
            ),
            ProductLifecycleStage.PUBLISHING: (
                ProductLifecycleAction.WAIT_FOR_PUBLISHING,
                ProductLifecycleStage.WAITING_FOR_MEDIA_LINK,
                "Publishing is in progress or awaiting provider completion.",
            ),
            ProductLifecycleStage.WAITING_FOR_MEDIA_LINK: (
                ProductLifecycleAction.PASTE_MEDIA_LINK,
                ProductLifecycleStage.ACTIVE,
                "Publishing requires media link verification.",
            ),
            ProductLifecycleStage.ACTIVE: (
                ProductLifecycleAction.READY_FOR_TELEGRAM,
                ProductLifecycleStage.TELEGRAM_READY,
                "Product is active and can be checked for Telegram readiness.",
            ),
            ProductLifecycleStage.TELEGRAM_READY: (
                ProductLifecycleAction.NO_ACTION_REQUIRED,
                None,
                "Product is ready for Telegram commerce.",
            ),
        }
        action, target, reason = mapping[stage]
        return ProductLifecycleRecommendation(
            action=action,
            label=action.value,
            reason=reason,
            target_stage=target,
        )

    def _resolve_snapshot(
        self,
        snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
        workflow_context: Mapping[str, Any],
    ) -> CreatorWorkflowSnapshot:
        if isinstance(snapshot, CreatorWorkflowSnapshot):
            return snapshot
        if isinstance(snapshot, Mapping):
            return self._snapshot_from_mapping(snapshot)
        if workflow_context:
            return self.creator_workflow.build_snapshot(**workflow_context)
        return self.creator_workflow.build_snapshot()

    @staticmethod
    def _snapshot_from_mapping(snapshot: Mapping[str, Any]) -> CreatorWorkflowSnapshot:
        from app.models.creator_workflow import CreatorWorkflowStageStatus

        current_stage = snapshot.get("current_stage") or CreatorWorkflowStage.IMPORTED
        if not isinstance(current_stage, CreatorWorkflowStage):
            current_stage = CreatorWorkflowStage(str(current_stage))
        raw_stages = tuple(snapshot.get("stages") or ())
        stages = []
        for item in raw_stages:
            if isinstance(item, CreatorWorkflowStageStatus):
                stages.append(item)
                continue
            if not isinstance(item, Mapping):
                continue
            stage = item.get("stage")
            stages.append(
                CreatorWorkflowStageStatus(
                    stage=(
                        stage
                        if isinstance(stage, CreatorWorkflowStage)
                        else CreatorWorkflowStage(str(stage))
                    ),
                    status=str(item.get("status") or "pending"),
                    summary=item.get("summary"),
                    source=item.get("source"),
                    compatibility=item.get("compatibility") or {},
                )
            )
        return CreatorWorkflowSnapshot(
            workflow_id=snapshot.get("workflow_id"),
            current_stage=current_stage,
            stages=tuple(stages),
            creator_intent=snapshot.get("creator_intent"),
            asset_ids=tuple(snapshot.get("asset_ids") or ()),
            product_id=ProductLifecycleService._safe_text(snapshot.get("product_id")),
            experience_id=ProductLifecycleService._safe_text(snapshot.get("experience_id")),
            content_type=ProductLifecycleService._safe_text(snapshot.get("content_type")),
            product_status=ProductLifecycleService._safe_text(snapshot.get("product_status")),
            approval_status=ProductLifecycleService._safe_text(snapshot.get("approval_status")),
            publishing_status=ProductLifecycleService._safe_text(
                snapshot.get("publishing_status")
            ),
            media_link_status=ProductLifecycleService._safe_text(
                snapshot.get("media_link_status")
            ),
            telegram_ready=ProductLifecycleService._bool(snapshot.get("telegram_ready")),
            metadata=snapshot.get("metadata") or {},
        )

    @staticmethod
    def _snapshot_data(snapshot: CreatorWorkflowSnapshot | Mapping[str, Any]) -> dict[str, Any]:
        if isinstance(snapshot, CreatorWorkflowSnapshot):
            return {
                "product_status": snapshot.product_status,
                "approval_status": snapshot.approval_status,
                "publishing_status": snapshot.publishing_status,
                "media_link_status": snapshot.media_link_status,
                "telegram_ready": snapshot.telegram_ready,
                "stages": snapshot.stages,
            }
        return dict(snapshot)

    @staticmethod
    def _stage_complete(
        data: Mapping[str, Any],
        stage: CreatorWorkflowStage,
    ) -> bool:
        stages = tuple(data.get("stages") or ())
        for item in stages:
            item_stage = ProductLifecycleService._read(item, "stage")
            if not isinstance(item_stage, CreatorWorkflowStage):
                try:
                    item_stage = CreatorWorkflowStage(str(item_stage))
                except ValueError:
                    continue
            if item_stage == stage:
                return ProductLifecycleService._read(item, "status") == "complete"
        return False

    @staticmethod
    def _read(value: Any, key: str) -> Any:
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
