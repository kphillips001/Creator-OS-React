from datetime import datetime, timedelta, timezone

import pytest

from app.services.customer_value_attention_service import (
    CustomerValueAttentionService,
)
from app.services.commercial_nonpayment_evidence_service import (
    CommercialNonpaymentEvidenceService,
)


NOW = datetime(2026, 9, 1, 18, 0, tzinfo=timezone.utc)


def project(commerce=None, behavior=None):
    return CustomerValueAttentionService().project(
        commerce_memory=commerce or {"purchaseCount": 0},
        behavior=behavior or {},
        now=NOW,
    )


def repeated_nonconversion(**extra):
    return {
        "message_count": 20,
        "presented_opportunity_count": 2,
        "failed_nonconverted_opportunity_count": 2,
        "low_information_response_count": 4,
        **extra,
    }


def test_one_failed_opportunity_does_not_activate_nurture():
    result = project(behavior=repeated_nonconversion(
        presented_opportunity_count=1,
        failed_nonconverted_opportunity_count=1,
    ))
    assert result.low_cost_nurture_eligible is False
    assert result.low_cost_nurture_active is False
    assert result.optional_ordinary_reply_suppressed is False


def test_repeated_proven_nonconversion_activates_low_cost_nurture():
    result = project(behavior=repeated_nonconversion())
    assert result.low_cost_nurture_eligible is True
    assert result.low_cost_nurture_active is True
    assert result.attention_tier == "LOW"
    assert result.effort_mode == "MINIMAL"
    assert result.nurture_response_budget == 1
    assert result.optional_ordinary_reply_suppressed is False


def test_consumed_rolling_budget_suppresses_optional_chat():
    last = NOW - timedelta(hours=2)
    result = project(behavior=repeated_nonconversion(
        nurture_response_count_rolling_day=1,
        last_nurture_response_at=last,
    ))
    assert result.optional_ordinary_reply_suppressed is True
    assert result.suppression_reason == "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
    assert result.nurture_next_optional_response_at == (
        last + timedelta(hours=24)
    ).isoformat()


def test_next_rolling_day_permits_another_lightweight_response():
    result = project(behavior=repeated_nonconversion(
        nurture_response_count_rolling_day=0,
        last_nurture_response_at=NOW - timedelta(hours=25),
    ))
    assert result.low_cost_nurture_active is True
    assert result.optional_ordinary_reply_suppressed is False


def test_fresh_buying_intent_immediately_bypasses_nurture():
    result = project(behavior=repeated_nonconversion(
        nurture_response_count_rolling_day=1,
        direct_buying_intent=True,
    ))
    assert result.low_cost_nurture_eligible is True
    assert result.low_cost_nurture_active is False
    assert result.optional_ordinary_reply_suppressed is False
    assert result.fresh_commercial_intent_detected is True
    assert result.nurture_bypassed_for_commercial_intent is True
    assert result.attention_tier == "HIGH"


def test_provider_purchase_exits_nonbuyer_nurture():
    result = project(
        commerce={"purchaseCount": 1, "lifetimeGrossMinor": 300},
        behavior=repeated_nonconversion(converted_opportunity_count=1),
    )
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.buyer_stage == "FIRST_TIME_BUYER"
    assert result.low_cost_nurture_eligible is False
    assert result.low_cost_nurture_active is False
    assert result.nurture_exited_after_purchase is True
    assert result.relationship_investment == "WARM"


@pytest.mark.parametrize("purchase_count,gross", [
    (1, 300), (2, 1800), (4, 20_000), (8, 60_000),
])
def test_verified_buyers_never_enter_nonbuyer_nurture(purchase_count, gross):
    result = project(
        commerce={"purchaseCount": purchase_count, "lifetimeGrossMinor": gross},
        behavior=repeated_nonconversion(),
    )
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.low_cost_nurture_eligible is False
    assert result.low_cost_nurture_active is False


def test_sexuality_alone_does_not_activate_commercial_nurture():
    result = project(behavior={
        "message_count": 30,
        "sexual_engagement_only": True,
        "sexual_engagement_count": 12,
        "post_offer_sexual_engagement_count": 12,
        "failed_nonconverted_opportunity_count": 0,
    })
    assert result.low_cost_nurture_active is False
    assert result.time_waster_risk == "NONE"


@pytest.mark.parametrize("behavior", [
    {"message_count": 20, "low_information_response_count": 10},
    {"message_count": 20, "hostility_level": "HIGH", "repeated_hostility": True},
])
def test_quiet_or_rude_alone_does_not_activate_commercial_nurture(behavior):
    result = project(behavior=behavior)
    assert result.low_cost_nurture_eligible is False
    assert result.low_cost_nurture_active is False


def test_healthy_good_lead_without_failed_opportunities_is_not_throttled():
    result = project(behavior={
        "message_count": 8,
        "meaningful_engagement_count": 5,
        "presented_opportunity_count": 0,
        "failed_nonconverted_opportunity_count": 0,
    })
    assert result.low_cost_nurture_active is False
    assert result.effort_mode == "BALANCED"


def test_derived_state_is_reversible_when_canonical_basis_is_absent():
    prior = project(behavior=repeated_nonconversion())
    current = project(behavior={
        "message_count": 21,
        "presented_opportunity_count": 2,
        "failed_nonconverted_opportunity_count": 0,
        "meaningful_engagement_count": 5,
    })
    assert prior.low_cost_nurture_active is True
    assert current.low_cost_nurture_active is False


@pytest.mark.parametrize("message,nonpayment,browsing", [
    ("I'm just browsing", False, True),
    ("I'm not buying right now", True, False),
    ("I don't feel like paying", True, False),
    ("I'm only here to look", False, True),
    ("I'm not spending anything today", True, False),
    ("maybe later, I'm not paying now", True, False),
    ("I just want to see what's available", False, True),
])
def test_current_nonpayment_and_browsing_semantics(message, nonpayment, browsing):
    result = CommercialNonpaymentEvidenceService.classify(message)
    assert result["explicitNonpaymentDetected"] is nonpayment
    assert result["browsingOnlyDetected"] is browsing


def test_repeated_nonpayment_decays_historical_commercial_protection():
    result = project(behavior=repeated_nonconversion(
        rejection_count=4,
        idle_browsing_signal_count=4,
        commercial_movement=True,
        commercial_movement_count=2,
        explicit_nonpayment_detected=True,
        browsing_only_detected=True,
    ))
    assert result.historical_commercial_interest is True
    assert result.current_commercial_interest is False
    assert result.commercial_trajectory_protection_active is False
    assert result.commercial_trajectory_decay_reason == (
        "REPEATED_TERMINAL_NONCONVERSION_AND_CURRENT_NONPAYMENT"
    )
    assert result.time_waster_risk == "HIGH"
    assert result.low_cost_nurture_active is True
    diagnostics = dict(result.to_mapping())
    assert diagnostics["currentCommercialInterest"] is False
    assert diagnostics["historicalCommercialInterest"] is True
    assert diagnostics["commercialTrajectoryProtectionActive"] is False
    assert diagnostics["explicitNonpaymentDetected"] is True
    assert diagnostics["browsingOnlyDetected"] is True
    assert diagnostics["timeWasterScore"] >= 6


def test_one_failure_with_repeated_nonpayment_does_not_activate_nurture():
    result = project(behavior=repeated_nonconversion(
        presented_opportunity_count=1,
        failed_nonconverted_opportunity_count=1,
        rejection_count=5,
        idle_browsing_signal_count=5,
        explicit_nonpayment_detected=True,
        browsing_only_detected=True,
    ))
    assert result.low_cost_nurture_eligible is False
    assert result.low_cost_nurture_active is False
    assert result.time_waster_risk != "HIGH"


def test_active_unresolved_offer_preserves_customer_from_nurture():
    result = project(behavior=repeated_nonconversion(
        rejection_count=4,
        idle_browsing_signal_count=4,
        explicit_nonpayment_detected=True,
        browsing_only_detected=True,
        active_unresolved_opportunity=True,
    ))
    assert result.low_cost_nurture_active is False
    assert "ACTIVE_UNRESOLVED_OPPORTUNITY_PROTECTION" in result.time_waster_evidence


def test_current_direct_intent_supersedes_historical_nonconversion():
    result = project(behavior=repeated_nonconversion(
        rejection_count=4,
        idle_browsing_signal_count=4,
        direct_buying_intent=True,
        commercial_interest_type="SEND_OR_LINK_REQUEST",
    ))
    assert result.current_commercial_interest is True
    assert result.commercial_trajectory_protection_active is True
    assert result.low_cost_nurture_active is False
    assert result.nurture_bypassed_for_commercial_intent is True


def test_single_price_objection_is_not_persistent_browsing():
    evidence = CommercialNonpaymentEvidenceService.classify(
        "that's too expensive"
    )
    assert evidence["explicitNonpaymentDetected"] is False
    assert evidence["browsingOnlyDetected"] is False
