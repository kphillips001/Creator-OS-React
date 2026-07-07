"""Provider-neutral Creator Review optimization read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.product_lifecycle import ProductLifecycle


class CreatorReviewState(str, Enum):
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
    REVIEW_RECOMMENDED = "REVIEW_RECOMMENDED"
    READY_FOR_APPROVAL = "READY_FOR_APPROVAL"
    AUTO_PROGRESS_ELIGIBLE = "AUTO_PROGRESS_ELIGIBLE"


class CreatorReviewAction(str, Enum):
    REVIEW_PRODUCT = "Review Product"
    APPROVE_PRODUCT = "Approve Product"
    OPTIONAL_REVIEW = "Optional Review"
    CONTINUE_AUTOMATICALLY = "Continue Automatically"


@dataclass(frozen=True)
class CreatorReviewRecommendation:
    action: CreatorReviewAction
    label: str
    reason: str | None = None
    source: str = "CreatorReviewOptimizationService"


@dataclass(frozen=True)
class CreatorReviewStatus:
    """Read-only determination of whether creator review is needed."""

    state: CreatorReviewState
    recommendation: CreatorReviewRecommendation
    lifecycle: ProductLifecycle | None = None
    confidence: float | None = None
    review_required: bool = False
    auto_progress_eligible: bool = False
    reasons: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_creator_action(self) -> str:
        return self.recommendation.label
