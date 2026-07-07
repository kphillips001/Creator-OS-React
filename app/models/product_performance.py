"""Provider-neutral Product Performance read models.

Product Performance aggregates Business Learning evidence into Product-level
guidance. Business Learning remains the owner of historical outcomes and
performance evidence.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.business_learning import PerformanceMetric
from app.models.product_business import ProductBusinessSnapshot


class ProductPerformanceStatus(str, Enum):
    STRONG_PERFORMER = "STRONG_PERFORMER"
    AVERAGE_PERFORMER = "AVERAGE_PERFORMER"
    UNDERPERFORMING = "UNDERPERFORMING"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    MONITOR = "MONITOR"
    NO_DATA = "NO_DATA"


@dataclass(frozen=True)
class ProductPerformanceRecommendation:
    label: str
    reason: str | None = None
    source: str = "ProductPerformanceService"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductPerformanceSummary:
    sales_performance: Mapping[str, Any] = field(default_factory=dict)
    free_conversion_performance: Mapping[str, Any] = field(default_factory=dict)
    bundle_performance: Mapping[str, Any] = field(default_factory=dict)
    story_performance: Mapping[str, Any] = field(default_factory=dict)
    photoshoot_performance: Mapping[str, Any] = field(default_factory=dict)
    customer_engagement: Mapping[str, Any] = field(default_factory=dict)
    conversion_rate: float = 0.0
    customer_reach: Mapping[str, Any] = field(default_factory=dict)
    trend: str = "unknown"
    overall_health: str = "unknown"
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ProductPerformance:
    product_id: str | None = None
    status: ProductPerformanceStatus = ProductPerformanceStatus.NO_DATA
    summary: ProductPerformanceSummary = field(default_factory=ProductPerformanceSummary)
    recommendation: ProductPerformanceRecommendation = field(
        default_factory=lambda: ProductPerformanceRecommendation(
            label="Monitor",
            reason="No Product Performance evidence was available.",
        )
    )
    product_business_snapshot: ProductBusinessSnapshot | None = None
    performance_metrics: tuple[PerformanceMetric, ...] = ()
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommended_action(self) -> str:
        return self.recommendation.label
