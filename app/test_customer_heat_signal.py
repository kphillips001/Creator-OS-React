from datetime import datetime, timedelta, timezone

from app.services.customer_heat_signal_service import CustomerHeatSignalService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.sexual_sales_opportunity_service import SexualSalesOpportunityService


def project(message, classifier=None, tone=None):
    return CustomerHeatSignalService().project(
        message=message, classifier_result=classifier or {},
        contextual_tone=tone or {},
    )


def sexual_classifier(**extra):
    return {
        "sexual_engagement": True,
        "explicit_without_buying_intent": True,
        "escalation_ready": True,
        "recommended_action": "build_tension",
        "confidence": .94,
        **extra,
    }


def bare_brain():
    service = object.__new__(CustomerSalesBrainService)
    service.config = type("Config", (), {
        "sexual_receptiveness_min_engagements": 4,
    })()
    return service


def hot_context(message="I'm feeling frisky"):
    return {
        "inbound_message_count": 1,
        "sexual_engagement_count": 0,
        "sexual_engagement_only": False,
        "customer_heat_signal": project(message, sexual_classifier()),
        "sexual_sales_opportunity": {"sexualSalesOpportunityEligible": True},
        "effective_content_selling_allowed": True,
    }


def test_cold_ordinary_affection_and_mild_compliment_retain_warmup():
    for text in ("Hi", "How are you?", "You're beautiful", "Hey ❤️", "Love your mirror selfie"):
        assert project(text)["warmupOverrideEligible"] is False


def test_richard_shaped_turns_are_current_customer_heat():
    for text in ("I'm feeling a little frisky right now", "I'm home alone, wish you were here"):
        result = project(text, sexual_classifier())
        assert result["detected"] is True
        assert result["customerInitiated"] is True
        assert result["strength"] == "STRONG"
        assert result["warmupOverrideEligible"] is True


def test_stu_shaped_escalation_is_stronger_than_ordinary_compliment():
    assert project(
        "Love your mirror selfie. Make me tingle down below", sexual_classifier(),
    )["warmupOverrideEligible"] is True
    assert project("Love your mirror selfie")["warmupOverrideEligible"] is False


def test_eric_sequence_crosses_threshold_without_endless_escalation():
    turns = (
        "I wish you were here with me",
        "Thinking about you beside a bonfire is giving me naughty thoughts",
        "I keep fantasizing about touching you",
    )
    assert all(project(text, sexual_classifier())["warmupOverrideEligible"] for text in turns)


def test_intimate_content_interest_and_request_are_heat():
    interest = project("Do you have intimate content?")
    request = project("Can you send me a sexy photo?")
    assert interest["warmupOverrideEligible"] is True
    assert request["warmupOverrideEligible"] is True
    assert interest["type"] == "INTIMATE_CONTENT_INTEREST"
    assert request["type"] == "CURRENT_COMMERCIAL_INTEREST"


def test_strong_semantic_route_aligns_but_weak_flirt_does_not_override():
    assert project("Something suggestive", sexual_classifier())["warmupOverrideEligible"] is True
    assert project("hey cutie", {
        "sexual_engagement": True, "confidence": .55,
    })["warmupOverrideEligible"] is False


def test_ava_initiated_reciprocation_does_not_override_without_escalation():
    history = ({"role": "assistant", "content": "You're trouble 😉"},)
    reciprocal = CustomerHeatSignalService().project(
        message="haha maybe", classifier_result=sexual_classifier(),
        recent_transcript=history,
    )
    escalated = CustomerHeatSignalService().project(
        message="I'm fantasizing about you touching me",
        classifier_result=sexual_classifier(), recent_transcript=history,
    )
    assert reciprocal["initiationSource"] == "AVA_INITIATED_RECIPROCATION"
    assert reciprocal["warmupOverrideEligible"] is False
    assert escalated["initiationSource"] == "CUSTOMER_ESCALATED"
    assert escalated["warmupOverrideEligible"] is True


def test_heat_feeds_episode_policy_without_authorizing_delivery():
    intents = type("Intents", (), {
        "list_confirmed_presentations_for_buyer": lambda *a, **k: [],
    })()
    result = SexualSalesOpportunityService(
        intents=intents, cooldown=timedelta(hours=72),
    ).project(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=9,
        latest_message="I'm feeling frisky", now=datetime.now(timezone.utc),
        customer_heat_signal=project("I'm feeling frisky", sexual_classifier()),
    )
    assert result["sexualSignalClass"] == "SEXUAL_ESCALATION"
    assert result["sexualSalesOpportunityEligible"] is True
    assert "offerAuthorized" not in result


def test_override_removes_warmup_blockers_only():
    service = bare_brain()
    allowed = service._proactive_hot_opportunity_assessment(
        hot_context(), active_purchase_intent=False, active_sales_session=False,
    )
    assert allowed["warmupOverrideApplied"] is True
    assert allowed["proactiveHotOpportunityAuthorized"] is True
    assert allowed["hotOpportunityBlockers"] == ()


def test_cooldown_active_intent_session_backoff_and_controls_still_block():
    service = bare_brain()
    context = {
        **hot_context(),
        "purchase_cooldown_active": True,
        "sales_progression": {"phase": "BACK_OFF"},
        "relationship_control_mode": "HUMAN_OPERATOR",
        "effective_content_selling_allowed": False,
    }
    result = service._proactive_hot_opportunity_assessment(
        context, active_purchase_intent=True, active_sales_session=True,
    )
    for blocker in (
        "ACTIVE_PURCHASE_INTENT", "ACTIVE_SALES_SESSION", "BACK_OFF",
        "HUMAN_OPERATOR", "CONTENT_SELLING_NOT_ALLOWED",
        "COMMERCIAL_OR_PROACTIVE_COOLDOWN",
    ):
        assert blocker in result["hotOpportunityBlockers"]
    assert result["proactiveHotOpportunityAuthorized"] is False


def test_commerce_relevance_uses_heat_without_forcing_offer():
    service = bare_brain()
    service.conversational_progression = type("Progression", (), {
        "has_direct_purchase_intent": lambda self, message: False,
        "transition_features": lambda self, message: {},
    })()
    relevant, reason = service._commerce_selection_relevant({
        "latest_message": "I'm feeling frisky",
        "customer_heat_signal": project("I'm feeling frisky", sexual_classifier()),
        "proactive_hot_opportunity": {
            "proactiveHotOpportunityAuthorized": True,
            "warmupOverrideApplied": True,
        },
    })
    assert relevant is True
    assert reason == "WARMUP_OVERRIDE_CUSTOMER_HEAT"
