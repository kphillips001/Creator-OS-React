import pytest

from app.services.ava_natural_conversation_policy import AvaNaturalConversationPolicy
from app.services.ava_offline_access_policy import AvaOfflineAccessPolicy, OfflineContextType


@pytest.fixture
def policy():
    return AvaOfflineAccessPolicy()


@pytest.mark.parametrize(("text", "expected"), [
    ("When can we meet?", OfflineContextType.EXPLICIT_MEETUP_REQUEST),
    ("Can I visit you?", OfflineContextType.VISIT_OR_TRAVEL_REQUEST),
    ("Come visit me.", OfflineContextType.VISIT_OR_TRAVEL_REQUEST),
    ("I'd love to take you to dinner", OfflineContextType.DATE_REQUEST),
    ("Want to get drinks together?", OfflineContextType.DATE_REQUEST),
    ("What's your address?", OfflineContextType.LOCATION_TO_VISIT_REQUEST),
    ("I could drive there this weekend", OfflineContextType.VISIT_OR_TRAVEL_REQUEST),
    ("Will you fly out to see me?", OfflineContextType.VISIT_OR_TRAVEL_REQUEST),
    ("I want to have sex when we meet", OfflineContextType.FUTURE_SEXUAL_ENCOUNTER_REQUEST),
    ("I'll hold you when we're together", OfflineContextType.FUTURE_PHYSICAL_INTIMACY_REQUEST),
    ("Can we meeet in person?", OfflineContextType.EXPLICIT_MEETUP_REQUEST),
])
def test_actual_offline_requests_require_boundary(policy, text, expected):
    result = policy.classify(text)
    assert result.context_type is expected
    assert result.boundary_required is True
    assert result.offline_access_allowed is False
    assert result.fantasy_allowed is True


@pytest.mark.parametrize("text", [
    "I dreamed we had the perfect date",
    "Imagine we met on a beach in a movie",
    "Let's roleplay a fantasy meetup",
])
def test_explicit_fantasy_remains_allowed(policy, text):
    result = policy.classify(text)
    assert result.context_type is OfflineContextType.FANTASY_OR_HYPOTHETICAL
    assert result.boundary_required is False


@pytest.mark.parametrize("text", [
    "Nice to meet you", "See you later", "Maybe someday you'll see the pictures",
    "Want to see the photos?", "I met a friendly dog in the story",
])
def test_false_positives_are_not_offline_context(policy, text):
    assert policy.classify(text).context_type is OfflineContextType.NO_OFFLINE_CONTEXT


def test_wish_you_were_here_stays_warm_without_a_required_disclaimer(policy):
    result = policy.classify("I wish you were here")
    assert result.context_type is OfflineContextType.INDIRECT_OFFLINE_INVITATION
    assert result.boundary_required is False
    assert not policy.candidate_violation_reasons(
        "You make that sound pretty tempting 😏", authority=result,
        customer_text="I wish you were here")


def test_location_then_travel_is_multi_turn_safe(policy):
    result = policy.classify("I could drive there this weekend", recent_history=[
        {"role": "assistant", "text": "I'm near the coast."}])
    assert result.context_type is OfflineContextType.VISIT_OR_TRAVEL_REQUEST
    assert result.boundary_required


def test_visual_context_does_not_grant_travel_authority(policy):
    result = policy.classify("You should come here with me", visual_context={
        "summary": "Customer vacation image with an ocean view"})
    assert result.context_type is OfflineContextType.VISIT_OR_TRAVEL_REQUEST
    assert result.offline_access_allowed is False


@pytest.mark.parametrize("status", ["BUYER", "HVP", "COMMERCIAL_ACTIVE", "SEXUAL_AUTHORIZED"])
def test_status_never_overrides_offline_authority(policy, status):
    projection = {**policy.classify("When can we meet?").diagnostics(), "status": status}
    assert projection["offlineAccessAllowed"] is False
    assert projection["commercialOverrideAllowed"] is False
    assert projection["sexualAuthorityOverrideAllowed"] is False


@pytest.mark.parametrize(("customer", "candidate"), [
    ("You're missing some amazing sunsets", "Maybe I'm saving the best moments for when we finally meet."),
    ("It's all about pleasuring you", "Maybe one day you'll get to show me just how much."),
    ("I don't know what's keeping you so far away", "Maybe I'm just waiting for you to close that gap a little."),
])
def test_historical_dave_joseph_clay_candidates_are_forbidden(policy, customer, candidate):
    assert policy.candidate_violation_reasons(
        candidate, authority=policy.classify(customer), customer_text=customer,
    ) == ("MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION",)


def test_natural_policy_reports_forbidden_generation_for_final_gate(policy):
    authority = policy.classify("When can we meet?")
    decision = AvaNaturalConversationPolicy().evaluate(
        customer_text="When can we meet?", candidate="I can't wait until we finally meet.",
        diagnostics={"offlineAccessAuthority": authority.diagnostics()})
    assert decision.text == "I can't wait until we finally meet."
    assert "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION" in decision.reasons


def test_prompt_answers_direct_question_without_future_eligibility(policy):
    prompt = policy.classify("When can we meet?").prompt_block()
    assert "boundaryRequired: true" in prompt
    assert "Let's keep things online for now" in prompt
    assert "creates no later eligibility" in prompt


def test_coarse_location_small_talk_remains_allowed(policy):
    assert policy.classify("Are you near the coast?").context_type is OfflineContextType.NO_OFFLINE_CONTEXT


def test_diagnostics_are_bounded_and_operation_scoped(policy):
    diagnostics = policy.classify("Can I visit?").diagnostics()
    assert diagnostics["operationScoped"] is True
    assert "transcript" not in diagnostics
