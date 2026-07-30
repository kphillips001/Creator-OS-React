"""Creator-owned Commercial Role assignments for canonical Media Assets."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Mapping
from uuid import UUID


COMMERCIAL_ROLE_VOCABULARY_VERSION = "1.0"


class CommercialRole(str, Enum):
    DISCOVERY = "DISCOVERY"
    HERO = "HERO"
    CORE = "CORE"
    PROGRESSION = "PROGRESSION"
    PREMIUM = "PREMIUM"
    FINALE = "FINALE"
    BONUS = "BONUS"


class CommercialRoleState(str, Enum):
    SUGGESTED = "SUGGESTED"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    INACTIVE = "INACTIVE"
    RETIRED = "RETIRED"


class CommercialRoleOrigin(str, Enum):
    AI_SUGGESTED = "AI_SUGGESTED"
    CREATOR_ASSIGNED = "CREATOR_ASSIGNED"
    OPERATOR_ASSIGNED = "OPERATOR_ASSIGNED"


class CommercialRoleActorType(str, Enum):
    AI = "AI"
    CREATOR = "CREATOR"
    OPERATOR = "OPERATOR"


@dataclass(frozen=True)
class CommercialRoleAssignment:
    assignment_id: UUID
    asset_id: int
    creator_profile_id: int
    role: CommercialRole
    state: CommercialRoleState
    origin: CommercialRoleOrigin
    rationale: str | None
    suggestion_confidence: float | None
    evidence: Mapping[str, Any] = field(default_factory=dict)
    assigned_by_type: CommercialRoleActorType | None = None
    assigned_by_identifier: str | None = None
    vocabulary_version: str = COMMERCIAL_ROLE_VOCABULARY_VERSION
    created_at: datetime | None = None
    updated_at: datetime | None = None


@dataclass(frozen=True)
class CommercialRoleHistoryEntry:
    history_id: int
    assignment_id: UUID
    asset_id: int
    creator_profile_id: int
    role: CommercialRole
    event_type: str
    previous_state: CommercialRoleState | None
    new_state: CommercialRoleState
    actor_type: CommercialRoleActorType
    actor_identifier: str | None
    reason: str | None
    created_at: datetime

