from datetime import datetime, timedelta, timezone

from app.services.conversation_coherence_service import ConversationCoherenceService
from app.services.gpt_service import GPTService


NOW = datetime(2026, 9, 15, 22, 0, tzinfo=timezone.utc)


def unresolved(text, *, age=timedelta(minutes=1)):
    return {
        "operation_id": "prior-operation",
        "inbound_message_text": text,
        "inbound_received_at": NOW - age,
        "unsatisfied_obligations": ["ANSWER_DIRECT_QUESTION"],
    }


def test_el_fantastico_work_clarification():
    result = ConversationCoherenceService.resolve(
        current_text="For work, that is…",
        antecedent=unresolved("Do you do anything besides content?"), now=NOW,
    )
    assert result.resolved is True
    assert result.persona_domain == "OCCUPATION_WORK"
    assert result.turn_obligations == ("ANSWER_DIRECT_QUESTION",)
    assert result.resolved_customer_meaning == "What else do you do for work besides content?"


def test_fun_and_content_format_clarifications():
    fun = ConversationCoherenceService.resolve(
        current_text="For fun, I mean.", antecedent=unresolved("Do you hike?"), now=NOW)
    photos = ConversationCoherenceService.resolve(
        current_text="Mostly photos?", antecedent=unresolved("Do you make content?"), now=NOW)
    assert (fun.resolved, fun.persona_domain) == (True, "INTERESTS_LIFESTYLE")
    assert photos.resolved_customer_meaning == "Is the content you make mostly photos?"


def test_no_fabricated_antecedent_and_expiry():
    unrelated = ConversationCoherenceService.resolve(
        current_text="For work, though?", antecedent=unresolved("Nice weather."), now=NOW)
    expired = ConversationCoherenceService.resolve(
        current_text="For work.",
        antecedent=unresolved("Do you do anything besides content?", age=timedelta(minutes=11)),
        now=NOW,
    )
    assert unrelated.resolved is False
    assert expired.resolved is False
    assert expired.failure_reason == "ANTECEDENT_EXPIRED"


def test_no_resolution_without_unsatisfied_question():
    antecedent = unresolved("Do you hike?")
    antecedent["unsatisfied_obligations"] = ["ACKNOWLEDGE_COMPLIMENT"]
    result = ConversationCoherenceService.resolve(
        current_text="For fun, I mean.", antecedent=antecedent, now=NOW)
    assert result.resolved is False


def test_occupation_relevance_blocks_pool_and_allows_grounded_answer():
    question = "What else do you do for work besides content?"
    blocked = GPTService._foreground_semantic_relevance(
        question, "Work by the pool sounds like a pretty sweet gig.")
    allowed = GPTService._foreground_semantic_relevance(
        question, "I also work in marketing and events.")
    unknown = GPTService._foreground_semantic_relevance(
        question, "I don't have another job established beyond content.")
    assert blocked["required"] is True and blocked["satisfied"] is False
    assert allowed["satisfied"] is True
    assert unknown["satisfied"] is True


def test_compliments_have_only_acknowledgement_semantics():
    for text in (
        "You look beautiful.",
        "I love your photos.",
        "You're gorgeous.",
        "That picture is amazing.",
        "You look so naturally beautiful in your photos. I love them.",
    ):
        obligations = GPTService._turn_obligations(text, new_relationship=False)
        assert "ACKNOWLEDGE_COMPLIMENT" in obligations
        assert "ANSWER_DIRECT_QUESTION" not in obligations
        assert "ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" not in obligations


def test_miroslav_compliment_acknowledgement_satisfies_quality_semantics():
    style = GPTService._style_analysis(
        "Aw, thank you—that's really sweet of you.",
        "You look so naturally beautiful in your photos. I love them.",
        pressure={}, ordinary=True, memory_callback=False,
        new_relationship=False,
    )
    assert style["turnObligations"] == ["ACKNOWLEDGE_COMPLIMENT"]
    assert style["turnObligationsSatisfied"] is True
    assert style["unsatisfiedTurnObligations"] == []


def test_commercial_and_persona_contrasts_remain_distinct():
    assert "HONOR_COMMERCIAL_REQUEST" in GPTService._turn_obligations(
        "How much is your content?", new_relationship=False)
    assert "ANSWER_DIRECT_QUESTION" in GPTService._turn_obligations(
        "What else do you do for work?", new_relationship=False)
    assert "HONOR_COMMERCIAL_REQUEST" not in GPTService._turn_obligations(
        "What else do you do for work besides content?", new_relationship=False)


def test_terminal_operation_remains_distinct_from_semantic_projection():
    antecedent = unresolved("Do you do anything besides content?")
    result = ConversationCoherenceService.resolve(
        current_text="For work, that is.", antecedent=antecedent, now=NOW)
    assert result.resolved is True
    assert antecedent["operation_id"] == "prior-operation"
    assert "state" not in antecedent  # projection has no lifecycle mutation authority
