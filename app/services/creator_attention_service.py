"""Creator Attention Engine.

CreatorAttentionService aggregates existing Creator Workflow, Product
Lifecycle, Creator Review Optimization, and Publishing Automation read models.
It does not approve Products, publish Products, execute Telegram, or mutate
workflow state.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_attention import (
    CreatorAttentionCategory,
    CreatorAttentionItem,
    CreatorAttentionPriority,
    CreatorAttentionSummary,
)
from app.models.creator_review_optimization import (
    CreatorReviewState,
    CreatorReviewStatus,
)
from app.models.creator_workflow import CreatorWorkflowSnapshot
from app.models.product_lifecycle import ProductLifecycle, ProductLifecycleStage
from app.models.publishing_automation import (
    PublishingAutomationState,
    PublishingAutomationStatus,
)

if TYPE_CHECKING:
    from app.models.chat_commerce_registration import ChatCommerceAssetRecord
    from app.services.creator_review_optimization_service import (
        CreatorReviewOptimizationService,
    )
    from app.services.product_lifecycle_service import ProductLifecycleService
    from app.services.publishing_automation_service import PublishingAutomationService


class CreatorAttentionService:
    """Derive creator interruptions from existing read-only workflow outputs."""

    PRIORITY_ORDER = {
        CreatorAttentionPriority.CRITICAL: 0,
        CreatorAttentionPriority.HIGH: 1,
        CreatorAttentionPriority.NORMAL: 2,
        CreatorAttentionPriority.LOW: 3,
    }

    def __init__(
        self,
        *,
        product_lifecycle_service: "ProductLifecycleService | None" = None,
        review_optimization_service: "CreatorReviewOptimizationService | None" = None,
        publishing_automation_service: "PublishingAutomationService | None" = None,
        confidence_threshold: float = 0.75,
    ):
        self._product_lifecycle = product_lifecycle_service
        self._review_optimization = review_optimization_service
        self._publishing_automation = publishing_automation_service
        self.confidence_threshold = float(confidence_threshold)

    @property
    def product_lifecycle(self) -> "ProductLifecycleService":
        if self._product_lifecycle is None:
            from app.services.product_lifecycle_service import ProductLifecycleService

            self._product_lifecycle = ProductLifecycleService()
        return self._product_lifecycle

    @property
    def review_optimization(self) -> "CreatorReviewOptimizationService":
        if self._review_optimization is None:
            from app.services.creator_review_optimization_service import (
                CreatorReviewOptimizationService,
            )

            self._review_optimization = CreatorReviewOptimizationService(
                minimum_auto_confidence=self.confidence_threshold
            )
        return self._review_optimization

    @property
    def publishing_automation(self) -> "PublishingAutomationService":
        if self._publishing_automation is None:
            from app.services.publishing_automation_service import (
                PublishingAutomationService,
            )

            self._publishing_automation = PublishingAutomationService()
        return self._publishing_automation

    def build_attention_summary(
        self,
        *,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        review_status: CreatorReviewStatus | Mapping[str, Any] | None = None,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        chat_registration_records: tuple["ChatCommerceAssetRecord", ...] = (),
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorAttentionSummary:
        items = self.build_attention_items(
            workflow_snapshot=workflow_snapshot,
            lifecycle=lifecycle,
            review_status=review_status,
            publishing_status=publishing_status,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
            chat_registration_records=chat_registration_records,
        )
        ordered = self.prioritize_items(items)
        attention_required = any(item.attention_required for item in ordered)
        top = ordered[0]
        return CreatorAttentionSummary(
            items=ordered,
            attention_required=attention_required,
            highest_priority=top.priority,
            recommended_action=top.recommended_action,
            compatibility={
                "source": "creator_attention",
                "owner": "CreatorAttentionService",
                "read_only": True,
                "recommendation_only": True,
                "provider_neutral": True,
                "does_not_approve_products": True,
                "does_not_publish": True,
                "does_not_execute_telegram": True,
                "does_not_modify_workflow_state": True,
                **dict(metadata or {}),
            },
        )

    def build_attention_items(
        self,
        *,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        review_status: CreatorReviewStatus | Mapping[str, Any] | None = None,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None = None,
        publishing_projection: Any | None = None,
        publishing_job: Any | None = None,
        publishing_queue_item: Any | None = None,
        chat_registration_records: tuple["ChatCommerceAssetRecord", ...] = (),
    ) -> tuple[CreatorAttentionItem, ...]:
        resolved_lifecycle = self._resolve_lifecycle(lifecycle, workflow_snapshot)
        resolved_review = self._resolve_review_status(
            review_status,
            workflow_snapshot=workflow_snapshot,
            lifecycle=resolved_lifecycle,
        )
        resolved_publishing = self._resolve_publishing_status(
            publishing_status,
            workflow_snapshot=workflow_snapshot,
            lifecycle=resolved_lifecycle,
            publishing_projection=publishing_projection,
            publishing_job=publishing_job,
            publishing_queue_item=publishing_queue_item,
        )

        items: list[CreatorAttentionItem] = []
        self._add_workflow_items(items, workflow_snapshot)
        self._add_review_items(items, resolved_review)
        self._add_lifecycle_items(items, resolved_lifecycle, resolved_review)
        self._add_publishing_items(items, resolved_publishing)
        self._add_chat_registration_items(items, chat_registration_records)

        deduped = self._dedupe_items(items)
        if not any(item.attention_required for item in deduped):
            return (self._no_action_item(workflow_snapshot, resolved_lifecycle),)
        return deduped

    def prioritize_items(
        self,
        items: tuple[CreatorAttentionItem, ...],
    ) -> tuple[CreatorAttentionItem, ...]:
        return tuple(
            sorted(
                items,
                key=lambda item: (
                    self.PRIORITY_ORDER[item.priority],
                    0 if item.attention_required else 1,
                    item.category.value,
                    item.recommended_action,
                ),
            )
        )

    @staticmethod
    def _dedupe_items(
        items: list[CreatorAttentionItem],
    ) -> tuple[CreatorAttentionItem, ...]:
        seen: set[tuple[str, str, str, str | None]] = set()
        deduped: list[CreatorAttentionItem] = []
        for item in items:
            key = (
                item.category.value,
                item.priority.value,
                item.recommended_action,
                item.product_id,
            )
            if key in seen:
                continue
            seen.add(key)
            deduped.append(item)
        return tuple(deduped)

    def _resolve_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
    ) -> ProductLifecycle | None:
        if isinstance(lifecycle, ProductLifecycle):
            return lifecycle
        if lifecycle is not None:
            return self.product_lifecycle.build_lifecycle(lifecycle)
        if workflow_snapshot is not None:
            try:
                return self.product_lifecycle.build_lifecycle(workflow_snapshot)
            except Exception:
                return None
        return None

    def _resolve_review_status(
        self,
        review_status: CreatorReviewStatus | Mapping[str, Any] | None,
        *,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
        lifecycle: ProductLifecycle | None,
    ) -> CreatorReviewStatus | None:
        if isinstance(review_status, CreatorReviewStatus):
            return review_status
        if review_status is not None:
            return self._review_from_mapping(review_status)
        try:
            return self.review_optimization.build_review_status(
                workflow_snapshot=workflow_snapshot,
                lifecycle=lifecycle,
            )
        except Exception:
            return None

    def _resolve_publishing_status(
        self,
        publishing_status: PublishingAutomationStatus | Mapping[str, Any] | None,
        *,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
        lifecycle: ProductLifecycle | None,
        publishing_projection: Any | None,
        publishing_job: Any | None,
        publishing_queue_item: Any | None,
    ) -> PublishingAutomationStatus | None:
        if isinstance(publishing_status, PublishingAutomationStatus):
            return publishing_status
        if publishing_status is not None:
            return self._publishing_from_mapping(publishing_status)
        if (
            lifecycle is None
            and workflow_snapshot is None
            and publishing_projection is None
            and publishing_job is None
            and publishing_queue_item is None
        ):
            return None
        try:
            return self.publishing_automation.build_status(
                lifecycle=lifecycle,
                workflow_snapshot=workflow_snapshot,
                publishing_projection=publishing_projection,
                publishing_job=publishing_job,
                publishing_queue_item=publishing_queue_item,
            )
        except Exception:
            return None

    def _add_workflow_items(
        self,
        items: list[CreatorAttentionItem],
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
    ) -> None:
        if workflow_snapshot is None:
            return
        content_type = self._read(workflow_snapshot, "content_type")
        creator_intent = self._read(workflow_snapshot, "creator_intent")
        product_id = self._read(workflow_snapshot, "product_id")
        if not content_type and creator_intent is None and not product_id:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.REVIEW,
                    priority=CreatorAttentionPriority.HIGH,
                    recommended_action="Select Content Type",
                    reason="Creator-selected Content Type is required before workflow progression.",
                    workflow_snapshot=workflow_snapshot,
                    title="Content Type selection required",
                    evidence={"missing": "content_type"},
                )
            )

    def _add_review_items(
        self,
        items: list[CreatorAttentionItem],
        review_status: CreatorReviewStatus | None,
    ) -> None:
        if review_status is None:
            return
        if review_status.state == CreatorReviewState.REVIEW_REQUIRED:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.REVIEW,
                    priority=CreatorAttentionPriority.HIGH,
                    recommended_action="Review Product",
                    reason=review_status.recommendation.reason
                    or "Creator judgment is required before progression.",
                    lifecycle=review_status.lifecycle,
                    title="Product review required",
                    evidence={
                        "state": review_status.state.value,
                        "warnings": review_status.warnings,
                    },
                )
            )
            return
        if review_status.state == CreatorReviewState.READY_FOR_APPROVAL:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.APPROVAL,
                    priority=CreatorAttentionPriority.NORMAL,
                    recommended_action="Approve Product",
                    reason=review_status.recommendation.reason
                    or "Review output is ready for creator approval.",
                    lifecycle=review_status.lifecycle,
                    title="Product approval required",
                    evidence={"state": review_status.state.value},
                )
            )
            return
        if review_status.state == CreatorReviewState.REVIEW_RECOMMENDED:
            priority = CreatorAttentionPriority.LOW
            action = "Optional Review"
            if (
                review_status.confidence is not None
                and review_status.confidence < self.confidence_threshold
            ):
                priority = CreatorAttentionPriority.NORMAL
                action = "Review Product"
            items.append(
                self._item(
                    category=CreatorAttentionCategory.REVIEW,
                    priority=priority,
                    recommended_action=action,
                    reason=review_status.recommendation.reason
                    or "Creator review is useful but not mandatory.",
                    attention_required=priority != CreatorAttentionPriority.LOW,
                    lifecycle=review_status.lifecycle,
                    title="Product review recommended",
                    evidence={
                        "state": review_status.state.value,
                        "confidence": review_status.confidence,
                    },
                )
            )

    def _add_lifecycle_items(
        self,
        items: list[CreatorAttentionItem],
        lifecycle: ProductLifecycle | None,
        review_status: CreatorReviewStatus | None,
    ) -> None:
        if lifecycle is None:
            return
        if lifecycle.stage == ProductLifecycleStage.REVIEW_READY and not self._has_category(
            items,
            CreatorAttentionCategory.APPROVAL,
        ):
            items.append(
                self._item(
                    category=CreatorAttentionCategory.APPROVAL,
                    priority=CreatorAttentionPriority.NORMAL,
                    recommended_action="Approve Product",
                    reason="Creator review is complete and Product approval is the next lifecycle action.",
                    lifecycle=lifecycle,
                    title="Product approval required",
                    evidence={"stage": lifecycle.stage.value},
                )
            )
        if (
            lifecycle.stage == ProductLifecycleStage.STRATEGY_READY
            and review_status is None
        ):
            items.append(
                self._item(
                    category=CreatorAttentionCategory.REVIEW,
                    priority=CreatorAttentionPriority.NORMAL,
                    recommended_action="Review Product",
                    reason="Product and Commerce Strategy are ready for creator review.",
                    lifecycle=lifecycle,
                    title="Product review required",
                    evidence={"stage": lifecycle.stage.value},
                )
            )

    def _add_publishing_items(
        self,
        items: list[CreatorAttentionItem],
        publishing_status: PublishingAutomationStatus | None,
    ) -> None:
        if publishing_status is None:
            return
        if publishing_status.state == PublishingAutomationState.NEEDS_ATTENTION:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.FAILURE,
                    priority=CreatorAttentionPriority.CRITICAL,
                    recommended_action="Resolve Publishing Failure",
                    reason=publishing_status.recommendation.reason
                    or "Publishing requires creator or operator attention.",
                    lifecycle=publishing_status.lifecycle,
                    title="Publishing failure requires attention",
                    evidence=publishing_status.evidence,
                )
            )
        elif publishing_status.state == PublishingAutomationState.WAITING_FOR_MEDIA_LINK:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.MEDIA_LINK,
                    priority=CreatorAttentionPriority.HIGH,
                    recommended_action="Paste Media Link",
                    reason="Creator must manually create and paste the provider Media Link.",
                    lifecycle=publishing_status.lifecycle,
                    title="Media Link required",
                    evidence=publishing_status.evidence,
                )
            )
        elif publishing_status.state == PublishingAutomationState.VERIFY_MEDIA_LINK:
            items.append(
                self._item(
                    category=CreatorAttentionCategory.MEDIA_LINK,
                    priority=CreatorAttentionPriority.NORMAL,
                    recommended_action="Verify Media Link",
                    reason="Media Link is available and should be verified through Publishing.",
                    lifecycle=publishing_status.lifecycle,
                    title="Publishing verification required",
                    evidence=publishing_status.evidence,
                )
            )

    def _add_chat_registration_items(
        self,
        items: list[CreatorAttentionItem],
        chat_registration_records: tuple["ChatCommerceAssetRecord", ...],
    ) -> None:
        if not chat_registration_records:
            return
        from app.models.chat_commerce_registration import ChatAvailabilityState

        for record in chat_registration_records:
            if record.availability_state == ChatAvailabilityState.CHAT_READY:
                continue
            if record.availability_state == ChatAvailabilityState.RETIRED:
                priority = CreatorAttentionPriority.NORMAL
                action = "Review Retired Chat Asset"
                title = "Chat Commerce asset retired"
            elif record.temporarily_unavailable:
                priority = CreatorAttentionPriority.HIGH
                action = "Review Chat Availability"
                title = "Chat Commerce asset unavailable"
            else:
                priority = CreatorAttentionPriority.HIGH
                action = "Resolve Chat Registration"
                title = "Chat Commerce registration blocked"
            reason = record.error_message or (
                ", ".join(record.block_reasons)
                if record.block_reasons
                else "Chat Commerce registration is not eligible for runtime inventory."
            )
            items.append(
                CreatorAttentionItem(
                    category=CreatorAttentionCategory.FAILURE,
                    priority=priority,
                    recommended_action=action,
                    reason=reason,
                    title=title,
                    product_id=(
                        str(record.product_ids[0]) if record.product_ids else None
                    ),
                    workflow_id=record.source_workflow,
                    source="ChatCommerceRegistrationService",
                    evidence={
                        "asset_id": record.asset_id,
                        "chat_registration_id": str(record.chat_registration_id),
                        "availability_state": record.availability_state.value,
                        "commerce_destination": record.commerce_destination,
                        "fulfillment_ready": record.fulfillment_ready,
                        "block_reasons": list(record.block_reasons),
                    },
                    compatibility={
                        "read_only": True,
                        "recommendation_only": True,
                        "provider_neutral": True,
                        "does_not_mutate_state": True,
                        "source": "chat_commerce_registration",
                    },
                )
            )

    def _no_action_item(
        self,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None,
        lifecycle: ProductLifecycle | None,
    ) -> CreatorAttentionItem:
        return self._item(
            category=CreatorAttentionCategory.INFORMATION,
            priority=CreatorAttentionPriority.LOW,
            recommended_action="No Action Required",
            reason="Current workflow projections do not require creator interruption.",
            attention_required=False,
            workflow_snapshot=workflow_snapshot,
            lifecycle=lifecycle,
            title="No creator action required",
        )

    def _item(
        self,
        *,
        category: CreatorAttentionCategory,
        priority: CreatorAttentionPriority,
        recommended_action: str,
        reason: str,
        attention_required: bool = True,
        workflow_snapshot: CreatorWorkflowSnapshot | Mapping[str, Any] | None = None,
        lifecycle: ProductLifecycle | None = None,
        title: str | None = None,
        evidence: Mapping[str, Any] | None = None,
    ) -> CreatorAttentionItem:
        snapshot = workflow_snapshot or self._read(lifecycle, "workflow_snapshot")
        return CreatorAttentionItem(
            category=category,
            priority=priority,
            recommended_action=recommended_action,
            reason=reason,
            attention_required=attention_required,
            title=title,
            product_id=self._safe_text(
                self._read(lifecycle, "product_id") or self._read(snapshot, "product_id")
            ),
            workflow_id=self._safe_text(self._read(snapshot, "workflow_id")),
            evidence=evidence or {},
            compatibility={
                "read_only": True,
                "recommendation_only": True,
                "provider_neutral": True,
                "does_not_mutate_state": True,
            },
        )

    @staticmethod
    def _has_category(
        items: list[CreatorAttentionItem],
        category: CreatorAttentionCategory,
    ) -> bool:
        return any(item.category == category for item in items)

    @staticmethod
    def _review_from_mapping(value: Mapping[str, Any]) -> CreatorReviewStatus:
        from app.models.creator_review_optimization import (
            CreatorReviewAction,
            CreatorReviewRecommendation,
        )

        state = value.get("state")
        if not isinstance(state, CreatorReviewState):
            state = CreatorReviewState(str(state))
        recommendation = value.get("recommendation")
        if not isinstance(recommendation, CreatorReviewRecommendation):
            action = value.get("action") or (
                "Review Product"
                if state == CreatorReviewState.REVIEW_REQUIRED
                else "Continue Automatically"
            )
            if not isinstance(action, CreatorReviewAction):
                action = CreatorReviewAction(str(action))
            recommendation = CreatorReviewRecommendation(
                action=action,
                label=str(value.get("label") or action.value),
                reason=value.get("reason"),
            )
        return CreatorReviewStatus(
            state=state,
            recommendation=recommendation,
            lifecycle=value.get("lifecycle"),
            confidence=value.get("confidence"),
            review_required=bool(value.get("review_required")),
            auto_progress_eligible=bool(value.get("auto_progress_eligible")),
            reasons=tuple(value.get("reasons") or ()),
            warnings=tuple(value.get("warnings") or ()),
            metadata=value.get("metadata") or {},
        )

    @staticmethod
    def _publishing_from_mapping(value: Mapping[str, Any]) -> PublishingAutomationStatus:
        from app.models.publishing_automation import (
            PublishingAutomationAction,
            PublishingAutomationRecommendation,
        )

        state = value.get("state")
        if not isinstance(state, PublishingAutomationState):
            state = PublishingAutomationState(str(state))
        recommendation = value.get("recommendation")
        if not isinstance(recommendation, PublishingAutomationRecommendation):
            action = value.get("action") or (
                "Review Publishing Failure"
                if state == PublishingAutomationState.NEEDS_ATTENTION
                else "No Publishing Action"
            )
            if not isinstance(action, PublishingAutomationAction):
                action = PublishingAutomationAction(str(action))
            recommendation = PublishingAutomationRecommendation(
                action=action,
                label=str(value.get("label") or action.value),
                reason=value.get("reason"),
            )
        return PublishingAutomationStatus(
            state=state,
            recommendation=recommendation,
            product_id=value.get("product_id"),
            lifecycle=value.get("lifecycle"),
            publishing_status=value.get("publishing_status"),
            media_link_status=value.get("media_link_status"),
            provider_status=value.get("provider_status"),
            provider_error=value.get("provider_error"),
            manual_media_link_required=bool(value.get("manual_media_link_required")),
            attention_required=bool(value.get("attention_required")),
            telegram_ready=bool(value.get("telegram_ready")),
            evidence=value.get("evidence") or {},
            compatibility=value.get("compatibility") or {},
        )

    @staticmethod
    def _read(value: Any, key: str) -> Any:
        if value is None:
            return None
        if isinstance(value, Mapping):
            return value.get(key)
        return getattr(value, key, None)

    @staticmethod
    def _safe_text(value: Any) -> str | None:
        if value in (None, ""):
            return None
        return str(getattr(value, "value", value))
