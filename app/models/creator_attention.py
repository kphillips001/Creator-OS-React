"""Provider-neutral Creator Attention read models."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Mapping


class CreatorAttentionPriority(str, Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    NORMAL = "NORMAL"
    LOW = "LOW"


class CreatorAttentionCategory(str, Enum):
    REVIEW = "REVIEW"
    APPROVAL = "APPROVAL"
    PUBLISHING = "PUBLISHING"
    MEDIA_LINK = "MEDIA_LINK"
    FAILURE = "FAILURE"
    INFORMATION = "INFORMATION"


@dataclass(frozen=True)
class CreatorAttentionItem:
    """Read-only item describing why creator attention is or is not required."""

    category: CreatorAttentionCategory
    priority: CreatorAttentionPriority
    recommended_action: str
    reason: str
    attention_required: bool = True
    title: str | None = None
    product_id: str | None = None
    workflow_id: str | None = None
    source: str = "CreatorAttentionService"
    evidence: Mapping[str, Any] = field(default_factory=dict)
    compatibility: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class CreatorAttentionSummary:
    """Read-only prioritized creator attention projection."""

    items: tuple[CreatorAttentionItem, ...]
    attention_required: bool
    highest_priority: CreatorAttentionPriority
    recommended_action: str
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    @property
    def actionable_items(self) -> tuple[CreatorAttentionItem, ...]:
        return tuple(item for item in self.items if item.attention_required)
