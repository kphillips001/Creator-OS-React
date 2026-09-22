from datetime import datetime, timezone

import pytest

from app.services.ppv_escalation_projection_service import PPVEscalationProjectionService


def project(**overrides):
    values = {"mapped": False, "verified_purchase_count": None, "intents": (),
              "latest_diagnostics": {}, "follow_through": {"available": True}}
    values.update(overrides)
    return PPVEscalationProjectionService().project(**values)


def diagnostics(*, signal="NONE", fresh=False, decision="CONTINUE_CONVERSATION",
                reason="CURRENT_TURN_NOT_READY", authorized=False, sexual=False,
                selected=False):
    return {"customer_value_attention": {"commercialInterestType": signal,
             "freshCommercialIntentDetected": fresh},
            "commerce_decision": {"decision": decision, "reason": reason,
             "proactiveProgression": {"authorized": authorized},
             "recommendation": {"selected": selected}},
            "sexual_commercial_progression": {
             "sexualEngagementDetected": sexual,
             "sustainedSexualReceptiveness": False}}


@pytest.mark.parametrize("signal", ["COMMERCIAL_CURIOSITY", "PRICE_REQUEST",
                                     "DIRECT_CONTENT_INTENT", "SEND_OR_LINK_REQUEST"])
def test_current_canonical_commercial_signals_project_interest(signal):
    result = project(latest_diagnostics=diagnostics(signal=signal, fresh=True))
    assert result["stage"] == "COMMERCIAL_INTEREST"
    assert result["nextAction"] == "COMMERCIAL_EVALUATION"


def test_joseph_sexual_only_high_tier_evidence_remains_warming():
    result = project(latest_diagnostics=diagnostics(sexual=True))
    assert result["stage"] == "WARMING"
    assert result["warmupStatus"] == "IN_PROGRESS"
    assert result["commercialSignal"] == "NONE"
    assert result["nextAction"] == "CONTINUE_WARMUP"
    assert "not" in result["why"] or "no current commercial intent" in result["why"]


def test_authorized_selected_offer_is_ready_to_offer():
    result = project(latest_diagnostics=diagnostics(
        decision="PRESENT_OFFER", authorized=True, selected=True))
    assert result["stage"] == "READY_TO_OFFER"
    assert result["nextAction"] == "PRESENT_OFFER"


def intent(status="PRESENTED", confirmed=True):
    return {"purchase_intent_id": "intent-1", "status": status,
            "presented_at": datetime(2026, 9, 14, tzinfo=timezone.utc),
            "confirmed_delivery": confirmed, "title": "Set",
            "offering_type": "SINGLE", "expected_price_minor": 1200}


def test_active_presented_intent_is_awaiting_purchase():
    result = project(intents=[intent()])
    assert result["stage"] == "AWAITING_PURCHASE"
    assert result["purchaseIntentState"] == "PRESENTED"


@pytest.mark.parametrize("follow,stage,action", [
    ({"available": True, "eligible": True}, "FOLLOW_UP_ELIGIBLE", "NUDGE"),
    ({"available": True, "confirmed_nudge": True}, "NUDGE_SENT", "AWAIT_PURCHASE"),
    ({"available": True, "backoff": True}, "BACKOFF", "BACK_OFF"),
])
def test_follow_through_precedence(follow, stage, action):
    result = project(intents=[intent()], follow_through=follow)
    assert (result["stage"], result["nextAction"]) == (stage, action)


def test_verified_settlement_has_highest_precedence():
    result = project(mapped=True, verified_purchase_count=2, intents=[intent()],
                     follow_through={"available": True, "backoff": True})
    assert result["stage"] == "PURCHASED"
    assert result["verifiedPurchases"] == 2


def test_operator_projection_exposes_backend_nonbuyer_policy_authority():
    result = project(follow_through={"available": True, "backoff": True,
        "conversation_policy": {"responsePurpose": "TIME_WASTER_COMPRESSED_REPLY",
            "supporterBoundaryConfirmed": True, "timeWaster": True,
            "dailyOptionalReplyLimit": 2, "optionalRepliesUsedToday": 1,
            "sexualAccessGated": True, "relationshipRemainsActive": True}})
    assert result["conversationPolicy"] == {
        "responsePurpose": "TIME_WASTER_COMPRESSED_REPLY",
        "supporterBoundaryCommunicated": True,
        "timeWaster": True,
        "timeWasterReason": "Repeated sexual boundary-pushing after a confirmed supporter boundary.",
        "optionalReplyAllowance": 2, "optionalRepliesUsedToday": 1,
        "nextResetAt": None, "sexualAccessGated": True,
        "relationshipActive": True, "commercialReentry": False}


def test_durable_backoff_precedes_hot_projection_without_fresh_intent():
    hot = {"proactiveHotOpportunityAuthorized": True}
    result = project(
        intents=[intent(status="EXPIRED")],
        latest_diagnostics=readiness_diagnostics(hot=hot),
        follow_through={"available": True, "confirmed_nudge": True,
                        "backoff": True},
    )
    assert result["stage"] == "BACKOFF"
    assert result["nextAction"] == "BACK_OFF"
    assert result["offerEligibility"] != "EVALUATION_READY"


def test_fresh_direct_intent_can_reenter_after_durable_backoff():
    result = project(
        latest_diagnostics=readiness_diagnostics(
            signal="PRICE_REQUEST", fresh=True),
        follow_through={"available": True, "confirmed_nudge": True,
                        "backoff": True},
    )
    assert result["stage"] == "COMMERCIAL_RE_ENTRY"
    assert result["nextAction"] == "COMMERCIAL_EVALUATION"


def test_explicit_canonical_reentry_projects_but_generic_permission_does_not():
    assert project(commercial_reentry=True)["stage"] == "COMMERCIAL_RE_ENTRY"
    assert project(latest_diagnostics={"relationshipNurture": {
        "commercialReentryAllowed": True}})["stage"] == "WARMING"


def test_missing_optional_followthrough_is_bounded_unavailable():
    result = project(follow_through={"available": False})
    assert result["followUpStatus"] == "UNAVAILABLE"
    assert result["nudgeStatus"] == "UNAVAILABLE"
    assert result["backoffStatus"] == "UNAVAILABLE"


def test_hvp_or_tier_metadata_cannot_manufacture_offer_readiness():
    result = project(latest_diagnostics={"marketTier": "HIGH",
        "operatorClassification": "HIGH_VALUE_PROSPECT"})
    assert result["stage"] == "WARMING"


def readiness_diagnostics(*, evidence=(), authorized=False, sexual_count=0,
                          sustained=False, signal="NONE", fresh=False,
                          hot=None):
    value = {"behaviorEvidenceCounts": {"inbound_message_count": 8,
        "meaningful_engagement_count": 5, "offer_exposure_count": 0,
        "sexual_engagement_count": sexual_count}}
    return {"customer_value_attention": value,
        "commercial_receptiveness": {"commercialInterestType": signal,
            "freshDirectIntentDetected": fresh},
        "commerce_decision": {"decision": "CONTINUE_CONVERSATION",
            "reason_code": "CURRENT_TURN_NOT_READY", "proactive_progression": {
                "proactiveProgressionAuthorized": authorized,
                "proactiveProgressionEvidence": list(evidence)},
            "proactive_hot_opportunity": dict(hot or {})},
        "commercial_summary": {"sexualCommercialProgression": {
            "sustainedSexualReceptiveness": sustained}}}


def test_new_prospect_readiness_fails_closed_without_evidence():
    readiness = project()["offerReadiness"]
    assert readiness["status"] == "UNKNOWN"
    assert readiness["distance"] == "Additional warming required"
    assert all(item["status"] == "UNAVAILABLE" for item in readiness["requirements"][:-1])


def test_exactly_one_proactive_condition_remaining():
    required = {key for key, _ in PPVEscalationProjectionService.PROACTIVE_REQUIREMENTS}
    readiness = project(latest_diagnostics=readiness_diagnostics(
        evidence=required - {"RECIPROCAL_RELATIONAL_WARMING"}))["offerReadiness"]
    assert readiness["distance"] == "1 condition remaining"


def test_threshold_satisfied_does_not_hide_another_boolean_gate():
    evidence = {"SUSTAINED_VOLUNTARY_CONVERSATION", "MEANINGFUL_ENGAGEMENT",
        "VOLUNTARY_SELF_DISCLOSURE", "NO_OFFER_EXPOSURE"}
    readiness = project(latest_diagnostics=readiness_diagnostics(
        evidence=evidence, sexual_count=4, sustained=True))["offerReadiness"]
    assert readiness["qualifyingSignals"]["sexualEngagementCount"] == 4
    assert readiness["requirements"][-1]["status"] == "SATISFIED"
    assert readiness["distance"] == "1 condition remaining"


def test_all_warming_gates_mean_evaluation_not_automatic_offer():
    evidence = {key for key, _ in PPVEscalationProjectionService.PROACTIVE_REQUIREMENTS}
    readiness = project(latest_diagnostics=readiness_diagnostics(
        evidence=evidence, authorized=True))["offerReadiness"]
    assert readiness["distance"] == "Ready for commercial evaluation"


@pytest.mark.parametrize("signal", ["PRICE_REQUEST", "DIRECT_CONTENT_INTENT",
                                     "SEND_OR_LINK_REQUEST", "PURCHASE_ACCEPTANCE"])
def test_direct_commercial_signals_expose_bypass_without_frontend_inference(signal):
    readiness = project(latest_diagnostics=readiness_diagnostics(
        signal=signal, fresh=True))["offerReadiness"]
    assert readiness["bypass"]["available"] is True
    assert readiness["distance"] == "Ready for commercial evaluation"


def test_newer_confirmed_diagnostics_replace_older_count_projection():
    old = project(latest_diagnostics=readiness_diagnostics(
        sexual_count=3, sustained=False))["offerReadiness"]
    new = project(latest_diagnostics=readiness_diagnostics(
        sexual_count=6, sustained=True))["offerReadiness"]
    assert old["qualifyingSignals"]["sexualEngagementCount"] == 3
    assert new["qualifyingSignals"] == {
        "sexualEngagementCount": 6, "sexualReceptivenessThreshold": 4,
        "sustainedSexualReceptiveness": True}


def test_authorized_hot_path_projects_evaluation_not_ready_to_offer():
    hot = {
        "proactiveHotOpportunityDetected": True,
        "proactiveHotOpportunityAuthorized": True,
        "sustainedConversationSatisfied": True,
        "sustainedConversationCount": 15,
        "sustainedConversationRequired": 6,
        "sustainedSexualReceptiveness": True,
        "sexualEngagementCount": 7,
        "sexualEngagementRequired": 4,
        "currentHotToneQualified": True,
        "noPriorPaidOfferExposure": True,
        "commercialSafeguardsPassed": True,
        "hotOpportunityBlockers": [],
        "commercialEvaluationReason": "SUSTAINED_HOT_CONVERSATION",
    }
    result = project(latest_diagnostics=readiness_diagnostics(
        sexual_count=7, sustained=True, hot=hot,
    ))
    assert result["stage"] == "COMMERCIAL_EVALUATION"
    assert result["nextAction"] == "EVALUATE_OFFER"
    assert result["offerEligibility"] == "EVALUATION_READY"
    assert result["offerReadiness"]["status"] == "EVALUATION_READY"
    assert result["offerReadiness"]["hotPath"]["status"] == "SATISFIED"
    assert result["offerReadiness"]["hotPath"]["sexualEngagementCount"] == 7
    assert result["offerReadiness"]["hotPath"]["note"].startswith("Evaluation only")


def test_blocked_hot_path_preserves_relational_gaps_and_warming():
    result = project(latest_diagnostics=readiness_diagnostics(hot={
        "proactiveHotOpportunityDetected": True,
        "proactiveHotOpportunityAuthorized": False,
        "hotOpportunityBlockers": ["PRIOR_PAID_OFFER_EXPOSURE"],
    }))
    assert result["stage"] == "WARMING"
    assert result["offerReadiness"]["hotPath"]["status"] == "BLOCKED"
    assert result["offerReadiness"]["hotPath"]["blockers"] == [
        "PRIOR_PAID_OFFER_EXPOSURE"
    ]
