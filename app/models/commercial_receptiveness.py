"""Canonical, auditable commercial receptiveness projection."""
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class CommercialReceptivenessState(str, Enum):
    COLD = "COLD"
    WARM = "WARM"
    HOT = "HOT"
    COOLING = "COOLING"
    BACK_OFF = "BACK_OFF"


@dataclass(frozen=True)
class CommercialReceptiveness:
    state: CommercialReceptivenessState
    strength: int
    positive_evidence: tuple[str, ...]
    resistance_evidence: tuple[str, ...]
    pressure_evidence: tuple[str, ...]
    fresh_direct_intent: bool
    recent_purchase: bool
    continuation_eligible: bool
    another_sale_appropriate_now: bool
    reason: str
    commercial_interest_type: str = "NONE"

    def to_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "state": self.state.value,
            "strength": self.strength,
            "positiveEvidence": list(self.positive_evidence),
            "resistanceEvidence": list(self.resistance_evidence),
            "pressureEvidence": list(self.pressure_evidence),
            "freshDirectIntentDetected": self.fresh_direct_intent,
            "recentPurchaseDetected": self.recent_purchase,
            "continuationEligible": self.continuation_eligible,
            "anotherSaleAppropriateNow": self.another_sale_appropriate_now,
            "reason": self.reason,
            "commercialInterestType": self.commercial_interest_type,
        })
