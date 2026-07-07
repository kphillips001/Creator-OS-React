"""Presentation models for Product Review workflows."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any, Mapping


@dataclass(frozen=True)
class ProductReviewSection:
    title: str
    status: str = "available"
    summary: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)
    evidence: tuple[Mapping[str, Any], ...] = ()
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductReview:
    """Read-only, creator-facing review model for a Product Draft."""

    product_id: str
    creator_profile_id: int | None
    product_name: str
    description: str | None
    product_type: str
    delivery_type: str
    product_origin: str
    product_status: str
    approval_status: str
    approved_at: str | None
    last_reviewed_at: str | None
    review_notes: str | None
    price_cents: int | None
    currency: str
    review_status: str
    priority: str
    product: ProductReviewSection
    experience: ProductReviewSection
    commerce: ProductReviewSection
    commerce_overrides: ProductReviewSection
    publishing: ProductReviewSection
    ai_rationale: ProductReviewSection
    warnings: tuple[str, ...] = ()
    manual_overrides: Mapping[str, Any] = field(default_factory=dict)

    def with_manual_overrides(
        self,
        overrides: Mapping[str, Any] | None,
    ) -> "ProductReview":
        """Return a review copy with UI-only override proposals attached."""

        return replace(self, manual_overrides=dict(overrides or {}))


@dataclass(frozen=True)
class ProductReviewSummary:
    total_reviews: int
    needs_review: int
    approved: int
    rejected: int
    ready_to_publish: int
    manual_products: int
    ai_product_drafts: int
    products_with_commerce_overrides: int
    draft_reviews: int
    publishing_reviews: int
    high_priority_reviews: int
    ready_for_approval: int
    reviews: tuple[ProductReview, ...] = ()
