"""Presentation models for Creator Review of AI import workflow results."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class CreatorReviewSection:
    title: str
    status: str = "available"
    summary: str | None = None
    confidence: float | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class CreatorReview:
    """Read-only, UI-ready view of completed AI import workflow results."""

    review_type: str
    asset_ids: tuple[int, ...]
    asset: CreatorReviewSection
    asset_understanding: CreatorReviewSection
    content_intelligence: CreatorReviewSection
    experience: CreatorReviewSection
    experience_recommendation: CreatorReviewSection
    product_strategy: CreatorReviewSection
    commerce_strategy: CreatorReviewSection
    commerce_recommendation: CreatorReviewSection
    product_draft: CreatorReviewSection
    delivery_type: CreatorReviewSection
    publishing_readiness: CreatorReviewSection
    organization: CreatorReviewSection
    warnings: tuple[str, ...] = ()
    manual_overrides: Mapping[str, Any] = field(default_factory=dict)

    def with_manual_overrides(
        self,
        overrides: Mapping[str, Any] | None,
    ) -> "CreatorReview":
        """Return a review copy with UI-only override proposals attached."""

        return replace(self, manual_overrides=dict(overrides or {}))


@dataclass(frozen=True)
class CreatorReviewDashboardItem:
    review_type: str
    title: str
    detail: str
    status: str
    priority: str
    target: str | None = None
    confidence: float | None = None
    evidence_available: bool = False
    override_proposals: tuple[str, ...] = ()
    completeness: str = "Unavailable"


@dataclass(frozen=True)
class CreatorReviewDashboardSummary:
    total_pending: int
    assets_awaiting_review: int
    experiences_awaiting_review: int
    products_awaiting_review: int
    high_priority_reviews: int
    publishing_reviews_remaining: int
    completed_reviews: int | None
    review_completion_percentage: float | None
    items: tuple[CreatorReviewDashboardItem, ...] = ()
