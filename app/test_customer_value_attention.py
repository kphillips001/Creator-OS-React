from datetime import datetime, timedelta, timezone

import pytest

from app.services.customer_value_attention_service import CustomerValueAttentionService
from app.services.outreach_mass_ppv_coordination_service import OutreachMassPPVCoordinationService
from app.engine.decision_engine import DecisionEngine


NOW = datetime(2026, 8, 28, tzinfo=timezone.utc)


def project(commerce=None, behavior=None, legacy=None):
    return CustomerValueAttentionService().project(
        commerce_memory=commerce, behavior=behavior, legacy=legacy, now=NOW,
    )


@pytest.mark.parametrize("effort", ["BALANCED", "COMPRESSED", "MINIMAL"])
def test_canonical_effort_projection_reaches_legacy_gpt_boundary_unchanged(effort):
    projection = dict(project({"purchaseCount": 0}).to_mapping())
    projection["effortMode"] = effort
    projection["attentionTier"] = "LOW" if effort != "BALANCED" else "MEDIUM"
    projection["compatibility"] = {
        "effort_mode": "balanced", "attention_tier": "medium",
    }

    flattened = DecisionEngine._canonical_attention_compatibility(projection)

    assert flattened["effort_mode"] == effort.lower()
    assert flattened["attention_tier"] == projection["attentionTier"].lower()


@pytest.mark.parametrize(
    "case,commerce,behavior,expected",
    [
        ("A", {"purchaseCount": 0}, {"message_count": 2},
         ("PROSPECT", "NONE", "BALANCED")),
        ("B", {"purchaseCount": 0}, {"message_count": 20, "commercial_movement": True},
         ("ENGAGED_PROSPECT", "NONE", "BALANCED")),
        ("C", {"purchaseCount": 0}, {"message_count": 20, "offer_exposure_count": 3,
                                      "failed_nonconverted_opportunity_count": 3},
         ("LOW_VALUE_PROSPECT", "HIGH", "MINIMAL")),
        ("D", {"purchaseCount": 0}, {"message_count": 12, "sexual_engagement_only": True},
         ("ENGAGED_PROSPECT", "NONE", "BALANCED")),
        ("E", {"purchaseCount": 1, "lifetimeGrossMinor": 300}, {},
         ("BUYER", "NONE", "BALANCED")),
        ("F", {"purchaseCount": 1, "lifetimeGrossMinor": 300, "purchaseRecencyDays": 2}, {},
         ("BUYER", "NONE", "BALANCED")),
        ("G", {"purchaseCount": 2, "lifetimeGrossMinor": 1200}, {},
         ("REPEAT_BUYER", "NONE", "FULL")),
        ("H", {"purchaseCount": 3, "lifetimeGrossMinor": 15000}, {},
         ("HIGH_VALUE", "NONE", "FULL")),
        ("I", {"purchaseCount": 5, "lifetimeGrossMinor": 50000}, {},
         ("WHALE", "NONE", "FULL")),
        ("J", {"purchaseCount": 1, "lifetimeGrossMinor": 300},
         {"message_count": 20, "offer_exposure_count": 3, "rejection_count": 3},
         ("BUYER", "NONE", "COMPRESSED")),
        ("K", {"purchaseCount": 8, "lifetimeGrossMinor": 60000},
         {"message_count": 30, "rejection_count": 3},
         ("WHALE", "NONE", "BALANCED")),
        ("L", {"purchaseCount": 1, "lifetimeGrossMinor": 300, "purchaseRecencyDays": 180}, {},
         ("BUYER", "NONE", "BALANCED")),
        ("N", {"purchaseCount": 0}, {"message_count": 20, "active_session": True},
         ("ENGAGED_PROSPECT", "NONE", "BALANCED")),
    ],
)
def test_deterministic_customer_value_matrix(case, commerce, behavior, expected):
    result = project(commerce, behavior)
    assert (result.value_tier, result.time_waster_risk, result.effort_mode) == expected, case


def test_d_first_party_sexual_engagement_is_not_buying_intent():
    result = project({"purchaseCount": 0}, {
        "message_count": 12, "sexual_engagement_only": True,
    })
    assert result.commercial_momentum == "COLD"
    assert result.commercial_progression_pressure == "NORMAL"
    assert result.time_waster_opportunity_basis is False


def test_sexual_high_volume_after_repeated_commercial_exposure_is_attributed():
    result = project({"purchaseCount": 0}, {
        "message_count": 12,
        "sexual_engagement_only": True,
        "proactive_tease_delivered_count": 1,
        "build_interest_exposure_count": 1,
        "offer_exposure_count": 2,
        "failed_nonconverted_opportunity_count": 2,
    })
    assert result.time_waster_risk == "HIGH"
    assert result.effort_mode == "MINIMAL"
    assert result.time_waster_opportunity_basis is True
    assert result.commercial_opportunity_exposure_count == 4


def test_one_failed_ppv_is_not_strong_time_waster_evidence():
    result = project({"purchaseCount": 0}, {
        "message_count": 7, "sexual_engagement_only": True,
        "offer_exposure_count": 1, "post_offer_sexual_engagement_count": 2,
    })
    assert result.time_waster_risk != "HIGH"
    assert "MULTIPLE_OFFERS_NO_CONVERSION" not in result.time_waster_evidence
    assert "REPEATED_POST_OFFER_SEXUAL_CONSUMPTION_NO_CONVERSION" not in result.time_waster_evidence


def test_presented_active_offer_is_not_failed_without_terminal_evidence():
    result = project({"purchaseCount": 0}, {
        "message_count": 4,
        "offer_exposure_count": 1,
        "presented_opportunity_count": 1,
        "active_unresolved_opportunity": True,
    })
    assert result.presented_opportunity_count == 1
    assert result.failed_nonconverted_opportunity_count == 0
    assert result.active_unresolved_opportunity is True


def test_repeated_failed_ppvs_plus_post_offer_sexual_consumption_tapers():
    result = project({"purchaseCount": 0}, {
        "message_count": 10, "sexual_engagement_only": True,
        "offer_exposure_count": 2, "post_offer_sexual_engagement_count": 3,
        "failed_nonconverted_opportunity_count": 2,
    })
    assert result.time_waster_risk == "HIGH"
    assert result.effort_mode == "MINIMAL"
    assert "MULTIPLE_OFFERS_NO_CONVERSION" in result.time_waster_evidence
    assert "REPEATED_POST_OFFER_SEXUAL_CONSUMPTION_NO_CONVERSION" in result.time_waster_evidence


def test_post_offer_time_waster_thresholds_are_configurable(monkeypatch):
    monkeypatch.setenv("CUSTOMER_VALUE_MIN_FAILED_PAID_OPPORTUNITIES", "3")
    monkeypatch.setenv("CUSTOMER_VALUE_MIN_POST_OFFER_SEXUAL_TURNS", "4")
    service = CustomerValueAttentionService()
    before = service.project(commerce_memory={"purchaseCount": 0}, behavior={
        "message_count": 7, "sexual_engagement_only": True,
        "offer_exposure_count": 2, "post_offer_sexual_engagement_count": 4,
        "failed_nonconverted_opportunity_count": 2,
    }, now=NOW)
    after = service.project(commerce_memory={"purchaseCount": 0}, behavior={
        "message_count": 10, "sexual_engagement_only": True,
        "offer_exposure_count": 3, "post_offer_sexual_engagement_count": 4,
        "failed_nonconverted_opportunity_count": 3,
    }, now=NOW)
    assert "MULTIPLE_OFFERS_NO_CONVERSION" not in before.time_waster_evidence
    assert "REPEATED_POST_OFFER_SEXUAL_CONSUMPTION_NO_CONVERSION" in after.time_waster_evidence


def test_eight_friendly_messages_without_commercial_opportunity_are_not_time_wasting():
    result = project({"purchaseCount": 0}, {"message_count": 8})
    assert result.time_waster_risk == "NONE"
    assert "PERSISTENT_CHAT_WITHOUT_COMMERCIAL_MOVEMENT" not in result.time_waster_evidence
    assert result.time_waster_opportunity_basis is False


def test_one_short_reply_does_not_taper_or_promote_by_turn_count():
    result = project({"purchaseCount": 0}, {
        "message_count": 7, "low_information_response_count": 1,
    })
    assert result.value_tier == "PROSPECT"
    assert result.time_waster_risk == "NONE"
    assert result.effort_mode == "BALANCED"


def test_sustained_low_return_compresses_effort_without_commercial_time_waster():
    result = project({"purchaseCount": 0}, {
        "message_count": 7,
        "low_information_response_count": 4,
        "idle_browsing_signal_count": 2,
        "meaningful_engagement_count": 1,
        "low_conversational_return_count": 6,
    })
    assert result.time_waster_risk == "NONE"
    assert result.attention_tier == "LOW"
    assert result.effort_mode == "COMPRESSED"
    assert result.taper_applied is True
    assert result.taper_reason == "SUSTAINED_LOW_CONVERSATIONAL_RETURN"
    assert result.conversation_continuation_value == "LOW"
    assert "ACCUMULATED_LOW_INFORMATION_LOW_RECIPROCITY" not in result.time_waster_evidence


@pytest.mark.parametrize("message_count", [1, 2])
def test_initial_quiet_turns_receive_balanced_effort(message_count):
    result = project({"purchaseCount": 0}, {
        "message_count": message_count,
        "low_information_response_count": message_count,
        "meaningful_engagement_count": 0,
        "low_conversational_return_count": message_count,
    })
    assert result.effort_mode == "BALANCED"
    assert result.taper_applied is False
    assert result.time_waster_risk == "NONE"


def test_meaningful_engagement_restores_normal_effort_after_quiet_history():
    result = project({"purchaseCount": 0}, {
        "message_count": 8,
        "low_information_response_count": 5,
        "meaningful_engagement_count": 2,
        "low_conversational_return_count": 5,
    })
    assert result.effort_mode == "BALANCED"
    assert result.taper_applied is False
    assert result.time_waster_risk == "NONE"


def test_created_but_never_presented_intent_is_not_an_opportunity():
    result = project({"purchaseCount": 0}, {
        "message_count": 20,
        "presented_opportunity_count": 0,
        "failed_nonconverted_opportunity_count": 0,
        "active_purchase_intent": True,
        "sexual_engagement_only": True,
    })
    assert result.presented_opportunity_count == 0
    assert result.time_waster_opportunity_basis is False
    assert result.time_waster_risk == "NONE"


def test_one_confirmed_presented_opportunity_does_not_create_high_risk():
    result = project({"purchaseCount": 0}, {
        "message_count": 20,
        "presented_opportunity_count": 1,
        "failed_nonconverted_opportunity_count": 1,
        "sexual_engagement_only": True,
        "post_offer_sexual_engagement_count": 5,
    })
    assert result.time_waster_opportunity_basis is True
    assert result.time_waster_risk != "HIGH"
    assert result.effort_mode != "MINIMAL"


def test_repeated_durable_nonconversion_can_taper_attention():
    result = project({"purchaseCount": 0}, {
        "message_count": 20,
        "presented_opportunity_count": 2,
        "failed_nonconverted_opportunity_count": 2,
        "sexual_engagement_only": True,
        "post_offer_sexual_engagement_count": 4,
        "low_information_response_count": 4,
    })
    assert result.time_waster_risk == "HIGH"
    assert result.effort_mode == "MINIMAL"
    assert "MULTIPLE_OFFERS_NO_CONVERSION" in result.time_waster_evidence


def test_active_unresolved_offer_is_protected_not_counted_as_failed():
    result = project({"purchaseCount": 0}, {
        "message_count": 20,
        "presented_opportunity_count": 1,
        "failed_nonconverted_opportunity_count": 0,
        "active_unresolved_opportunity": True,
    })
    assert result.active_unresolved_opportunity is True
    assert result.time_waster_risk == "NONE"
    assert "ACTIVE_UNRESOLVED_OPPORTUNITY_PROTECTION" in result.time_waster_evidence


def test_verified_purchase_recovers_prior_nonconversion_risk():
    result = project({"purchaseCount": 1, "lifetimeGrossMinor": 300}, {
        "message_count": 40,
        "presented_opportunity_count": 4,
        "failed_nonconverted_opportunity_count": 3,
        "converted_opportunity_count": 1,
        "sexual_engagement_only": True,
        "post_offer_sexual_engagement_count": 8,
    })
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.time_waster_risk in {"NONE", "LOW"}
    assert result.effort_mode != "MINIMAL"


def test_genuine_engagement_and_buying_intent_recover_immediately():
    quiet = {
        "message_count": 6,
        "low_information_response_count": 5,
        "idle_browsing_signal_count": 2,
        "meaningful_engagement_count": 1,
        "direct_buying_intent": True,
    }
    result = project({"purchaseCount": 0}, quiet)
    assert result.value_tier == "ENGAGED_PROSPECT"
    assert result.time_waster_risk in {"NONE", "LOW"}
    assert result.attention_tier == "HIGH"
    assert result.commercial_momentum == "HOT"


def test_positive_response_after_one_tease_is_protected_as_movement():
    result = project({"purchaseCount": 0}, {
        "message_count": 14,
        "proactive_tease_delivered_count": 1,
        "customer_commercial_response_count": 1,
        "sales_progression_phase": "BUILD_INTEREST",
    })
    assert result.time_waster_risk == "NONE"
    assert result.commercial_opportunity_exposure_count == 1


def test_e_verified_first_buyer_gets_retention_protection():
    result = project({"purchaseCount": 1, "lifetimeGrossMinor": 300})
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.buyer_stage == "FIRST_TIME_BUYER"
    assert result.buyer_protection_applied is True
    assert result.retention_priority == "NORMAL"
    assert result.relationship_investment == "WARM"
    assert result.memory_priority == "ELEVATED"
    assert result.sales_pressure == "LOW"
    assert result.offer_cadence == "POST_PURCHASE_CAREFUL"


def test_l_dormant_buyer_remains_a_buyer():
    result = project({
        "purchaseCount": 1, "lifetimeGrossMinor": 300,
        "lastPurchaseAt": (NOW - timedelta(days=180)).isoformat(),
    })
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.retention_lifecycle == "DORMANT_BUYER"
    assert result.reactivation_state == "DORMANT"
    assert result.offer_cadence == "REENGAGEMENT_CAREFUL"


def test_dormant_buyer_reactivation_restores_buyer_attention_without_cold_reset():
    result = project({
        "purchaseCount": 2,
        "lifetimeGrossMinor": 1800,
        "lastPurchaseAt": (NOW - timedelta(days=180)).isoformat(),
    }, {"current_inbound_activity": True, "message_count": 1})
    assert result.buyer_status == "VERIFIED_BUYER"
    assert result.value_tier == "REPEAT_BUYER"
    assert result.retention_lifecycle == "DORMANT_BUYER"
    assert result.reactivation_state == "REACTIVATED_BUYER"
    assert result.relationship_investment == "ELEVATED"
    assert result.attention_tier == "HIGH"


def test_whale_value_changes_relationship_investment_not_offer_frequency():
    result = project({
        "purchaseCount": 8,
        "lifetimeGrossMinor": 60000,
        "lastPurchaseAt": NOW.isoformat(),
    }, {"message_count": 50})
    assert result.value_tier == "WHALE"
    assert result.retention_priority == "VIP"
    assert result.relationship_investment == "HIGHEST"
    assert result.memory_priority == "HIGHEST"
    assert result.sales_pressure == "LOW"
    assert result.offer_cadence == "CAREFUL_PREMIUM"


def test_canonical_projection_labels_legacy_relationship_data_advisory():
    result = project(
        {"purchaseCount": 0, "lifetimeGrossMinor": 0},
        legacy={"user_value_tier": "whale", "is_whale": True},
    ).to_mapping()
    assert result["authority"] == "COMMERCE_BACKED_AUTHORITATIVE_VALUE"
    assert result["buyerStatus"] == "NONBUYER"
    assert result["legacyRelationshipObservationsAuthority"] == "ADVISORY_ONLY"


def test_m_price_sensitive_buyer_retains_canonical_affinity():
    result = project({
        "purchaseCount": 2, "lifetimeGrossMinor": 1800,
        "averageOrderValueMinor": 900, "largestOrderMinor": 1100,
        "affinity": {
            "offeringTypes": {"SINGLE": 2}, "tags": {"lingerie": 3},
            "typicalPriceMinMinor": 700, "typicalPriceMaxMinor": 1100,
        },
    }, {"rejection_count": 1})
    assert result.buyer_protection_applied is True
    assert result.price_affinity["typicalPriceMaxMinor"] == 1100
    assert result.offering_type_affinity == {"SINGLE": 2}


def test_o_false_buyer_claim_cannot_override_provider_truth():
    result = project(
        {"purchaseCount": 0, "lifetimeGrossMinor": 0},
        legacy={"user_value_tier": "whale", "is_whale": True},
    )
    assert result.buyer_status == "NONBUYER"
    assert result.buyer_protection_applied is False
    assert result.value_tier != "WHALE"
    assert "LEGACY_BUYER_STATUS_REJECTED_WITHOUT_PROVIDER_PURCHASE" in result.conflict_resolution


def test_legacy_fallback_preserves_compatibility_but_is_not_provider_verified():
    result = project(legacy={"user_value_tier": "whale", "is_whale": True})
    assert result.value_tier == "WHALE"
    assert result.buyer_status == "LEGACY_BUYER_UNVERIFIED"
    assert result.buyer_protection_applied is False
    assert "LEGACY_FALLBACK_NO_CANONICAL_COMMERCE" in result.legacy_signals_consumed


def test_projection_is_side_effect_free_and_schema_is_stable():
    commerce = {"purchaseCount": 1, "lifetimeGrossMinor": 300}
    behavior = {"message_count": 5}
    before = (dict(commerce), dict(behavior))
    mapping = project(commerce, behavior).to_mapping()
    assert (commerce, behavior) == before
    assert mapping["schemaVersion"] == "customer_value_attention_v1"


def test_outreach_coordination_consumes_supplied_canonical_projection():
    canonical = project(
        {"purchaseCount": 0},
        {"message_count": 20, "offer_exposure_count": 3,
         "failed_nonconverted_opportunity_count": 3},
    ).to_mapping()
    result = OutreachMassPPVCoordinationService().evaluate({
        "customer_value_attention": canonical,
    })
    assert result["time_waster"] is True
    assert result["allow_outreach"] is False
    assert result["customer_value_attention"]["timeWasterRisk"] == "HIGH"


def test_outreach_does_not_let_legacy_whale_override_canonical_prospect():
    canonical = project(
        {"purchaseCount": 0, "lifetimeGrossMinor": 0},
    ).to_mapping()
    result = OutreachMassPPVCoordinationService().evaluate({
        "customer_value_attention": canonical,
        "is_whale": True,
        "user_value_tier": "whale",
    })
    assert result["protected_user"] is False


def test_outreach_preserves_any_verified_buyer_from_canonical_projection():
    canonical = project(
        {"purchaseCount": 1, "lifetimeGrossMinor": 300},
    ).to_mapping()
    result = OutreachMassPPVCoordinationService().evaluate({
        "customer_value_attention": canonical,
    })
    assert result["protected_user"] is True
    assert result["recommended_action"] == "protect_user"
