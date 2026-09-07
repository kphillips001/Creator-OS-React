from app.api.test_chat import ScenarioPrepareRequest
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.commercial_receptiveness_service import (
    CommercialReceptivenessService,
)
from app.services.gpt_service import GPTService
from app.services.session_escalation_decision_service import (
    SessionEscalationDecisionService,
)
from app.testing.session5_scenario_harness import SCENARIO_MANIFEST


def test_c20_is_formally_defined_without_changing_c01_through_c19():
    identifiers = [item.scenario_id for item in SCENARIO_MANIFEST]
    assert identifiers[:19] == [f"C{number:02d}" for number in range(1, 20)]
    assert identifiers[19:] == ["C20"]

    c20 = SCENARIO_MANIFEST[-1]
    assert c20.name == "END_TO_END_SESSION_SELLING"
    assert c20.certification_objectives == (
        "SESSION_OPPORTUNITY", "TEASER", "FIRST_PAID_ITEM",
        "STRUCTURED_PRICE_NO_VERBAL_PRICE",
        "PURCHASE_ACKNOWLEDGEMENT", "NATURAL_CONTINUATION",
        "NEXT_PAID_STEP", "MULTIPLE_PURCHASE_PROGRESSION",
        "ESCALATION", "FINALE", "COMPLETION", "POST_SESSION_RETENTION",
    )
    assert set(c20.branch_checkpoints) == {
        "CUSTOMER_FACING_SESSION_TERMINOLOGY_NOT_REQUIRED",
        "FREE_TEASER_NO_PAID_COMMERCE", "SESSION_STATE_CONTINUITY",
        "NO_UNRELATED_OFFER_INTERRUPTION", "OWNERSHIP_EXCLUSION",
        "POST_COMPLETION_NO_AUTOMATIC_REOPEN",
    }
    assert c20.canonical_customer_turns == (
        "you've got me curious tonight", "okay, now you've got my attention",
        "tease me a little", "I like where this is going", "show me more",
        "I paid for it", "that was worth it, keep going", "what's next?",
        "send me that one", "I paid for that one too",
        "take it up another level", "show me the next one", "I bought it",
        "that was really good", "we should do that again sometime",
    )
    assert [
        (
            event.after_turn,
            event.presentation_authority_types,
            event.expected_session_position,
            event.expected_foundation_reference,
            event.expected_session_role,
        )
        for event in c20.canonical_events
    ] == [
        (5, ("SEND_OR_LINK_REQUEST",), 2, "certification-C20", None),
        (9, ("SEND_OR_LINK_REQUEST",), 3, "certification-C20", None),
        (12, ("SEND_OR_LINK_REQUEST",), 4, "certification-C20", "FINALE"),
    ]
    assert ScenarioPrepareRequest(scenario_id="C20").scenario_id == "C20"


def test_c20_customer_language_keeps_internal_session_terms_out_of_the_script():
    script = SCENARIO_MANIFEST[-1].canonical_customer_turns
    internal_terms = (
        "session", "sales session", "position", "step", "first_unlock",
        "escalation", "finale",
    )
    assert not any(
        term in message.casefold()
        for message in script
        for term in internal_terms
    )


def test_c20_natural_paid_requests_have_existing_semantic_authority():
    progression = ConversationalSalesProgressionService()
    for turn in ("show me more", "send me that one", "show me the next one"):
        assert progression.has_direct_purchase_intent(turn) is True
        assert progression.recommended_conversational_action(
            turn, {}, {},
        ) == "PRESENT_OFFER"


def test_c20_natural_tease_is_foregrounded_without_paid_intent():
    progression = ConversationalSalesProgressionService()
    turn = "tease me a little"
    relevance = GPTService._foreground_semantic_relevance(
        turn, "Careful, I can tease you a little.",
    )
    assert relevance["intent"] == "TEASE_OR_FLIRT_REQUEST"
    assert relevance["satisfied"] is True
    assert progression.has_direct_purchase_intent(turn) is False


def test_c20_natural_continuation_and_final_request_do_not_need_role_words():
    assert SessionEscalationDecisionService.continuation_intent(
        "that was worth it, keep going"
    ) == "ONGOING_EXPERIENCE"
    assert ConversationalSalesProgressionService().has_direct_purchase_intent(
        "show me the next one"
    ) is True


def test_c20_noncommercial_negative_controls_do_not_authorize_commerce():
    progression = ConversationalSalesProgressionService()
    for turn in ("how was your day?", "I'm just hanging out", "you look cute"):
        assert progression.has_direct_purchase_intent(turn) is False
        assert progression.recommended_conversational_action(
            turn, {}, {},
        ) == "CHAT"


def test_c20_post_completion_language_is_not_current_purchase_intent():
    progression = ConversationalSalesProgressionService()
    feedback = "that was really good"
    future = "we should do that again sometime"
    assert progression.has_direct_purchase_intent(feedback) is False
    assert progression.has_direct_purchase_intent(future) is False
    temporal = CommercialReceptivenessService.temporal_commercial_deferment(
        future
    )
    assert temporal["currentCommercialInterest"] is False
    assert temporal["futureCommercialReentryAllowed"] is True
