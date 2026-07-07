"""Provider-neutral Creator Workflow read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping

from app.models.creator_intent import CreatorIntent


class CreatorWorkflowStage(str, Enum):
    IMPORTED = "IMPORTED"
    CONTENT_ANALYZED = "CONTENT_ANALYZED"
    EXPERIENCE_CREATED = "EXPERIENCE_CREATED"
    PRODUCT_STRATEGY_READY = "PRODUCT_STRATEGY_READY"
    COMMERCE_STRATEGY_READY = "COMMERCE_STRATEGY_READY"
    IN_CREATOR_REVIEW = "IN_CREATOR_REVIEW"
    APPROVED = "APPROVED"
    PUBLISHING = "PUBLISHING"
    WAITING_FOR_MEDIA_LINK = "WAITING_FOR_MEDIA_LINK"
    ACTIVE = "ACTIVE"
    TELEGRAM_READY = "TELEGRAM_READY"


WORKFLOW_STAGE_ORDER = (
    CreatorWorkflowStage.IMPORTED,
    CreatorWorkflowStage.CONTENT_ANALYZED,
    CreatorWorkflowStage.EXPERIENCE_CREATED,
    CreatorWorkflowStage.PRODUCT_STRATEGY_READY,
    CreatorWorkflowStage.COMMERCE_STRATEGY_READY,
    CreatorWorkflowStage.IN_CREATOR_REVIEW,
    CreatorWorkflowStage.APPROVED,
    CreatorWorkflowStage.PUBLISHING,
    CreatorWorkflowStage.WAITING_FOR_MEDIA_LINK,
    CreatorWorkflowStage.ACTIVE,
    CreatorWorkflowStage.TELEGRAM_READY,
)


@dataclass(frozen=True)
class CreatorWorkflowStageStatus:
    stage: CreatorWorkflowStage
    status: str
    summary: str | None = None
    source: str | None = None
    evidence: tuple[Mapping[str, Any], ...] = ()
    compatibility: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorWorkflowSnapshot:
    """Read-only status projection for a Creator OS workflow item."""

    workflow_id: str | None
    current_stage: CreatorWorkflowStage
    stages: tuple[CreatorWorkflowStageStatus, ...]
    creator_intent: CreatorIntent | None = None
    asset_ids: tuple[int, ...] = ()
    product_id: str | None = None
    experience_id: str | None = None
    content_type: str | None = None
    product_status: str | None = None
    approval_status: str | None = None
    publishing_status: str | None = None
    media_link_status: str | None = None
    telegram_ready: bool = False
    completed_stages: tuple[CreatorWorkflowStage, ...] = ()
    pending_stages: tuple[CreatorWorkflowStage, ...] = ()
    blocked_stages: tuple[CreatorWorkflowStage, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def stage_status(self, stage: CreatorWorkflowStage | str) -> str | None:
        normalized = (
            stage if isinstance(stage, CreatorWorkflowStage) else CreatorWorkflowStage(stage)
        )
        for item in self.stages:
            if item.stage == normalized:
                return item.status
        return None
