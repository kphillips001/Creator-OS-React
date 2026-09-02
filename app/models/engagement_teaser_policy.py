"""Deterministic policy contracts for autonomous Free Engagement Teasers."""
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


ENGAGEMENT_POLICY_KEY = "INTELLIGENT_FREE_ENGAGEMENT_TEASERS"
ENGAGEMENT_POLICY_VERSION = "engagement_teaser_policy_v1"


class EngagementStrategy(str, Enum):
    WARM_UP = "WARM_UP"
    RE_ENGAGE = "RE_ENGAGE"
    RELATIONSHIP = "RELATIONSHIP"


@dataclass(frozen=True)
class EngagementTeaserPolicyConfig:
    dormant_inactivity_days: int = 21
    reengagement_cooldown_days: int = 45
    warm_up_minimum_inbound_messages: int = 6
    minimum_messages_between_teasers: int = 8
    minimum_days_between_teasers: int = 7
    relationship_cooldown_days: int = 30
    maximum_per_active_conversation: int = 1
    maximum_per_rolling_period: int = 2
    rolling_period_days: int = 30
    meaningful_history_minimum_inbound_messages: int = 8
    relationship_minimum_inbound_messages: int = 12
    relationship_recent_activity_days: int = 3
    active_conversation_hours: int = 24

    @classmethod
    def from_mapping(cls, value):
        allowed = cls.__dataclass_fields__
        source = dict(value or {})
        return cls(**{key: int(source[key]) for key in allowed if key in source})

    def to_dict(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(frozen=True)
class EngagementTeaserDecision:
    decision: str
    reason_code: str
    strategy: EngagementStrategy | None = None
    evidence: dict[str, Any] = field(default_factory=dict)
    suppression_evidence: dict[str, Any] = field(default_factory=dict)
    policy_version: str = ENGAGEMENT_POLICY_VERSION
    decision_id: str | None = None
