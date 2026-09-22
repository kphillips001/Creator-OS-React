"""Strict bounded projection of the canonical current-turn commercial decision."""
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class PreGenerationCommercialDecision:
    fresh_direct_intent: bool
    current_commercial_interest: bool
    commercial_interest_type: str
    referent_present: bool
    grounded_purchase_acceptance: bool
    temporal_deferred: bool
    no_buy_boundary: bool
    classifier_rejected_buying_intent: bool
    deterministic_commercial_evidence: bool
    commercial_bypass_eligible: bool
    active_offer_nudge_candidate: bool = False
    active_offer_reservation_authorized: bool = False
    active_offer_reservation_reason: str | None = None
    mandatory_response_obligation: bool = False
    authority: str = "COMMERCIAL_RECEPTIVENESS_SERVICE"

    def diagnostics(self):
        return asdict(self)
