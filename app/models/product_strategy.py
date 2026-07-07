"""Provider-neutral Product Strategy recommendation models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


@dataclass(frozen=True)
class ProductStrategyEvidence:
    reason: str
    detail: str | None = None
    weight: int = 0


@dataclass(frozen=True)
class ProductCompositionRecommendation:
    composition_type: str
    included_asset_ids: tuple[int, ...] = ()
    asset_order: tuple[int, ...] = ()
    cover_asset_id: int | None = None
    experience_id: str | None = None
    relationship_type: str | None = None
    related_recommendation_types: tuple[str, ...] = ()
    rationale: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProductStrategyRecommendation:
    recommendation_type: str
    source_type: str
    source_id: str | None
    asset_ids: tuple[int, ...] = ()
    composition: ProductCompositionRecommendation | None = None
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[ProductStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductCatalogRecommendation:
    associated_experience_id: str | None
    associated_experience_type: str | None = None
    recommended_products: tuple[ProductStrategyRecommendation, ...] = ()
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[ProductStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductStrategyResult:
    source_type: str
    source_id: str | None
    recommendations: tuple[ProductStrategyRecommendation, ...] = ()
    catalog_recommendation: ProductCatalogRecommendation | None = None
    confidence: float = 0.0
    rationale: tuple[str, ...] = ()
    evidence: tuple[ProductStrategyEvidence, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)
