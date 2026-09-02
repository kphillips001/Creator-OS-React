"""Structured contract for backend-enforced adaptive proactive selling."""
from dataclasses import dataclass, field
from typing import Any


SALES_READINESS_POLICY_KEY = "ADAPTIVE_SALES_READINESS"
SALES_READINESS_POLICY_VERSION = "adaptive_sales_readiness_v1"


@dataclass(frozen=True)
class AdaptiveSalesReadinessConfig:
    normal_prospect_target_min: int = 10
    normal_prospect_target_max: int = 15
    meaningful_inactivity_days: int = 7
    count_direction: str = "INBOUND_CUSTOMER"
    count_scope: str = "CURRENT_WARMUP_WINDOW"
    benchmark_is_advisory: bool = True
    benchmark_never_forces_offer: bool = True
    direct_purchase_intent_bypass: bool = True
    strong_buying_intent_acceleration: bool = True
    engagement_acceleration: bool = True
    relationship_history_adjustment: bool = True
    buyer_history_adjustment: bool = True
    free_teaser_response_adjustment: bool = True
    active_session_precedence: bool = True
    safety_precedence: bool = True
    backoff_precedence: bool = True
    recent_purchase_cooldown_precedence: bool = True
    active_offer_precedence: bool = True
    payment_state_precedence: bool = True
    ownership_precedence: bool = True
    availability_precedence: bool = True

    @classmethod
    def from_mapping(cls, value):
        source = dict(value or {})
        fields = cls.__dataclass_fields__
        return cls(**{key: source[key] for key in fields if key in source})

    def to_dict(self):
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass(frozen=True)
class AdaptiveSalesReadinessDecision:
    authorized: bool
    reason_code: str
    segment: str
    direct_intent: bool
    strong_readiness: bool
    warmup_depth: int
    benchmark_position: str
    evidence: dict[str, Any] = field(default_factory=dict)
    suppression_evidence: dict[str, Any] = field(default_factory=dict)
    policy_version: str = SALES_READINESS_POLICY_VERSION

