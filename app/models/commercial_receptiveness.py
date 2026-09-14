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
    deferred_commercial_interest: bool = False
    deferred_interest_reason: str | None = None
    current_commercial_interest: bool = False
    future_commercial_reentry_allowed: bool = True
    temporal_commercial_qualifier: str | None = None
    commercial_referent_present: bool = False
    commercial_referent_type: str = "NONE"
    acceptance_grounded: bool = False
    nurture_bypassed: bool = False

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
            "deferredCommercialInterest": self.deferred_commercial_interest,
            "deferredInterestReason": self.deferred_interest_reason,
            "currentCommercialInterest": self.current_commercial_interest,
            "futureCommercialReentryAllowed": self.future_commercial_reentry_allowed,
            "temporalCommercialQualifier": self.temporal_commercial_qualifier,
            "commercialReferentPresent": self.commercial_referent_present,
            "commercialReferentType": self.commercial_referent_type,
            "acceptanceGrounded": self.acceptance_grounded,
            "nurtureBypassed": self.nurture_bypassed,
        })
