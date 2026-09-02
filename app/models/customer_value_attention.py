"""Canonical, side-effect-free customer value and attention projection."""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Mapping


@dataclass(frozen=True)
class CustomerValueAttention:
    value_authority: str
    buyer_status: str
    buyer_stage: str
    value_tier: str
    retention_lifecycle: str
    retention_priority: str
    lifetime_spend_minor: int
    average_order_value_minor: int
    largest_order_minor: int
    purchase_count: int
    last_purchase_at: str | None
    purchase_recency_days: float | None
    reactivation_state: str
    commercial_momentum: str
    attention_tier: str
    effort_mode: str
    time_waster_risk: str
    time_waster_evidence: tuple[str, ...]
    commercial_opportunity_exposure_count: int
    presented_opportunity_count: int
    failed_nonconverted_opportunity_count: int
    converted_opportunity_count: int
    active_unresolved_opportunity: bool
    proactive_tease_delivered_count: int
    build_interest_exposure_count: int
    offer_exposure_count: int
    customer_commercial_response_count: int
    time_waster_opportunity_basis: bool
    buyer_protection_applied: bool
    buyer_protection_reason: str | None
    low_cost_nurture_eligible: bool
    low_cost_nurture_active: bool
    low_cost_nurture_reason: str | None
    nurture_response_budget: int
    nurture_responses_used: int
    nurture_next_optional_response_at: str | None
    optional_ordinary_reply_suppressed: bool
    suppression_reason: str | None
    fresh_commercial_intent_detected: bool
    nurture_bypassed_for_commercial_intent: bool
    nurture_exited_after_purchase: bool
    commercial_interest_type: str
    conversation_continuation_value: str
    commercial_progression_pressure: str
    taper_applied: bool
    taper_reason: str | None
    relationship_investment: str
    memory_priority: str
    sales_pressure: str
    offer_cadence: str
    current_commercial_interest: bool = False
    historical_commercial_interest: bool = False
    commercial_trajectory_protection_active: bool = False
    commercial_trajectory_protection_reason: str | None = None
    commercial_trajectory_decay_reason: str | None = None
    explicit_nonpayment_detected: bool = False
    browsing_only_detected: bool = False
    time_waster_score: int = 0
    relationship_discovery: Mapping[str, Any] = field(default_factory=dict)
    offering_type_affinity: Mapping[str, Any] = field(default_factory=dict)
    content_affinity: Mapping[str, Any] = field(default_factory=dict)
    price_affinity: Mapping[str, Any] = field(default_factory=dict)
    canonical_signals_consumed: tuple[str, ...] = ()
    legacy_signals_consumed: tuple[str, ...] = ()
    conflict_resolution: tuple[str, ...] = ()
    reason: str = ""
    compatibility: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "compatibility", MappingProxyType(dict(self.compatibility)))
        object.__setattr__(self, "relationship_discovery", MappingProxyType(dict(self.relationship_discovery)))
        object.__setattr__(self, "offering_type_affinity", MappingProxyType(dict(self.offering_type_affinity)))
        object.__setattr__(self, "content_affinity", MappingProxyType(dict(self.content_affinity)))
        object.__setattr__(self, "price_affinity", MappingProxyType(dict(self.price_affinity)))

    def to_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "schemaVersion": "customer_value_attention_v1",
            "authority": self.value_authority,
            "buyerStatus": self.buyer_status,
            "buyerStage": self.buyer_stage,
            "valueTier": self.value_tier,
            "retentionLifecycle": self.retention_lifecycle,
            "retentionPriority": self.retention_priority,
            "lifetimeSpendMinor": self.lifetime_spend_minor,
            "averageOrderValueMinor": self.average_order_value_minor,
            "largestOrderMinor": self.largest_order_minor,
            "purchaseCount": self.purchase_count,
            "lastPurchaseAt": self.last_purchase_at,
            "purchaseRecencyDays": self.purchase_recency_days,
            "reactivationState": self.reactivation_state,
            "commercialMomentum": self.commercial_momentum,
            "attentionTier": self.attention_tier,
            "effortMode": self.effort_mode,
            "timeWasterRisk": self.time_waster_risk,
            "timeWasterEvidence": list(self.time_waster_evidence),
            "commercialOpportunityExposureCount": self.commercial_opportunity_exposure_count,
            "presentedOpportunityCount": self.presented_opportunity_count,
            "failedNonconvertedOpportunityCount": self.failed_nonconverted_opportunity_count,
            "convertedOpportunityCount": self.converted_opportunity_count,
            "activeUnresolvedOpportunity": self.active_unresolved_opportunity,
            "proactiveTeaseDeliveredCount": self.proactive_tease_delivered_count,
            "buildInterestExposureCount": self.build_interest_exposure_count,
            "offerExposureCount": self.offer_exposure_count,
            "customerCommercialResponseCount": self.customer_commercial_response_count,
            "timeWasterOpportunityBasis": self.time_waster_opportunity_basis,
            "buyerProtectionApplied": self.buyer_protection_applied,
            "buyerProtectionReason": self.buyer_protection_reason,
            "lowCostNurtureEligible": self.low_cost_nurture_eligible,
            "lowCostNurtureActive": self.low_cost_nurture_active,
            "lowCostNurtureReason": self.low_cost_nurture_reason,
            "nurtureResponseBudget": self.nurture_response_budget,
            "nurtureResponsesUsed": self.nurture_responses_used,
            "nurtureNextOptionalResponseAt": self.nurture_next_optional_response_at,
            "optionalOrdinaryReplySuppressed": self.optional_ordinary_reply_suppressed,
            "suppressionReason": self.suppression_reason,
            "freshCommercialIntentDetected": self.fresh_commercial_intent_detected,
            "nurtureBypassedForCommercialIntent": self.nurture_bypassed_for_commercial_intent,
            "nurtureExitedAfterPurchase": self.nurture_exited_after_purchase,
            "commercialInterestType": self.commercial_interest_type,
            "conversationContinuationValue": self.conversation_continuation_value,
            "commercialProgressionPressure": self.commercial_progression_pressure,
            "taperApplied": self.taper_applied,
            "taperReason": self.taper_reason,
            "relationshipInvestment": self.relationship_investment,
            "memoryPriority": self.memory_priority,
            "salesPressure": self.sales_pressure,
            "offerCadence": self.offer_cadence,
            "currentCommercialInterest": self.current_commercial_interest,
            "historicalCommercialInterest": self.historical_commercial_interest,
            "commercialTrajectoryProtectionActive": self.commercial_trajectory_protection_active,
            "commercialTrajectoryProtectionReason": self.commercial_trajectory_protection_reason,
            "commercialTrajectoryDecayReason": self.commercial_trajectory_decay_reason,
            "explicitNonpaymentDetected": self.explicit_nonpayment_detected,
            "browsingOnlyDetected": self.browsing_only_detected,
            "timeWasterScore": self.time_waster_score,
            "relationshipDiscovery": dict(self.relationship_discovery),
            "offeringTypeAffinity": dict(self.offering_type_affinity),
            "contentAffinity": dict(self.content_affinity),
            "priceAffinity": dict(self.price_affinity),
            "canonicalSignalsConsumed": list(self.canonical_signals_consumed),
            "legacySignalsConsumed": list(self.legacy_signals_consumed),
            "conflictResolution": list(self.conflict_resolution),
            "reason": self.reason,
            "legacyRelationshipObservationsAuthority": "ADVISORY_ONLY",
            "compatibility": dict(self.compatibility),
        })
