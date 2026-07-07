"""Provider-neutral Product Lifecycle read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.creator_workflow import CreatorWorkflowSnapshot


class ProductLifecycleStage(str, Enum):
    DRAFT = "DRAFT"
    STRATEGY_READY = "STRATEGY_READY"
    REVIEW_READY = "REVIEW_READY"
    APPROVED = "APPROVED"
    PUBLISHING_READY = "PUBLISHING_READY"
    PUBLISHING = "PUBLISHING"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    ACTIVE = "ACTIVE"
    TELEGRAM_READY = "TELEGRAM_READY"


class ProductLifecycleAction(str, Enum):
    COMPLETE_STRATEGY = "Complete Strategy"
    READY_FOR_REVIEW = "Ready for Review"
    APPROVE_PRODUCT = "Approve Product"
    PUBLISH_PRODUCT = "Publish Product"
    WAIT_FOR_PUBLISHING = "Wait for Publishing"
    PASTE_MEDIA_LINK = "Paste Media Link"
    READY_FOR_TELEGRAM = "Ready for Telegram"
    NO_ACTION_REQUIRED = "No Action Required"


@dataclass(frozen=True)
class ProductLifecycleRecommendation:
    action: ProductLifecycleAction
    label: str
    reason: str | None = None
    target_stage: ProductLifecycleStage | None = None
    source: str = "ProductLifecycleService"


@dataclass(frozen=True)
class ProductLifecycle:
    """Read-only Product lifecycle projection.

    ProductLifecycle summarizes existing Product, Review, Publishing, and
    Creator Workflow state. It does not mutate Product or Publishing records.
    """

    product_id: str | None
    stage: ProductLifecycleStage
    recommendation: ProductLifecycleRecommendation
    workflow_snapshot: CreatorWorkflowSnapshot | None = None
    approval_status: str | None = None
    product_status: str | None = None
    publishing_status: str | None = None
    media_link_status: str | None = None
    telegram_ready: bool = False
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommended_action(self) -> str:
        return self.recommendation.label
