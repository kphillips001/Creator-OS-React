"""Provider-neutral Product Improvement read models.

Product Improvement converts Product Business evidence into advisory
recommendations only. It never mutates Product, Publishing, Strategy, or
Learning state.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class ProductImprovementType(str, Enum):
    CREATE_FREE_PREVIEW = "CREATE_FREE_PREVIEW"
    CREATE_BUNDLE = "CREATE_BUNDLE"
    IMPROVE_FREE_PREVIEW = "IMPROVE_FREE_PREVIEW"
    IMPROVE_COMPOSITION = "IMPROVE_COMPOSITION"
    REFRESH_PRODUCT = "REFRESH_PRODUCT"
    CONSOLIDATE_DUPLICATES = "CONSOLIDATE_DUPLICATES"
    RETIRE_PRODUCT = "RETIRE_PRODUCT"
    FIX_AVAILABILITY = "FIX_AVAILABILITY"
    PROMOTE_STRONG_PERFORMER = "PROMOTE_STRONG_PERFORMER"
    MONITOR_PRODUCT = "MONITOR_PRODUCT"
    CREATE_PRODUCT = "CREATE_PRODUCT"


class ProductImprovementPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


@dataclass(frozen=True)
class ProductImprovementRecommendation:
    improvement_type: ProductImprovementType
    priority: ProductImprovementPriority
    label: str
    recommended_next_action: str
    confidence: float = 0.0
    product_id: str | None = None
    rationale: tuple[str, ...] = ()
    supporting_evidence: Mapping[str, Any] = field(default_factory=dict)
    source: str = "ProductImprovementService"


@dataclass(frozen=True)
class ProductImprovement:
    product_id: str | None = None
    recommendations: tuple[ProductImprovementRecommendation, ...] = ()
    summary: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommendation(self) -> ProductImprovementRecommendation | None:
        return self.recommendations[0] if self.recommendations else None
