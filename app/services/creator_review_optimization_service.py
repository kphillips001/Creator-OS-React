"""Exception-based Creator Review optimization.

This service determines whether creator review is required from existing
workflow, lifecycle, Creator Review, and Product Review read models. It does
not approve Products, publish Products, or generate strategy.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, TYPE_CHECKING

from app.models.creator_review_optimization import (
    CreatorReviewAction,
    CreatorReviewRecommendation,
    CreatorReviewState,
    CreatorReviewStatus,
)
from app.models.product_lifecycle import ProductLifecycle, ProductLifecycleStage

if TYPE_CHECKING:
    from app.services.creator_review_service import CreatorReviewService
    from app.services.product_lifecycle_service import ProductLifecycleService
    from app.services.product_review_service import ProductReviewService


class CreatorReviewOptimizationService:
    """Classify review need without mutating Creator OS domain state."""

    def __init__(
        self,
        *,
        minimum_auto_confidence: float = 0.75,
        creator_review_service: "CreatorReviewService | None" = None,
        product_review_service: "ProductReviewService | None" = None,
        product_lifecycle_service: "ProductLifecycleService | None" = None,
    ):
        self.minimum_auto_confidence = float(minimum_auto_confidence)
        self._creator_review = creator_review_service
        self._product_review = product_review_service
        self._product_lifecycle = product_lifecycle_service

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
    def product_lifecycle(self) -> "ProductLifecycleService":
        if self._product_lifecycle is None:
            from app.services.product_lifecycle_service import ProductLifecycleService

            self._product_lifecycle = ProductLifecycleService()
        return self._product_lifecycle

    def build_review_status(
        self,
        *,
        workflow_snapshot: Any | None = None,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None = None,
        creator_review: Any | None = None,
        product_review: Any | None = None,
        workflow_result: Any | None = None,
        product_display: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CreatorReviewStatus:
        resolved_lifecycle = self._resolve_lifecycle(
            lifecycle,
            workflow_snapshot=workflow_snapshot,
        )
        resolved_creator_review = self._resolve_creator_review(
            creator_review,
            workflow_result=workflow_result,
        )
        resolved_product_review = self._resolve_product_review(
            product_review,
            product_display=product_display,
        )
        warnings = self._warnings(
            creator_review=resolved_creator_review,
            product_review=resolved_product_review,
        )
        reasons = list(warnings)
        confidence = self._confidence(
            creator_review=resolved_creator_review,
            product_review=resolved_product_review,
            lifecycle=resolved_lifecycle,
        )
        state = self._state(
            lifecycle=resolved_lifecycle,
            product_review=resolved_product_review,
            confidence=confidence,
            warnings=warnings,
            reasons=reasons,
        )
        recommendation = self._recommendation(state, reasons=tuple(reasons))
        return CreatorReviewStatus(
            state=state,
            recommendation=recommendation,
            lifecycle=resolved_lifecycle,
            confidence=confidence,
            review_required=state == CreatorReviewState.REVIEW_REQUIRED,
            auto_progress_eligible=state
            == CreatorReviewState.AUTO_PROGRESS_ELIGIBLE,
            reasons=tuple(dict.fromkeys(reasons)),
            warnings=warnings,
            metadata={
                "source": "creator_review_optimization",
                "owner": "CreatorReviewOptimizationService",
                "read_only": True,
                "orchestration_only": True,
                "provider_neutral": True,
                "does_not_approve_products": True,
                "does_not_publish": True,
                "does_not_generate_strategy": True,
                "minimum_auto_confidence": self.minimum_auto_confidence,
                **dict(metadata or {}),
            },
        )

    def build_from_workflow_snapshot(
        self,
        workflow_snapshot: Any,
        **context: Any,
    ) -> CreatorReviewStatus:
        return self.build_review_status(
            workflow_snapshot=workflow_snapshot,
            **context,
        )

    def build_from_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any],
        **context: Any,
    ) -> CreatorReviewStatus:
        return self.build_review_status(lifecycle=lifecycle, **context)

    def _resolve_lifecycle(
        self,
        lifecycle: ProductLifecycle | Mapping[str, Any] | None,
        *,
        workflow_snapshot: Any | None,
    ) -> ProductLifecycle | None:
        if isinstance(lifecycle, ProductLifecycle):
            return lifecycle
        if lifecycle is not None:
            return self.product_lifecycle.build_lifecycle(lifecycle)
        if workflow_snapshot is not None:
            return self.product_lifecycle.build_lifecycle(workflow_snapshot)
        return None

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

    def _state(
        self,
        *,
        lifecycle: ProductLifecycle | None,
        product_review: Any | None,
        confidence: float | None,
        warnings: tuple[str, ...],
        reasons: list[str],
    ) -> CreatorReviewState:
        review_status = self._text(self._read(product_review, "review_status"))
        priority = self._text(self._read(product_review, "priority"))
        commerce_overrides = self._read(product_review, "commerce_overrides")
        commerce_override_status = self._text(self._read(commerce_overrides, "status"))
        lifecycle_stage = self._read(lifecycle, "stage")

        if warnings:
            reasons.append("warnings_present")
            return CreatorReviewState.REVIEW_REQUIRED
        if priority == "high":
            reasons.append("high_priority_review")
            return CreatorReviewState.REVIEW_REQUIRED
        if review_status in {
            "Needs Attention",
            "Commerce Override Review",
            "Rejected",
            "Archived",
        }:
            reasons.append(f"review_status:{review_status}")
            return CreatorReviewState.REVIEW_REQUIRED
        if commerce_override_status == "overridden":
            reasons.append("commerce_overrides_present")
            return CreatorReviewState.REVIEW_REQUIRED

        confidence_ready = (
            confidence is not None and confidence >= self.minimum_auto_confidence
        )
        if review_status in {"Ready To Publish", "Ready for Approval", "Approved"}:
            if confidence_ready:
                reasons.append("review_ready_with_sufficient_confidence")
                return CreatorReviewState.AUTO_PROGRESS_ELIGIBLE
            reasons.append("review_ready_low_confidence")
            return CreatorReviewState.READY_FOR_APPROVAL

        if lifecycle_stage in {
            ProductLifecycleStage.STRATEGY_READY,
            ProductLifecycleStage.REVIEW_READY,
        }:
            if confidence_ready:
                reasons.append("strategy_ready_with_sufficient_confidence")
                return CreatorReviewState.AUTO_PROGRESS_ELIGIBLE
            reasons.append("strategy_ready_review_recommended")
            return CreatorReviewState.REVIEW_RECOMMENDED

        if lifecycle_stage in {
            ProductLifecycleStage.APPROVED,
            ProductLifecycleStage.PUBLISHING_READY,
            ProductLifecycleStage.PUBLISHING,
            ProductLifecycleStage.WAITING_FOR_MEDIA_LINK,
            ProductLifecycleStage.ACTIVE,
            ProductLifecycleStage.TELEGRAM_READY,
        }:
            reasons.append("already_past_review_gate")
            return CreatorReviewState.AUTO_PROGRESS_ELIGIBLE

        reasons.append("insufficient_review_evidence")
        return CreatorReviewState.REVIEW_RECOMMENDED

    @staticmethod
    def _recommendation(
        state: CreatorReviewState,
        *,
        reasons: tuple[str, ...],
    ) -> CreatorReviewRecommendation:
        if state == CreatorReviewState.REVIEW_REQUIRED:
            action = CreatorReviewAction.REVIEW_PRODUCT
            reason = "Creator judgment is required before progression."
        elif state == CreatorReviewState.READY_FOR_APPROVAL:
            action = CreatorReviewAction.APPROVE_PRODUCT
            reason = "Review output is ready for creator approval."
        elif state == CreatorReviewState.AUTO_PROGRESS_ELIGIBLE:
            action = CreatorReviewAction.CONTINUE_AUTOMATICALLY
            reason = "Existing evidence supports automatic progression."
        else:
            action = CreatorReviewAction.OPTIONAL_REVIEW
            reason = "Creator review is useful but not mandatory."
        if reasons:
            reason = f"{reason} Signals: {', '.join(reasons[:4])}."
        return CreatorReviewRecommendation(
            action=action,
            label=action.value,
            reason=reason,
        )

    def _confidence(
        self,
        *,
        creator_review: Any | None,
        product_review: Any | None,
        lifecycle: ProductLifecycle | None,
    ) -> float | None:
        values: list[float] = []
        for section_name in (
            "asset_understanding",
            "content_intelligence",
            "experience_recommendation",
            "product_strategy",
            "commerce_strategy",
            "commerce_recommendation",
        ):
            value = self._read(self._read(creator_review, section_name), "confidence")
            if value is not None:
                values.append(float(value))
        commerce = self._read(product_review, "commerce")
        commerce_data = self._read(commerce, "data") or {}
        value = self._read(commerce_data, "confidence")
        if value is not None:
            values.append(float(value))
        if lifecycle is not None and lifecycle.stage in {
            ProductLifecycleStage.APPROVED,
            ProductLifecycleStage.PUBLISHING_READY,
            ProductLifecycleStage.ACTIVE,
            ProductLifecycleStage.TELEGRAM_READY,
        }:
            values.append(0.9)
        if not values:
            return None
        return round(sum(values) / len(values), 2)

    @classmethod
    def _warnings(
        cls,
        *,
        creator_review: Any | None,
        product_review: Any | None,
    ) -> tuple[str, ...]:
        values: list[str] = []
        values.extend(str(item) for item in cls._read(creator_review, "warnings") or ())
        values.extend(str(item) for item in cls._read(product_review, "warnings") or ())
        return tuple(dict.fromkeys(item for item in values if item))

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
        return str(getattr(value, "value", value))
