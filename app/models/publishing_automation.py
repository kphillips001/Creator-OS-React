"""Provider-neutral Publishing Automation read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.product_lifecycle import ProductLifecycle


class PublishingAutomationState(str, Enum):
    NOT_READY = "NOT_READY"
    READY_TO_PUBLISH = "READY_TO_PUBLISH"
    QUEUED = "QUEUED"
    UPLOAD_IN_PROGRESS = "UPLOAD_IN_PROGRESS"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    VERIFY_MEDIA_LINK = "VERIFY_MEDIA_LINK"
    PUBLISHING_COMPLETE = "PUBLISHING_COMPLETE"
    READY_FOR_TELEGRAM = "READY_FOR_TELEGRAM"
    NEEDS_ATTENTION = "NEEDS_ATTENTION"


class PublishingAutomationAction(str, Enum):
    READY_TO_PUBLISH = "Ready to Publish"
    MONITOR_UPLOAD = "Upload in Progress"
    WAITING_FOR_MEDIA_LINK = "Waiting for Media Link"
    VERIFY_MEDIA_LINK = "Verify Media Link"
    PUBLISHING_COMPLETE = "Publishing Complete"
    READY_FOR_TELEGRAM = "Ready for Telegram"
    REVIEW_PUBLISHING_FAILURE = "Review Publishing Failure"
    NO_PUBLISHING_ACTION = "No Publishing Action"


@dataclass(frozen=True)
class PublishingAutomationRecommendation:
    action: PublishingAutomationAction
    label: str
    reason: str | None = None
    source: str = "PublishingAutomationService"


@dataclass(frozen=True)
class PublishingAutomationStatus:
    """Read-only publishing automation projection.

    This model summarizes existing Product Lifecycle, Creator Workflow, and
    Publishing projections. It does not upload, create jobs, verify media links,
    activate Products, or execute Telegram behavior.
    """

    state: PublishingAutomationState
    recommendation: PublishingAutomationRecommendation
    product_id: str | None = None
    lifecycle: ProductLifecycle | None = None
    publishing_status: str | None = None
    media_link_status: str | None = None
    provider_status: str | None = None
    provider_error: str | None = None
    manual_media_link_required: bool = False
    attention_required: bool = False
    telegram_ready: bool = False
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def next_recommended_action(self) -> str:
        return self.recommendation.label
