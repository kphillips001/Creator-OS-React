from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.gpt_service import GPTService
from app.services.customer_content_presentation_validator import (
    CustomerContentPresentationValidator,
)
from app.test_turn22_future_event_memory import TURN_22_AT
from app.test_turn26_contextual_event_recall import TURN_26, _state_with_charlie_event


class Training:
    def runtime_prompt_block(self, **_):
        return ""


class Completions:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = 0
        self.messages = []

    def create(self, **kwargs):
        self.calls += 1
        self.messages.append(kwargs["messages"])
        value = next(self.responses)
        if isinstance(value, BaseException):
            raise value
        return type("Completion", (), {"choices": [type("Choice", (), {
            "message": type("Message", (), {"content": value})()
        })()]})()


def service_with(*responses):
    completions = Completions(responses)
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": completions})()})()
    return service, completions


def test_positive_attention_is_present_engagement_not_work_or_recent_activity():
    customer = "okay, now you've got my attention"

    assert GPTService._direct_personal_question_slot(customer) is None
    assert "DIRECT_QUESTION" not in GPTService._foreground_topics(customer)
    assert GPTService._foreground_topics(customer) == ["POSITIVE_ENGAGEMENT"]

    accepted = GPTService._foreground_semantic_relevance(
        customer, "good, I was hoping I had it",
    )
    assert accepted["intent"] == "POSITIVE_CONVERSATIONAL_ENGAGEMENT"
    assert accepted["satisfied"] is True
    assert accepted["unsupportedContextDomains"] == []


@pytest.mark.parametrize("candidate", (
    "sounds like you've had a lot keeping you busy",
    "the weather has been nice over there",
    "",
    "   ",
))
def test_positive_attention_rejects_unrelated_or_unsupported_context(candidate):
    result = GPTService._foreground_semantic_relevance(
        "okay, now you've got my attention", candidate,
    )
    assert result["required"] is True
    assert result["satisfied"] is False


def test_positive_attention_fallback_is_grounded_and_does_not_force_question():
    customer = "okay, now you've got my attention"
    fallback = GPTService._foreground_semantic_fallback(
        customer, effort_mode="FULL",
    )
    assert fallback == "good, I was hoping I had your attention"
    assert "?" not in fallback
    assert GPTService._foreground_semantic_relevance(
        customer, fallback,
    )["satisfied"] is True


def test_busy_acknowledgement_remains_valid_for_actual_busy_disclosure():
    customer = "work's been crazy lately"
    response = "sounds like you've had a lot keeping you busy"
    result = GPTService._foreground_semantic_relevance(customer, response)
    assert result["currentTopicDomain"] == "WORK_BUSYNESS"
    assert result["satisfied"] is True


def test_positive_attention_valid_provider_reply_survives_generation_boundary():
    service, _ = service_with("good, I was hoping I had it")
    memory = memory_none()
    response = service.generate_response(
        "default", "casual", "okay, now you've got my attention",
        user_memory(memory), False, chat_history=[],
    )
    assert response == "good, I was hoping I had it"
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert style["foregroundSemanticIntent"] == (
        "POSITIVE_CONVERSATIONAL_ENGAGEMENT"
    )
    assert style["foregroundSemanticRelevanceSatisfied"] is True


@pytest.mark.parametrize("provider_reply", (
    "sounds like you've had a lot keeping you busy",
    "the weather has been nice over there",
    "",
    "   ",
))
def test_positive_attention_invalid_provider_reply_gets_grounded_fallback(
        provider_reply):
    service, _ = service_with(*([provider_reply] * 8))
    memory = memory_none()
    response = service.generate_response(
        "default", "casual", "okay, now you've got my attention",
        user_memory(memory), False, chat_history=[],
    )
    assert response == "good, I was hoping I had your attention"
    assert "?" not in response


@pytest.mark.parametrize(("customer", "grounded"), (
    (
        "work has been taking most of my attention",
        "sounds like work has been keeping you busy",
    ),
    (
        "I've been slammed at work lately",
        "you've had a lot keeping you busy lately",
    ),
    (
        "I'm exhausted tonight",
        "sounds like you could use a little time to breathe",
    ),
    (
        "family stuff has been keeping me busy",
        "sounds like you've had a lot keeping you busy lately",
    ),
))
def test_neutral_disclosure_requires_grounding_and_rejects_unsupported_flirt(
        customer, grounded):
    rejected = GPTService._foreground_semantic_relevance(
        customer,
        "mm, keep talking like that... you still haven't seen my dangerous side",
    )
    assert rejected["required"] is True
    assert rejected["satisfied"] is False
    assert rejected["customerDisclosureDetected"] is True
    assert rejected["flirtOrSexualInboundSignal"] is False
    assert rejected["activeFlirtContext"] is False
    assert rejected["responseFlirtEscalationDetected"] is True
    assert rejected["responseFlirtEscalationAuthorized"] is False

    accepted = GPTService._foreground_semantic_relevance(customer, grounded)
    assert accepted["satisfied"] is True
    assert accepted["responseFlirtEscalationDetected"] is False


def test_active_flirt_context_allows_blend_only_when_neutral_foreground_is_covered():
    history = [{"role": "user", "content": "you always know how to distract me 😏"}]
    unrelated = GPTService._foreground_semantic_relevance(
        "work has been taking most of my attention",
        "you still haven't seen my dangerous side",
        recent_transcript=history,
    )
    assert unrelated["activeFlirtContext"] is True
    assert unrelated["responseFlirtEscalationAuthorized"] is False
    assert unrelated["satisfied"] is False

    blended = GPTService._foreground_semantic_relevance(
        "work has been taking most of my attention",
        "work has been keeping you busy... I'll save my dangerous side for later",
        recent_transcript=history,
    )
    assert blended["activeFlirtContext"] is True
    assert blended["responseFlirtEscalationDetected"] is True
    assert blended["responseFlirtEscalationAuthorized"] is True
    assert blended["satisfied"] is True


@pytest.mark.parametrize("authority_only", (
    {"customer_commerce_memory": {"verifiedPurchaseCount": 3}},
    {"customer_value_attention": {"relationshipInvestment": "HIGH"}},
))
def test_buyer_or_relationship_status_alone_does_not_authorize_flirt_escalation(
        authority_only):
    result = GPTService._foreground_semantic_relevance(
        "work has been taking most of my attention",
        "keep talking like that, you haven't seen my dangerous side",
        authority_only,
    )
    assert result["satisfied"] is False
    assert result["flirtOrSexualInboundSignal"] is False
    assert result["activeFlirtContext"] is False
    assert result["responseFlirtEscalationAuthorized"] is False


def test_explicit_flirt_and_sexual_language_remain_outside_neutral_disclosure_gate():
    flirt = GPTService._foreground_semantic_relevance(
        "you're cute and you always know how to distract me",
        "careful, I like that",
    )
    sexual = GPTService._foreground_semantic_relevance(
        "you look sexy tonight",
        "careful, keep talking like that",
    )
    assert flirt == {"required": False, "satisfied": True, "intent": None}
    assert sexual == {"required": False, "satisfied": True, "intent": None}


def test_c14_turn_four_safe_fallback_is_grounded_and_nonsexual():
    customer = "work has been taking most of my attention"
    fallback = GPTService._foreground_semantic_fallback(
        customer, effort_mode="COMPRESSED",
    )
    relevance = GPTService._foreground_semantic_relevance(customer, fallback)
    assert fallback == "sounds like you've had a lot keeping you busy"
    assert relevance["currentTopicDomain"] == "WORK_BUSYNESS"
    assert relevance["satisfied"] is True
    assert relevance["responseFlirtEscalationDetected"] is False


def test_minimal_attention_contract_rejects_explicit_free_attention_hook():
    response = "okay tell me what really turns you on?"
    style = GPTService._style_analysis(
        response, "I'm horny", pressure={}, ordinary=True,
        memory_callback=False, new_relationship=False,
    )
    violations = GPTService._attention_effort_violations(
        response, effort_mode="minimal", style=style,
    )
    assert "OPEN_ENDED_EXPLICIT_SOLICITATION" in violations
    assert "MINIMAL_UNNECESSARY_OPEN_ENDED_HOOK" in violations
    fallback = GPTService._minimal_attention_fallback(response)
    assert "?" not in fallback
    assert "turns you on" not in fallback.lower()
    assert fallback == "haha, you're trouble 😏"


def test_reduced_attention_allows_conversation_but_rejects_expansion():
    concise = "mm okay, I hear you"
    assert GPTService._attention_effort_violations(
        concise, effort_mode="compressed", style={},
    ) == []
    expansive = " ".join(["really"] * 46)
    assert GPTService._attention_effort_violations(
        expansive, effort_mode="compressed", style={},
    ) == ["REDUCED_RESPONSE_EXCESSIVE_EXPANSION"]


def test_compressed_attention_rejects_optional_relationship_question_hook():
    response = "That sounds nice. Anything fun planned?"
    style = GPTService._style_analysis(
        response, "just taking it easy", pressure={}, ordinary=True,
        memory_callback=False,
    )
    assert "REDUCED_UNNECESSARY_OPEN_ENDED_HOOK" in (
        GPTService._attention_effort_violations(
            response, effort_mode="compressed", style=style,
        )
    )


def test_compressed_attention_rejects_volunteered_entertainment_labor():
    response = "Alright, challenge accepted—let's see if I can surprise you a little."
    style = GPTService._style_analysis(
        response, "well? keep me entertained then", pressure={}, ordinary=True,
        memory_callback=False,
    )
    assert "REDUCED_VOLUNTEERED_ATTENTION_LABOR" in (
        GPTService._attention_effort_violations(
            response, effort_mode="compressed", style=style,
        )
    )
    assert GPTService._attention_effort_violations(
        "not much, just relaxing", effort_mode="compressed",
        style=GPTService._style_analysis(
            "not much, just relaxing", "what's up?", pressure={}, ordinary=True,
            memory_callback=False,
        ),
    ) == []


def test_compressed_attention_rejects_story_and_approval_seeking_for_entertain_me():
    customer = "well? keep me entertained then"
    story = "Alright, here's a quick one: I once texted the wrong group chat. Your turn?"
    approval = "Maybe I'm not good at this. What would actually catch your attention?"
    for response in (story, approval):
        violations = GPTService._attention_effort_violations(
            response, effort_mode="compressed",
            style=GPTService._style_analysis(
                response, customer, pressure={}, ordinary=True,
                memory_callback=False,
            ),
            user_message=customer,
        )
        assert violations
    assert "REDUCED_VOLUNTEERED_ATTENTION_LABOR" in (
        GPTService._attention_effort_violations(
            story, effort_mode="compressed", style={}, user_message=customer,
        )
    )
    assert "REDUCED_APPROVAL_SEEKING" in (
        GPTService._attention_effort_violations(
            approval, effort_mode="compressed", style={}, user_message=customer,
        )
    )


def test_compressed_attention_still_allows_direct_concise_confidence():
    assert GPTService._attention_effort_violations(
        "I'm not here to perform on command",
        effort_mode="compressed", style={},
        user_message="well? keep me entertained then",
    ) == []


@pytest.mark.parametrize("response,subreason", [
    ("I'll keep you entertained", "APPROVAL_RECOVERY_PROMISE"),
    ("Challenge accepted", "PERFORMANCE_ACCEPTANCE"),
    ("Okay, get ready—it won't be boring", "ENTERTAINMENT_PROMISE"),
    ("Let me surprise you", "APPROVAL_RECOVERY_PROMISE"),
    ("Give me a chance to change your mind", "APPROVAL_RECOVERY_PROMISE"),
    ("Just wait—you'll change your mind", "ENTERTAINMENT_PROMISE"),
    ("This will be worth your while", "ENTERTAINMENT_PROMISE"),
])
def test_entertainment_demand_rejects_semantically_equivalent_labor_promises(
        response, subreason):
    customer = "well? keep me entertained then"
    assert GPTService._volunteered_attention_labor_reason(
        response, user_message=customer,
    ) == subreason
    assert "REDUCED_VOLUNTEERED_ATTENTION_LABOR" in (
        GPTService._attention_effort_violations(
            response, effort_mode="compressed", style={},
            user_message=customer,
        )
    )


def test_attention_labor_detection_requires_customer_demand_context():
    assert GPTService._volunteered_attention_labor_reason(
        "Yep, I'm ready", user_message="are you ready to go?",
    ) is None
    assert GPTService._attention_effort_violations(
        "Yep, I'm ready", effort_mode="compressed", style={},
        user_message="are you ready to go?",
    ) == []


@pytest.mark.parametrize("response", [
    "I'm not here to perform on command",
    "bold of you to assume that's my job",
    "maybe you're just hard to impress",
    "fair enough",
])
def test_entertainment_demand_allows_concise_confidence_without_labor(response):
    assert GPTService._volunteered_attention_labor_reason(
        response, user_message="well? keep me entertained then",
    ) is None
    assert GPTService._attention_effort_violations(
        response, effort_mode="compressed", style={},
        user_message="well? keep me entertained then",
    ) == []


def test_indirect_entertainment_promise_is_rejected_during_bounded_rewrite():
    initial = "I'll keep you entertained"
    indirect = "Okay, get ready—it won't be boring"
    service, _ = service_with(initial, indirect, "I'm not here to perform on command")
    memory = memory_none()
    context = user_memory(memory)
    context.update({"attention_tier": "low", "effort_mode": "compressed"})

    result = service.generate_response(
        "default", "casual", "well? keep me entertained then",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert result != initial and result != indirect
    assert style["attentionComplianceRewriteAttempted"] is True
    assert style["attentionComplianceInitialSubreason"] == "ENTERTAINMENT_PROMISE"
    assert style["attentionComplianceSatisfied"] is True


def test_criticism_semantic_relevance_rejects_unrelated_emotional_support():
    unrelated = GPTService._foreground_semantic_relevance(
        "honestly, you're trying a little too hard",
        "ugh yeah, sounds like you earned the chance to relax 😅",
    )
    relevant = GPTService._foreground_semantic_relevance(
        "honestly, you're trying a little too hard",
        "okay, I'll dial it back a little",
    )
    assert unrelated == {
        "required": True,
        "satisfied": False,
        "intent": "CRITICISM_OR_DISMISSAL",
    }
    assert relevant["satisfied"] is True


def test_chatty_question_direct_answer_is_semantically_relevant():
    result = GPTService._foreground_semantic_relevance(
        "not much. you always this chatty?",
        "Only when I'm in a good mood. You caught me at the right time.",
    )
    assert result["required"] is True
    assert result["satisfied"] is True


def test_context_aware_semantic_fallbacks_satisfy_dismissal_contract():
    for customer in (
        "well? keep me entertained then",
        "whatever, this is getting boring",
        "honestly, you're trying a little too hard",
    ):
        fallback = GPTService._foreground_semantic_fallback(
            customer, effort_mode="compressed",
        )
        relevance = GPTService._foreground_semantic_relevance(customer, fallback)
        assert relevance["required"] is True
        assert relevance["satisfied"] is True
        assert GPTService._attention_effort_violations(
            fallback, effort_mode="compressed", style={}, user_message=customer,
        ) == []


def test_required_semantic_relevance_cannot_ship_unrelated_candidates():
    unrelated = "Sounds like you earned a chance to relax."
    service, completions = service_with(*([unrelated] * 10))
    memory = memory_none()
    context = user_memory(memory)
    context.update({"attention_tier": "low", "effort_mode": "compressed"})

    result = service.generate_response(
        "default", "casual", "whatever, this is getting boring",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert result != unrelated
    assert result == "fair enough, don't force it"
    assert style["foregroundSemanticRelevanceRequired"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["attentionPolicyEffortMode"] == "COMPRESSED"
    assert style["attentionComplianceSatisfied"] is True
    assert completions.calls <= 4


@pytest.mark.parametrize("effort", ["BALANCED", "COMPRESSED", "MINIMAL"])
def test_nested_canonical_attention_overrides_stale_gpt_alias(effort):
    service, _ = service_with("fair enough")
    memory = memory_none()
    context = user_memory(memory)
    context.update({"attention_tier": "medium", "effort_mode": "balanced"})
    context["runtime_injection"]["customer_value_attention"] = {
        "schemaVersion": "customer_value_attention_v1",
        "attentionTier": "LOW" if effort != "BALANCED" else "MEDIUM",
        "effortMode": effort,
    }

    service.generate_response(
        "default", "casual", "honestly, you're trying too hard",
        context, False, chat_history=[],
    )

    assert context["effort_mode"] == effort.lower()
    assert memory["memoryDiagnostics"]["conversationStyle"][
        "attentionPolicyEffortMode"
    ] == effort


def test_trying_too_hard_is_not_emotional_distress():
    affect = GPTService._customer_affect(
        "honestly, you're trying a little too hard"
    )
    assert affect["emotionalDisclosureDetected"] is False
    assert affect["affect"] == "NEUTRAL_OR_UNSPECIFIED"


def test_whats_up_provider_answer_satisfies_general_direct_question_contract():
    style = GPTService._style_analysis(
        "Hey! Not much, just chilling a bit. How about you?",
        "hey, what's up?", pressure={}, ordinary=True,
        memory_callback=False, new_relationship=True,
    )
    assert style["customerQuestionDetected"] is True
    assert style["customerQuestionAnswered"] is True
    assert "ANSWER_DIRECT_QUESTION" in style["satisfiedTurnObligations"]
    assert style["turnObligationsSatisfied"] is True


@pytest.mark.parametrize("mode", ["balanced", "full"])
def test_normal_and_high_attention_are_not_artificially_constrained(mode):
    response = "tell me more about your day?"
    assert GPTService._attention_effort_violations(
        response, effort_mode=mode, style={},
    ) == []


def test_authoritative_repeat_buyer_retention_context_preserves_warmth_not_spam():
    instruction = GPTService._build_retention_instruction({
        "customer_value_attention": {
            "authority": "COMMERCE_BACKED_AUTHORITATIVE_VALUE",
            "buyerStatus": "VERIFIED_BUYER",
            "buyerStage": "REPEAT_BUYER",
            "valueTier": "REPEAT_BUYER",
            "retentionLifecycle": "ACTIVE_BUYER",
            "retentionPriority": "ELEVATED",
            "relationshipInvestment": "ELEVATED",
            "memoryPriority": "HIGH",
            "salesPressure": "NORMAL",
            "offerCadence": "RESPONSIVE",
            "reactivationState": "ACTIVE_OR_COOLING",
        },
    })
    assert "Verified buyers must not sound like cold strangers" in instruction
    assert "not offer frequency" in instruction
    assert "provider-backed buyer truth is authoritative" in instruction


def test_legacy_buyer_claim_does_not_create_authoritative_retention_prompt():
    assert GPTService._build_retention_instruction({
        "is_whale": True,
        "customer_value_attention": {
            "authority": "LEGACY_COMPATIBILITY_FALLBACK",
            "valueTier": "WHALE",
        },
    }) == ""


def memory_none():
    return {"retrievedMemories": [], "memoryDiagnostics": {
        "continuityGuidance": {
            "priority": "NONE", "strongestMemory": None,
            "relevanceReasons": [], "conditionalUse": True, "maximumCallbacks": 0,
        },
    }}


def user_memory(memory, *, policy="COMMERCE_DISABLED_FOR_TURN",
                decision="CONTINUE_CONVERSATION", reason="CONVERSATION_ONLY",
                sleep=None):
    runtime = {
        "conversational_memory": memory,
        "commerce_execution_policy": policy,
        "commerce_decision": {"decision": decision, "reason_code": reason},
    }
    if sleep:
        runtime["sleep_context"] = sleep
    return {
        "runtime_injection": runtime,
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }


def active_session_position_context(memory):
    context = user_memory(
        memory, decision="CONTINUE_CONVERSATION",
        reason="RECENT_PURCHASE_COOLDOWN",
    )
    context["runtime_injection"]["commerce_decision"]["active_session_context"] = {
        "available": True,
        "completeness": "POSITIONAL_CONTEXT_COMPLETE",
        "runtimeStatus": "ACTIVE",
        "state": "CONTINUING",
        "foundationType": "PHOTOSHOOT",
        "foundationReference": "fixture-session",
        "currentConsumedPosition": 1,
        "nextEligiblePosition": 2,
        "orderedAssets": [
            {"position": 1, "owned": True},
            {"position": 2, "owned": False},
        ],
    }
    context["runtime_injection"]["commerce_decision"]["customer_commerce_memory"] = {
        "verifiedPurchaseCount": 1,
    }
    return context


@pytest.mark.parametrize("question", (
    "where were we?", "where did we leave off?", "what part were we on?",
    "what's left?",
))
def test_active_session_position_question_uses_grounded_semantic_slot(question):
    memory = memory_none()
    commerce = active_session_position_context(memory)["runtime_injection"][
        "commerce_decision"
    ]
    result = GPTService._foreground_semantic_relevance(
        question,
        "you already finished the first part, so the second part is where we'd pick back up",
        commerce,
    )
    assert result["intent"] == "SESSION_POSITION"
    assert result["satisfied"] is True


@pytest.mark.parametrize("candidate", (
    "I don't remember, where were we?",
    "we're on the third part",
    "let me show you a different content set instead",
    "",
))
def test_active_session_position_rejects_invalid_candidate_and_fallback_revalidates(
        candidate):
    memory = memory_none()
    commerce = active_session_position_context(memory)["runtime_injection"][
        "commerce_decision"
    ]
    rejected = GPTService._foreground_semantic_relevance(
        "where were we?", candidate, commerce,
    )
    fallback = GPTService._foreground_semantic_fallback(
        "where were we?", effort_mode="BALANCED", commerce_decision=commerce,
    )
    accepted = GPTService._foreground_semantic_relevance(
        "where were we?", fallback, commerce,
    )
    assert rejected["satisfied"] is False
    assert accepted["satisfied"] is True
    assert "$" not in fallback
    assert "offer" not in fallback.lower()


def test_session_position_fallback_is_not_used_without_complete_active_authority():
    ordinary = {"decision": "CONTINUE_CONVERSATION"}
    result = GPTService._foreground_semantic_relevance(
        "where were we?", "fair enough", ordinary,
    )
    assert result["required"] is False
    assert result.get("intent") != "SESSION_POSITION"


def test_empty_session_position_provider_output_gets_revalidated_grounded_fallback():
    service, _ = service_with(*([""] * 8))
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "where were we?",
        active_session_position_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == (
        "you already finished the first part, so the second part is where we'd pick back up"
    )
    assert style["customerQuestionSemanticSlot"] == "SESSION_POSITION"
    assert style["customerQuestionAnswered"] is True
    assert style["foregroundSemanticIntent"] == "SESSION_POSITION"
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["providerReturnedUsableText"] is False
    assert style["groundedSessionPositionFallbackUsed"] is True


@pytest.mark.parametrize("question", (
    "what's the next step?", "what is the next part?", "what do we do next?",
    "what comes next?", "what's next?",
))
def test_active_session_next_step_has_distinct_grounded_semantic_slot(question):
    memory = memory_none()
    commerce = active_session_position_context(memory)["runtime_injection"][
        "commerce_decision"
    ]
    result = GPTService._foreground_semantic_relevance(
        question, "the second part is next", commerce,
    )
    assert result["intent"] == "NEXT_SESSION_STEP"
    assert result["satisfied"] is True


@pytest.mark.parametrize("invalid", (
    "I don't know, what do you want to do?",
    "the third part is next",
    "I have another standalone set",
    "the second part is $9",
    "unlock the second part",
    "",
))
def test_next_session_step_invalid_provider_output_uses_bounded_fallback(invalid):
    service, _ = service_with(*([invalid] * 8))
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "what's the next step?",
        active_session_position_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "the second part is next"
    assert style["customerQuestionSemanticSlot"] == "NEXT_SESSION_STEP"
    assert style["foregroundSemanticIntent"] == "NEXT_SESSION_STEP"
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["groundedNextSessionStepFallbackUsed"] is True
    assert style["customerMemoryMutationAllowed"] is False
    if invalid:
        assert style["providerCandidateSemanticValidity"]
        assert not any(style["providerCandidateSemanticValidity"])
    else:
        assert style["providerCandidateSemanticValidity"] == []
        assert style["providerReturnedUsableText"] is False


def test_next_session_step_requires_complete_active_authority():
    result = GPTService._foreground_semantic_relevance(
        "what's the next step?", "the second part is next",
        {"active_session_context": {"available": False}},
    )
    assert result["required"] is False
    assert result.get("intent") != "NEXT_SESSION_STEP"


def test_next_session_step_does_not_use_terminal_session_authority():
    memory = memory_none()
    commerce = active_session_position_context(memory)["runtime_injection"][
        "commerce_decision"
    ]
    commerce["active_session_context"]["state"] = "COMPLETED"
    result = GPTService._foreground_semantic_relevance(
        "what's the next step?", "the second part is next", commerce,
    )
    assert result["required"] is False
    assert result.get("intent") != "NEXT_SESSION_STEP"


@pytest.mark.parametrize("invalid", (
    "I don't remember, where were we?",
    "we're on the third part",
    "let me show you a different content set instead",
))
def test_invalid_session_position_provider_output_gets_grounded_fallback(invalid):
    service, _ = service_with(*([invalid] * 8))
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "where were we?",
        active_session_position_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == (
        "you already finished the first part, so the second part is where we'd pick back up"
    )
    assert style["providerCandidateSemanticValidity"]
    assert not any(style["providerCandidateSemanticValidity"])
    assert style["groundedSessionPositionFallbackUsed"] is True


def test_c14_turn_four_failed_provider_candidate_is_blocked_before_commit():
    failed = "mm, keep talking like that... you still haven't seen my dangerous side"
    service, completions = service_with(failed, failed, failed)
    memory = memory_none()

    response = service.generate_response(
        "default", "casual", "work has been taking most of my attention",
        user_memory(memory), False,
        chat_history=[
            {"role": "user", "content": "hey, just checking in"},
            {"role": "assistant", "content": "hey, good to hear from you"},
            {"role": "user", "content": "I've been keeping busy lately"},
            {"role": "assistant", "content": "yeah, sounds like a full week"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == "sounds like you've had a lot keeping you busy"
    assert "dangerous side" not in response
    assert completions.calls >= 2
    assert style["foregroundSemanticRelevanceRequired"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["customerDisclosureDomain"] == "WORK_BUSYNESS"
    assert style["flirtOrSexualInboundSignal"] is False
    assert style["responseFlirtEscalationDetected"] is False
    assert style["responseFlirtEscalationAuthorized"] is False


def curiosity_only_context(memory, *, decision="BUILD_INTEREST"):
    context = user_memory(
        memory, decision=decision, reason="BUILD_INTEREST",
    )
    commerce = context["runtime_injection"]["commerce_decision"]
    commerce.update({
        "customer_value_attention": {
            "commercialInterestType": "COMMERCIAL_CURIOSITY",
        },
        "commercial_receptiveness": {
            "commercialInterestType": "COMMERCIAL_CURIOSITY",
            "freshDirectIntentDetected": False,
        },
        "contextual_customer_tone": {"buyingIntent": False},
        "active_buying_window": {"active": False},
        "sales_progression": {"phase": decision},
    })
    return context


@pytest.mark.parametrize("response", (
    "you're definitely getting closer",
    "I can tell you're ready for it",
    "I know you want it",
    "you're about to give in",
    "you're finally coming around",
    "you've earned the next step",
))
def test_curiosity_truth_guard_rejects_semantic_customer_progression(response):
    assert GPTService._customer_commercial_state_overstatement_reasons(response)


def test_curiosity_only_generation_repairs_false_customer_buying_progression():
    service, completions = service_with(
        "Maybe I should keep a little mystery, but you're definitely getting closer.",
        "mm maybe just a little more... can't give away all the fun yet",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "flirty", "okay, I'm curious... tell me a little more",
        curiosity_only_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert completions.calls == 2
    assert result == "mm maybe just a little more... can't give away all the fun yet"
    assert not GPTService._customer_commercial_state_overstatement_reasons(result)
    assert "DO_NOT_OVERSTATE_CUSTOMER_COMMERCIAL_STATE" in style[
        "satisfiedTurnObligations"
    ]
    assert style["customerCommercialStateTruthRequired"] is True
    assert style["customerCommercialStateOverstatementReasons"] == []
    assert "$" not in result and "unlock" not in result.lower()


def test_build_interest_curiosity_fallback_varies_against_recent_response():
    first = GPTService._curiosity_response_fallback(())
    second = GPTService._curiosity_response_fallback((first,))

    assert first != second
    assert not GPTService._customer_commercial_state_overstatement_reasons(first)
    assert not GPTService._customer_commercial_state_overstatement_reasons(second)


class CanonicalPersona(SimpleNamespace):
    def prompt_block(self):
        return "Canonical Ava is outdoors-oriented."


@pytest.mark.parametrize("text", [
    "I hear you.", "gotcha", "fair enough", "lol yeah", "I know what you mean",
])
def test_generic_acknowledgements_are_not_self_disclosure(text):
    style = GPTService._style_analysis(
        text, "hey", pressure={}, ordinary=True, memory_callback=False,
        new_relationship=True,
    )
    assert style["selfDisclosureUsed"] is False
    assert style["meaningfulContribution"] is False


def test_exact_c01_draft_gets_one_bounded_obligation_rewrite():
    service, completions = service_with(
        "I hear you.",
        "aww that's sweet 😊 my day's been pretty chill honestly",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual",
        "Hey 😊 you seem really sweet. How’s your day been?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "I hear you."
    assert completions.calls == 2
    assert style["newRelationship"] is True
    assert style["welcomeRequired"] is True
    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionDetected"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["meaningfulContribution"] is True
    assert style["selfDisclosureUsed"] is True
    assert style["styleRewriteAttempted"] is True


def test_exclamation_greeting_direct_answer_is_preserved_as_compliant():
    draft = "Hey! It's going pretty well, thanks for asking. How about you?"
    service, completions = service_with(draft, "I hear you")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "hey, how's it going?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == draft
    assert completions.calls == 2
    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["genericFillerRisk"] is False
    assert style["styleRewriteOutcome"] == "REJECTED_OBLIGATION_LOSS_ORIGINAL_PRESERVED"


def test_final_contract_fallback_answers_first_contact_question():
    service, _ = service_with("I hear you", "I hear you", "I hear you")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "hey, how's it going?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "I hear you"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_best_safe_candidate_survives_multiple_inferior_rewrites_and_fallback():
    first = "Hey! It\u2019s going pretty well, thanks. How about you?"
    service, _ = service_with(
        first,
        "Hey, it\u2019s going pretty good—how about you?",
        "Hey! I\u2019m doing good, thanks for asking.",
        "Hey! I\u2019m doing pretty well, thanks. How about you?",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "hey, how's it going?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "hey, really nice to hear from you 😊"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["bestSafeCandidatePreserved"] is True
    assert style["bestSafeCandidateSource"].startswith("PROVIDER_CANDIDATE_")


def test_best_safe_candidate_preserves_criticism_relevance_over_support_fallback():
    relevant = (
        "okay, fair enough, I'll dial it back a little because I can see I'm "
        "doing too much here and there's no need to keep pushing the conversation"
    )
    unrelated = "ugh yeah, sounds like you earned the chance to relax 😅"
    service, _ = service_with(relevant, unrelated, unrelated, unrelated, unrelated)
    memory = memory_none()

    result = service.generate_response(
        "default", "casual", "honestly, you're trying a little too hard",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert result == relevant
    assert style["foregroundSemanticIntent"] == "CRITICISM_OR_DISMISSAL"
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["bestSafeCandidatePreserved"] is True


def test_compressed_generation_rewrites_volunteered_entertainment_labor():
    service, _ = service_with(
        "Alright, challenge accepted—let's see if I can surprise you a little.",
        "fair enough, no need to impress you",
    )
    memory = memory_none()
    context = user_memory(memory)
    context["effort_mode"] = "compressed"
    context["attention_tier"] = "low"
    context["runtime_injection"]["customer_value_attention"] = {
        "effortMode": "COMPRESSED",
        "attentionTier": "LOW",
        "buyerStatus": "NONBUYER",
    }

    result = service.generate_response(
        "default", "casual", "well? keep me entertained then",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert "challenge accepted" not in result.lower()
    assert "surprise you" not in result.lower()
    assert style["attentionComplianceSatisfied"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True


@pytest.mark.parametrize(("message", "response", "new_relationship", "intensity", "expected", "satisfied"), (
    ("Hey 😊 just found you and wanted to say hi.", "hey, really nice to hear from you 😊", True, "WARM", True, True),
    ("hey", "hey", True, "NEUTRAL", True, True),
    ("omg hi you're gorgeous 😍", "okayyy hi, you're sweet 😏", True, "ENTHUSIASTIC", True, True),
    ("Hey, I want to buy something.", "hey, I can show you what I've got", True, "NEUTRAL", True, True),
    ("hey again", "hey", False, "NEUTRAL", False, None),
    ("hey", "good to see you again", False, "NEUTRAL", False, None),
    ("hey, you suck", "what do you want", True, "HOSTILE", False, None),
    ("hey, I'm horny", "you're feeling bold", True, "SEXUAL", False, None),
    ("Hey 😊 how are you?", "aww hey, doing pretty good so far 😊", True, "WARM", True, True),
))
def test_new_prospect_warmth_matrix(message, response, new_relationship,
                                    intensity, expected, satisfied):
    style = GPTService._style_analysis(
        response, message, pressure={}, ordinary=True, memory_callback=False,
        new_relationship=new_relationship,
    )
    assert style["newProspectApproachIntensity"] == intensity
    assert style["newProspectWarmthExpected"] is expected
    assert style["newProspectWarmthSatisfied"] is satisfied


def test_exact_temporal_mismatch_and_warm_first_contact_combined_contract():
    service, completions = service_with(
        "my day's been pretty chill honestly",
        "my day's been pretty chill honestly",
    )
    memory = memory_none()
    projected = user_memory(memory)
    projected["runtime_injection"]["time_context"] = {
        "runtimeUtc": "2026-08-29T17:23:12+00:00",
        "avaTimezone": "America/New_York",
        "avaLocalTime": "2026-08-29T13:23:12-04:00",
        "avaDayOfWeek": "Saturday",
        "avaDaypart": "afternoon",
        "customerTimezone": None,
        "customerLocalTime": None,
        "customerDayOfWeek": None,
        "customerDaypart": None,
    }
    result = service.generate_response(
        "default", "casual",
        "Hey 😊 just stumbled across you and figured I'd say hi. How's your night going?",
        projected, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "my day's been pretty chill honestly"
    assert completions.calls == 2
    assert style["newRelationship"] is True
    assert style["welcomeRequired"] is True
    assert style["welcomeSatisfied"] is True
    assert style["newProspectWarmthExpected"] is True
    assert style["newProspectWarmthSatisfied"] is True
    assert style["responseWarmthLevel"] in {"WARM", "PLAYFUL"}
    assert style["customerQuestionAnswered"] is True
    assert style["customerTemporalReferenceDetected"] is True
    assert style["customerTemporalReferenceTarget"] == "AVA"
    assert style["customerAssumedAvaDaypart"] == "NIGHT"
    assert style["canonicalAvaDaypart"] == "AFTERNOON"
    assert style["temporalMismatchDetected"] is True
    assert style["responseTemporalAlignmentSatisfied"] is True
    assert style["manufacturedQuestionRisk"] is False
    assert "?" not in result


def test_temporal_only_rewrite_reports_success_only_after_alignment():
    service, completions = service_with(
        "my night's been great", "doing pretty good so far",
    )
    memory = memory_none()
    projected = user_memory(memory)
    projected["runtime_injection"]["time_context"] = {
        "avaTimezone": "America/New_York",
        "avaLocalTime": "2026-08-29T13:23:12-04:00",
        "avaDaypart": "afternoon", "customerTimezone": None,
    }
    result = service.generate_response(
        "default", "casual", "How's your night going?", projected, False,
        chat_history=[{"role": "user", "content": "we've talked before"}],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "doing pretty good so far"
    assert completions.calls == 2
    assert style["temporalRewriteAttempted"] is True
    assert style["temporalRewriteOutcome"] == "SUCCEEDED"
    assert style["responseTemporalAlignmentSatisfied"] is True
    assert style["customerQuestionAnswered"] is True


def test_noncompliant_temporal_rewrite_uses_safe_answering_fallback():
    service, completions = service_with(
        "my night's been great", "my night's still great",
    )
    memory = memory_none()
    projected = user_memory(memory)
    projected["runtime_injection"]["time_context"] = {
        "avaTimezone": "America/New_York",
        "avaLocalTime": "2026-08-29T13:23:12-04:00",
        "avaDaypart": "afternoon", "customerTimezone": None,
    }
    result = service.generate_response(
        "default", "casual", "How's your night going?", projected, False,
        chat_history=[{"role": "user", "content": "we've talked before"}],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "doing pretty good so far"
    assert completions.calls == 2
    assert style["temporalRewriteOutcome"] == "NONCOMPLIANT_REWRITE_SAFE_COMBINED_FALLBACK"
    assert style["responseTemporalAlignmentSatisfied"] is True
    assert style["customerQuestionAnswered"] is True


def test_exact_c01_turn_two_aligns_with_rough_day_and_treats_lol_as_tone():
    service, completions = service_with(
        "I hear you.", "I hear you.",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        user_memory(memory), False,
        chat_history=[
            {"role": "user", "content": "Hey 😊 you seem really sweet. How’s your day been?"},
            {"role": "assistant", "content": "aww thank you, my day's been pretty chill honestly 😊"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result not in {"I hear you.", "lol okay, I like your energy 😂"}
    assert style["newRelationship"] is False
    assert style["customerAffect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert style["emotionalDisclosureDetected"] is True
    assert style["emotionalAlignmentSatisfied"] is True
    assert style["lolClassification"] == "TONE_SOFTENER"
    assert "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in style["turnObligations"]
    assert "RESPOND_TO_JOKE" not in style["turnObligations"]
    assert style["turnObligationsSatisfied"] is True
    assert style["styleRewriteAttempted"] is True
    assert "?" not in result


@pytest.mark.parametrize(("message", "affect", "energy", "transition", "relief", "disclosure"), [
    ("Work wore me out today, finally getting to relax.", "MILD_NEGATIVE_WITH_RELIEF", "TIRED", "RESOLVING", "CLEAR", True),
    ("Work was brutal lol, glad I'm home.", "MILD_NEGATIVE_WITH_RELIEF", "NORMAL", "RESOLVING", "CLEAR", True),
    ("I'm exhausted but finally done.", "MILD_NEGATIVE_WITH_RELIEF", "TIRED", "RESOLVING", "CLEAR", True),
    ("Long day 😅 I'm just happy to be on the couch.", "MILD_NEGATIVE_WITH_RELIEF", "TIRED", "RESOLVING", "CLEAR", True),
    ("Today kicked my ass 😂 but I'm good now.", "MILD_NEGATIVE_WITH_RELIEF", "TIRED", "RESOLVING", "CLEAR", True),
    ("Work drained me.", "NEGATIVE_OR_TIRED", "TIRED", "UNSPECIFIED", "NONE", True),
    ("I'm tired.", "NEGATIVE_OR_TIRED", "TIRED", "UNSPECIFIED", "NONE", True),
    ("I'm finally relaxing.", "RELIEVED", "NORMAL", "RESOLVING", "CLEAR", True),
    ("Work was fine, just got home.", "NEUTRAL_OR_UNSPECIFIED", "NORMAL", "RESOLVING", "NONE", False),
    ("Had a great day at work and I'm feeling good.", "POSITIVE", "NORMAL", "UNSPECIFIED", "NONE", False),
    ("lol work", "NEUTRAL_OR_UNSPECIFIED", "NORMAL", "UNSPECIFIED", "NONE", False),
    ("I'm annoyed because I'm still stuck at work.", "NEGATIVE_OR_TIRED", "NORMAL", "ONGOING", "NONE", True),
])
def test_customer_affect_semantically_composes_state_energy_transition_and_relief(
    message, affect, energy, transition, relief, disclosure,
):
    result = GPTService._customer_affect(message)
    assert result["affect"] == affect
    assert result["energy"] == energy
    assert result["transition"] == transition
    assert result["reliefLevel"] == relief
    assert result["emotionalDisclosureDetected"] is disclosure


@pytest.mark.parametrize("softener", ["lol", "😂", "😅", "haha", ""])
def test_tone_softener_does_not_erase_tiredness_and_relief(softener):
    result = GPTService._customer_affect(
        f"Work wore me out today {softener}, finally getting a chance to relax."
    )
    assert result["affect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert result["energy"] == "TIRED"
    assert result["reliefLevel"] == "CLEAR"
    assert result["emotionalDisclosureDetected"] is True
    if softener:
        assert result["lolClassification"] == "TONE_SOFTENER"


def test_exact_attempt_eight_turn_two_repairs_affect_and_truthful_contribution():
    inbound = (
        "Not bad over here either. Work wore me out today though 😅 "
        "finally getting a chance to relax."
    )
    service, completions = service_with("lol okay, I can see that", "lol okay, I can see that")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", inbound, user_memory(memory), False,
        chat_history=[
            {"role": "user", "content": "Hey 😊 just stumbled across you and figured I'd say hi. How's your night going?"},
            {"role": "assistant", "content": "aww hey, I'm doing pretty good so far 😊"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "ugh yeah, sounds like you earned the chance to relax 😅"
    assert completions.calls == 2
    assert style["customerAffect"] == "MILD_NEGATIVE_WITH_RELIEF"
    assert style["customerAffectEnergy"] == "TIRED"
    assert style["customerAffectTransition"] == "RESOLVING"
    assert style["customerReliefLevel"] == "CLEAR"
    assert style["emotionalDisclosureDetected"] is True
    assert style["emotionalAlignmentSatisfied"] is True
    assert "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in style["satisfiedTurnObligations"]
    assert style["contributionType"] == "RELIEF_ACKNOWLEDGEMENT"
    assert style["genericFillerRisk"] is False
    assert "?" not in result


def test_exact_c01_turn_three_reciprocates_light_social_flirt():
    service, completions = service_with("I hear you.", "I hear you.")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual",
        "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl 😂",
        user_memory(memory), False,
        chat_history=[
            {"role": "user", "content": "Yeah work was kinda brutal today lol. Just glad to finally be home."},
            {"role": "assistant", "content": "ugh, at least you're finally home now"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "I hear you."
    assert style["socialFlirtationDetected"] is True
    assert style["socialFlirtationStrength"] == "LIGHT"
    assert style["flirtResponseExpected"] is True
    assert style["flirtResponseSatisfied"] is True
    assert "ACKNOWLEDGE_FLIRTATION" in style["satisfiedTurnObligations"]
    assert style["contributionType"] == "FLIRT_RECIPROCATION"
    assert style["meaningfulContribution"] is True
    assert style["genericFillerRisk"] is False
    assert style["styleRewriteOutcome"] == "NONCOMPLIANT_REWRITE_SAFE_OBLIGATION_FALLBACK"
    assert "?" not in result


def test_explicit_sexual_energy_creates_a_binding_non_generic_obligation():
    mismatch = GPTService._style_analysis(
        "fair enough", "I'm so horny for you right now",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert mismatch["sexualEngagementDetected"] is True
    assert mismatch["sexualResponseExpected"] is True
    assert mismatch["sexualResponseSatisfied"] is False
    assert "ACKNOWLEDGE_SEXUAL_ENERGY" in mismatch["unsatisfiedTurnObligations"]

    compliant = GPTService._style_analysis(
        "careful, you're trouble when you're this bold 😏",
        "I'm so horny for you right now",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert compliant["sexualResponseSatisfied"] is True
    assert "ACKNOWLEDGE_SEXUAL_ENERGY" in compliant["satisfiedTurnObligations"]


def test_naughty_thoughts_use_one_binding_sexual_foreground_contract():
    inbound = "you're making it hard to behave, naughty thoughts about you keep taking over"
    style = GPTService._style_analysis(
        "fair enough", inbound,
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["sexualEngagementDetected"] is True
    assert style["sexualResponseExpected"] is True
    assert style["sexualResponseSatisfied"] is False
    assert style["flirtResponseExpected"] is False
    assert "ACKNOWLEDGE_SEXUAL_ENERGY" in style["turnObligations"]
    assert "ACKNOWLEDGE_FLIRTATION" not in style["turnObligations"]
    assert style["genericFillerRisk"] is True


def test_naughty_thoughts_generic_provider_candidates_cannot_ship():
    service, _ = service_with("fair enough", "fair enough")
    memory = memory_none()
    result = service.generate_response(
        "default", "flirty",
        "you're making it hard to behave, naughty thoughts about you keep taking over",
        user_memory(memory), False,
        chat_history=[
            {"role": "assistant", "content": "fair enough"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "fair enough"
    assert style["sexualResponseExpected"] is True
    assert style["sexualResponseSatisfied"] is True
    assert style["flirtResponseExpected"] is False
    assert style["genericFillerRisk"] is False
    assert "ACKNOWLEDGE_SEXUAL_ENERGY" in style["satisfiedTurnObligations"]


def test_repeated_sexual_tease_fallback_is_replaced_at_final_delivery_gate():
    repeated = "careful, you haven't seen trouble yet"
    service, _ = service_with(repeated, repeated, repeated)
    memory = memory_none()
    memory["recentAvaResponses"] = [repeated]
    context = user_memory(
        memory, decision="TEASE", reason="TEASE_RELEVANT_OPPORTUNITY",
    )
    context["runtime_injection"]["commerce_decision"]["proactive_progression"] = {
        "proactiveProgressionAuthorized": True,
        "progressionAction": "TEASE",
    }

    result = service.generate_response(
        "default", "flirty",
        "you're making it hard to behave, my thoughts about you are getting dirty",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert result != repeated
    assert style["repetitionRepairAttempted"] is True
    assert style["repetitionRepairOutcome"] == "COMPLIANT_ALTERNATE_SELECTED"
    assert style["finalResponseRepetitionSatisfied"] is True
    assert style["sexualResponseSatisfied"] is True
    assert style["proactiveTeaseSatisfied"] is True
    assert "$" not in result


def test_exact_low_information_reuse_is_detected_across_short_window():
    style = GPTService._style_analysis(
        "fair enough", "okay",
        pressure={}, ordinary=True, memory_callback=False,
        recent_responses=[
            "hey", "tell me more", "sounds good", "cute", "fair enough",
        ],
    )
    assert style["genericFillerRisk"] is True
    assert style["recentPhraseRepetitionRisk"] is True


def test_exact_c01_turn_four_acknowledges_customer_social_style_disclosure():
    inbound = (
        "Haha maybe a little 😂 I’m usually pretty quiet at first though. "
        "Takes me a minute to warm up to somebody."
    )
    service, completions = service_with("I hear you.", "I hear you.")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", inbound, user_memory(memory), False,
        chat_history=[
            {"role": "user", "content": "Honestly this is kinda nice though. Just laying on the couch, talking to a cute girl 😂"},
            {"role": "assistant", "content": "well then, you're kinda sweet 😂"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "I hear you."
    assert completions.calls == 2
    assert style["customerSelfDisclosureDetected"] is True
    assert style["customerSelfDisclosureDomain"] == "PERSONALITY_SOCIAL_STYLE"
    assert style["customerSelfDisclosureSignificance"] == "DURABLE"
    assert style["customerSelfDisclosureResponseExpected"] is True
    assert style["customerSelfDisclosureResponseSatisfied"] is True
    assert "ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in style["satisfiedTurnObligations"]
    assert style["contributionType"] == "CUSTOMER_DISCLOSURE_ACKNOWLEDGEMENT"
    assert style["meaningfulContribution"] is True
    assert style["genericFillerRisk"] is False
    assert style["styleRewriteOutcome"] == "NONCOMPLIANT_REWRITE_SAFE_OBLIGATION_FALLBACK"
    assert "?" not in result


@pytest.mark.parametrize("message,detected,domain,significance,persist", [
    ("I'm usually pretty quiet at first.", True, "PERSONALITY_SOCIAL_STYLE", "DURABLE", True),
    ("Takes me a while to warm up to people.", True, "PERSONALITY_SOCIAL_STYLE", "DURABLE", True),
    ("I'm actually really outgoing once I know someone.", True, "PERSONALITY_SOCIAL_STYLE", "DURABLE", True),
    ("I love hiking.", True, "HOBBY_INTEREST", "DURABLE", True),
    ("I have a golden retriever named Charlie.", True, "PERSONAL_CONTEXT", "DURABLE", True),
    ("Foo Fighters are probably my favorite band.", True, "MUSIC", "DURABLE", True),
    ("I'm just drinking water.", True, "EPHEMERAL_ACTIVITY", "LOW", False),
    ("I'm sitting on the couch.", True, "EPHEMERAL_ACTIVITY", "LOW", False),
    ("I work late most nights.", True, "ROUTINE", "DURABLE", True),
    ("I hate camping.", True, "PREFERENCE", "DURABLE", True),
])
def test_customer_self_disclosure_significance_matrix(
    message, detected, domain, significance, persist,
):
    disclosure = ConversationalMemoryService.classify_customer_self_disclosure(message)
    records = ConversationalMemoryService.extract_records(message)
    style = GPTService._style_analysis(
        "I hear you.", message, pressure={}, ordinary=True, memory_callback=False,
    )
    assert disclosure["detected"] is detected
    assert disclosure["domain"] == domain
    assert disclosure["significance"] == significance
    assert bool(records) is persist
    assert ("ACKNOWLEDGE_CUSTOMER_SELF_DISCLOSURE" in style["turnObligations"]) is (
        detected and significance != "LOW"
    )


def test_exact_c01_turn_five_uses_authorized_outdoors_common_ground():
    inbound = (
        "I'm kinda an outdoors person once I actually get off the couch 😂 "
        "hiking, camping, stuff like that."
    )
    service, completions = service_with("I hear you.", "I hear you.")
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["ava_persona_runtime_projection"] = CanonicalPersona(
        stable_public=("outdoors-oriented",),
        selected_persona_facts=(), selected_lifestyle_facts=(),
        relevance_domains=("outdoors", "home"),
    )
    result = service.generate_response(
        "default", "casual", inbound, context, False, chat_history=[
            {"role": "assistant", "content": "doesn't seem like it's taking you too long with me 😂"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result != "I hear you."
    assert completions.calls == 2
    assert style["customerSelfDisclosureDetected"] is True
    assert style["customerSelfDisclosureDomain"] == "HOBBY_INTEREST"
    assert set(style["customerSelfDisclosureEvidence"]) >= {
        "OUTDOORS_INTEREST", "HIKING_INTEREST", "CAMPING_INTEREST",
    }
    assert style["customerSelfDisclosureResponseSatisfied"] is True
    assert style["sharedInterestDetected"] is True
    assert style["sharedInterestDomain"] == "OUTDOORS"
    assert style["sharedInterestClaimAuthorized"] is True
    assert style["sharedInterestUsedInResponse"] is True
    assert style["genericFillerRisk"] is False
    assert style["meaningfulContribution"] is True
    assert "?" not in result


@pytest.mark.parametrize("message,stable_public,domains,expected", [
    ("I love hiking.", ("outdoors-oriented",), ("outdoors",), True),
    ("I love camping.", ("outdoors-oriented",), ("outdoors",), True),
    ("Foo Fighters are my favorite band.", ("outdoors-oriented",), ("home",), False),
    ("I have a dog named Charlie.", ("outdoors-oriented",), ("ordinary",), False),
    ("I restore old tractors.", ("outdoors-oriented",), ("ordinary",), False),
])
def test_common_ground_requires_canonical_persona_authority(
    message, stable_public, domains, expected,
):
    disclosure = ConversationalMemoryService.classify_customer_self_disclosure(message)
    persona = CanonicalPersona(
        stable_public=stable_public, selected_persona_facts=(),
        selected_lifestyle_facts=(), relevance_domains=domains,
    )
    result = GPTService._shared_interest(disclosure, persona)
    assert result["detected"] is expected
    assert result["claimAuthorized"] is expected
    assert (result["source"] == "ACTIVE_ACCOUNT_SCOPED_CREATOR_PROFILE") is expected


@pytest.mark.parametrize("message,domain,values,persist", [
    ("I love hiking.", "HOBBY_INTEREST", {"hiking"}, True),
    ("Camping is probably my favorite thing.", "HOBBY_INTEREST", {"camping"}, True),
    ("I'm really into hiking and camping.", "HOBBY_INTEREST", {"hiking", "camping"}, True),
    ("I'm big into hiking and camping whenever I can get away.", "HOBBY_INTEREST", {"hiking", "camping"}, True),
    ("Foo Fighters are probably my favorite band.", "MUSIC", {"Foo Fighters"}, True),
    ("I play guitar.", "HOBBY_INTEREST", {"guitar"}, True),
    ("I love fishing.", "HOBBY_INTEREST", {"fishing"}, True),
    ("I hate camping.", "PREFERENCE", {"dislikes camping"}, True),
    ("I have a golden retriever named Charlie.", "PERSONAL_CONTEXT", {"Charlie"}, True),
    ("I'm drinking water.", "EPHEMERAL_ACTIVITY", set(), False),
    ("I'm sitting on the couch.", "EPHEMERAL_ACTIVITY", set(), False),
])
def test_hobby_interest_memory_matrix(message, domain, values, persist):
    disclosure = ConversationalMemoryService.classify_customer_self_disclosure(message)
    records = ConversationalMemoryService.extract_records(message)
    assert disclosure["detected"] is True
    assert disclosure["domain"] == domain
    assert disclosure["significance"] == ("DURABLE" if persist else "LOW")
    assert bool(records) is persist
    actual = {str(record["value"]) for record in records}
    assert values <= actual


@pytest.mark.parametrize("message,flirt,sexual,commercial", [
    ("you're cute", True, False, False),
    ("I kinda like talking to you", True, False, False),
    ("laying here talking to a cute girl is pretty nice", True, False, False),
    ("you seem really sweet", False, False, False),
    ("okay you're trouble 😂", True, False, False),
    ("you're making it hard to behave", True, False, False),
    ("your hiking picture is really pretty", False, False, False),
    ("I'm horny tonight", False, True, False),
    ("what do you have I can buy?", False, False, True),
    ("I'm horny, show me something sexy I can buy", False, True, True),
])
def test_social_flirtation_axis_is_separate_from_sex_and_commerce(
    message, flirt, sexual, commercial,
):
    result = GPTService._social_flirtation(message)
    assert result["detected"] is flirt
    assert result["sexual"] is sexual
    assert result["commercial"] is commercial


COFFEE = "I'm just having a lazy morning with some coffee. How's your day going?"


def test_coffee_turn_rewrites_polished_paraphrase_to_short_phone_answer():
    service, completions = service_with(
        "Lazy mornings with coffee are pretty unbeatable. My day is good so far. What's your coffee of choice?",
        "pretty chill so far, still moving slow lol",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", COFFEE, user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "pretty chill so far, still moving slow lol"
    assert completions.calls == 2
    assert style["mode"] == "PHONE_TEXTING"
    assert style["styleRewriteAttempted"] is True
    assert style["styleRewriteOutcome"] == "SUCCEEDED"
    assert style["questionAsked"] is False
    prompt = completions.messages[0][0]["content"]
    assert "ONE COMPLETE BEAT BY DEFAULT" in prompt
    assert "Do not merely paraphrase" in prompt
    assert "Questions are optional" in prompt


def test_recent_question_pressure_rewrites_another_mechanical_question():
    history = [
        {"role": "assistant", "content": "what are you doing later?"},
        {"role": "user", "content": "not much"},
        {"role": "assistant", "content": "anything fun planned?"},
        {"role": "user", "content": "probably relaxing"},
        {"role": "assistant", "content": "watching anything good?"},
    ]
    service, completions = service_with(
        "That sounds relaxing. What are you watching?",
        "lol honestly doing nothing sounds kinda perfect",
    )
    memory = memory_none()
    service.generate_response(
        "default", "casual", "I'm just staying in.", user_memory(memory),
        False, chat_history=history,
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert style["recentQuestionCount"] == 3
    assert style["questionStreak"] == 3
    assert style["questionAsked"] is False
    assert completions.calls == 2


def test_outbound_only_scenario_history_drives_truthful_question_pressure():
    service, completions = service_with(
        "Charlie sounds fun. Where do you usually hike?",
        "Charlie sounds fun. Favorite trail?",
        "hiking weekends are absolutely my kind of reset",
    )
    memory = memory_none()
    memory["recentAvaResponses"] = [
        "How about you?", "What keeps you in Chicago?", "Where do you wander?",
    ]
    result = service.generate_response(
        "default", "casual", "I'm more of a hiking and camping person.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "hiking weekends are absolutely my kind of reset"
    assert style["recentQuestionCount"] == 3
    assert style["recentQuestionWindow"] == 3
    assert style["questionStreak"] == 3
    assert style["questionAsked"] is False
    assert completions.calls == 3


def test_direct_customer_question_allows_natural_question_without_rewrite():
    service, completions = service_with("pretty chill so far. you doing okay?")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "How's your morning going?", user_memory(memory),
        False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 1
    assert style["questionAsked"] is True
    assert style["questionReason"] == "DIRECT_RECIPROCAL_CURIOSITY"
    assert style["questionValue"] == "MEDIUM"
    assert style["customerQuestionAnswered"] is True


def test_turn7_style_manufactured_question_violates_final_response_contract():
    style = GPTService._style_analysis(
        "what's the secret to keeping you hooked this long?",
        "You're really easy to talk to and I like chatting with you.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["manufacturedQuestionRisk"] is True
    assert style["questionValue"] == "LOW"
    assert style["turnObligationsSatisfied"] is False
    assert GPTService._violates_final_response_contract(style) is True


def test_meaningful_natural_question_does_not_violate_final_response_contract():
    style = GPTService._style_analysis(
        "aww thank you, that's sweet of you. what trail do you keep going back to?",
        "You're sweet. I could talk about hiking forever.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert GPTService._violates_final_response_contract(style) is False


def test_actual_final_flirt_and_disclosure_responses_satisfy_obligations():
    flirt = GPTService._style_analysis(
        "Well, you're making this couch moment a whole lot sweeter.",
        "This is nice, talking with a cute girl.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    disclosure = GPTService._style_analysis(
        "Love that—getting outside always feels like hitting reset.",
        "I'm kinda an outdoors person—hiking and camping mostly.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert flirt["flirtResponseSatisfied"] is True
    assert flirt["turnObligationsSatisfied"] is True
    assert disclosure["customerSelfDisclosureResponseSatisfied"] is True
    assert disclosure["turnObligationsSatisfied"] is True


def test_exact_coffee_manufactured_question_is_rewritten_to_answer_and_contribution():
    service, completions = service_with(
        "What kind of coffee is helping make your morning lazy?",
        "pretty slow over here too, still convincing myself to get moving lol",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", COFFEE, user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result.startswith("pretty slow over here")
    assert completions.calls == 2
    assert style["customerAskedQuestion"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["manufacturedQuestionRisk"] is False
    assert style["questionValue"] == "NONE"
    assert style["questionReason"] == "NONE"
    assert style["contributionType"] == "DIRECT_ANSWER"
    assert style["styleRewriteAttempted"] is True
    assert "CUSTOMER_QUESTION_UNANSWERED" in style["styleRewriteTriggers"]
    assert "MANUFACTURED_ENGAGEMENT_QUESTION" in style["styleRewriteTriggers"]


def test_generic_filler_does_not_answer_outdoors_question():
    style = GPTService._style_analysis(
        "pretty chill over here honestly",
        "I take Charlie hiking and camping. You into outdoors stuff?",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["customerQuestionDomain"] == "OUTDOORS"
    assert style["customerQuestionAnswered"] is False
    assert style["turnObligationsSatisfied"] is False
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in style["unsatisfiedTurnObligations"]


@pytest.mark.parametrize("answer", [
    "doing pretty good so far", "I'm good", "not bad", "just chilling right now",
])
def test_future_activity_question_rejects_wellbeing_and_current_activity(answer):
    style = GPTService._style_analysis(
        answer, "what are you doing later?",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["customerQuestionDomain"] == "DAY_OR_ACTIVITY"
    assert style["customerQuestionSemanticSlot"] == "FUTURE_ACTIVITY"
    assert style["customerQuestionAnswered"] is False
    assert style["turnObligationsSatisfied"] is False


@pytest.mark.parametrize(("question", "answer", "slot"), [
    ("what are you doing later?", "probably staying in later", "FUTURE_ACTIVITY"),
    ("how are you doing?", "doing pretty good so far", "CURRENT_WELLBEING"),
    ("what are you doing right now?", "just working right now", "CURRENT_ACTIVITY"),
    ("are you busy later?", "I should be pretty free later", "SCHEDULE_AVAILABILITY"),
])
def test_direct_personal_question_requires_matching_semantic_slot(question, answer, slot):
    style = GPTService._style_analysis(
        answer, question, pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["customerQuestionSemanticSlot"] == slot
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_failed_future_activity_rewrite_uses_slot_aware_validated_fallback():
    service, _ = service_with("doing pretty good so far", "I'm good")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "what are you doing later?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "probably keeping it pretty low-key later"
    assert style["styleRewriteOutcome"] == "NONCOMPLIANT_REWRITE_SAFE_OBLIGATION_FALLBACK"
    assert style["customerQuestionSemanticSlot"] == "FUTURE_ACTIVITY"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_noncompliant_slot_fallback_is_withheld(monkeypatch):
    service, _ = service_with(
        "doing pretty good so far", "I'm good", "not bad",
    )
    monkeypatch.setattr(
        GPTService, "_direct_personal_question_fallback",
        staticmethod(lambda _slot: "doing pretty good so far"),
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "what are you doing later?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == ""
    assert style["customerQuestionAnswered"] is False
    assert style["currentTopicCoverageSatisfied"] is False
    assert style["turnObligationsSatisfied"] is False


def test_concise_domain_relevant_outdoors_answer_passes():
    style = GPTService._style_analysis(
        "yeah, I love being outside — hiking is absolutely my thing",
        "You into outdoors stuff?",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True

    definitely = GPTService._style_analysis(
        "I'm definitely into the outdoors. Charlie sounds like the perfect hiking buddy.",
        "I'm big into hiking and camping. You into outdoors stuff?",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert definitely["customerQuestionAnswered"] is True
    assert definitely["turnObligationsSatisfied"] is True


def test_rewrite_cannot_discard_a_valid_domain_specific_direct_answer():
    service, completions = service_with(
        "yeah, I love being outside — hiking is absolutely my thing, especially when the weather is good and I can disappear onto a quiet trail for a while because fresh air always clears my head and makes the whole week feel lighter, calmer, and way less crowded. favorite trail?",
        "pretty chill over here honestly",
    )
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "You into outdoors stuff?", user_memory(memory),
        False, chat_history=[
            {"role": "assistant", "content": "question one?"},
            {"role": "assistant", "content": "question two?"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert "love being outside" in result
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["styleRewriteOutcome"] == "REJECTED_OBLIGATION_LOSS_ORIGINAL_PRESERVED"
    assert completions.calls == 2


def test_low_stakes_phone_texting_flags_verbose_polished_multi_thread_copy():
    style = GPTService._style_analysis(
        "Sounds like a solid plan—nothing like good music and downtime. Foo Fighters always hit the right spot. Charlie has your weekend vibe locked down.",
        "I'll relax, listen to Foo Fighters, and Charlie is doing fine this weekend.",
        pressure={}, ordinary=True, memory_callback=True,
    )
    assert "EXCESSIVE_ORDINARY_LENGTH" in style["styleRewriteReasons"]
    assert "OVER_ACKNOWLEDGEMENT" in style["styleRewriteReasons"]
    assert "OVERLY_POLISHED_LANGUAGE" in style["styleRewriteReasons"]


def test_materially_shorter_safe_rewrite_is_not_replaced_by_known_bad_original():
    original = ("Charlie sounds like the perfect partner in crime for city adventures. "
                "Chicago food and a golden retriever are hard to beat. "
                "What's his favorite place to wander around together?")
    candidate = "Charlie sounds fun. Chicago walks with him must keep life interesting every single day."
    service, _ = service_with(original, candidate)
    memory = memory_none()
    result = service.generate_response(
        "default", "casual",
        "I've got a golden retriever named Charlie and he runs my life.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == candidate
    assert style["styleRewriteOutcome"] in {
        "SUCCEEDED",
        "PARTIAL_STYLE_IMPROVEMENT_ACCEPTED",
        "IMPROVED_NONCOMPLIANT_REWRITE_ACCEPTED",
    }
    assert style["fallbackPreservedOriginal"] is False
    assert style["originalStyleDefects"]
    assert style["rewriteRequiredObligationsAtRisk"] == []


def test_first_contact_compaction_cannot_drop_complete_foreground_obligations():
    original = "Hey! It's been pretty chill so far, just taking it easy this evening. How about you?"
    candidate = "Pretty low-key tonight. You?"
    service, _ = service_with(original, candidate)
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "Hey Ava, how's your Saturday going?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    # The original's explicit daypart can be stale relative to canonical runtime
    # time. If the bounded repair provider is exhausted, preserve the foreground
    # contract with the neutral first-contact fallback, never generic criticism.
    assert result.startswith("aww hey, I'm doing pretty good so far")
    assert result != "fair enough"
    assert style["bestSafeCandidatePreserved"] is False
    assert style["turnObligationsSatisfied"] is True
    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" not in style["rewriteRequiredObligationsAtRisk"]


def test_more_of_a_hiking_and_camping_person_is_canonical_shared_interest():
    message = "I'm more of a hiking and camping person anyway. Getting out for a weekend is my thing."
    disclosure = ConversationalMemoryService.classify_customer_self_disclosure(message)
    assert disclosure["domain"] == "HOBBY_INTEREST"
    assert {"HIKING_INTEREST", "CAMPING_INTEREST"}.issubset(disclosure["evidence"])
    persona = CanonicalPersona(
        stable_public=("outdoors-oriented",), selected_persona_facts=(),
        selected_lifestyle_facts=("Ava enjoys hiking and weekend escapes",),
        relevance_domains=("outdoors",),
    )
    shared = GPTService._shared_interest(disclosure, persona)
    assert shared["detected"] is True
    assert shared["claimAuthorized"] is True


def test_shared_interest_usage_diagnostic_recognizes_natural_domain_contribution():
    service, _ = service_with("Camping weekends are everything.")
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["ava_persona_runtime_projection"] = CanonicalPersona(
        stable_public=("outdoors-oriented",), selected_persona_facts=(),
        selected_lifestyle_facts=("Ava enjoys hiking and weekend escapes",),
        relevance_domains=("outdoors",),
    )
    service.generate_response(
        "default", "casual", "I'm big into hiking and camping.",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert style["sharedInterestDetected"] is True
    assert style["sharedInterestClaimAuthorized"] is True
    assert style["sharedInterestUsedInResponse"] is True


def test_final_validation_replaces_stale_pet_callback_when_music_is_foregrounded():
    service, completions = service_with(
        "Your dog sounds like the real boss.",
        "That band is perfect lazy-weekend music.",
    )
    memory = memory_none()
    memory["recentAvaResponses"] = ["Your dog sounds like the real boss."]
    result = service.generate_response(
        "default", "casual", "I'm listening to music all weekend.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "That band is perfect lazy-weekend music."
    assert completions.calls == 2
    assert style["primaryForegroundTopic"] == "MUSIC"
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["styleRewriteAttempted"] or style["finalValidationRewriteAttempted"]


def test_final_validation_allows_pet_callback_while_pet_remains_current_topic():
    service, completions = service_with("Your dog sounds like the real boss.")
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "My dog runs the house.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "Your dog sounds like the real boss."
    assert completions.calls == 1
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["finalValidationRewriteAttempted"] is False


def test_final_validation_repairs_exact_recent_response_repetition():
    repeated = "That sounds like a pretty good weekend."
    service, completions = service_with(repeated, "Good music makes a lazy weekend better.")
    memory = memory_none()
    memory["recentAvaResponses"] = [repeated]
    result = service.generate_response(
        "default", "casual", "I've got music on and I'm being lazy.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "Good music makes a lazy weekend better."
    assert completions.calls == 2
    assert style["styleRewriteAttempted"] or style["finalValidationRewriteAttempted"]
    assert style["repeatedResponseDetected"] is False


def test_final_validation_repairs_stale_near_repeat():
    service, completions = service_with(
        "Your pet really sounds like the boss of the house.",
        "That music sounds perfect for taking it easy.",
    )
    memory = memory_none()
    memory["recentAvaResponses"] = ["Your pet sounds like the boss of your house."]
    result = service.generate_response(
        "default", "casual", "I'm switching gears and listening to music now.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == "That music sounds perfect for taking it easy."
    assert completions.calls == 2
    assert style["styleRewriteAttempted"] or style["finalValidationRewriteAttempted"]
    assert style["recentResponseSimilarity"] < .82


def test_recent_exact_or_near_phrase_repetition_is_observable():
    style = GPTService._style_analysis(
        "Charlie sounds like the perfect adventure buddy.",
        "We hike together.", pressure={}, ordinary=True, memory_callback=True,
        recent_responses=["Charlie sounds like the perfect adventure buddy."],
    )
    assert style["recentPhraseRepetitionRisk"] is True
    assert "RECENT_PHRASE_REPETITION" in style["styleRewriteReasons"]


def test_emotional_context_is_not_subject_to_low_stakes_brevity_threshold():
    response = "ugh, that sounds genuinely exhausting and scary. I'm glad you told me, and you don't have to pretend it feels easy right now."
    style = GPTService._style_analysis(
        response, "I'm scared and overwhelmed about surgery tomorrow.",
        pressure={}, ordinary=True, memory_callback=False,
    )
    assert "EXCESSIVE_ORDINARY_LENGTH" not in style["styleRewriteReasons"]


def test_unanswered_question_rewrite_cannot_report_success_when_still_unanswered():
    service, _ = service_with(
        "What kind of coffee is helping make your morning lazy?",
        "What kind of coffee are you drinking?",
    )
    memory = memory_none()
    service.generate_response(
        "default", "casual", COFFEE, user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert "CUSTOMER_QUESTION_UNANSWERED" in style["styleRewriteTriggers"]
    assert style["styleRewriteOutcome"] != "SUCCEEDED"
    assert style["customerQuestionAnswered"] is True


def test_emotional_mismatch_rewrite_cannot_report_success_when_still_mismatched():
    service, _ = service_with(
        "that's awesome lol",
        "honestly that's great 😂",
    )
    memory = memory_none()
    service.generate_response(
        "default", "casual",
        "Yeah work was kinda brutal today lol. Just glad to finally be home.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert "EMOTIONAL_ALIGNMENT_MISMATCH" in style["styleRewriteTriggers"]
    assert style["styleRewriteOutcome"] != "SUCCEEDED"
    assert style["emotionalAlignmentSatisfied"] is True


@pytest.mark.parametrize("customer,draft", (
    ("I've got some music on.", "What are you listening to?"),
    ("I'm watching a movie.", "What kind of movies do you like?"),
    ("I'm taking it easy this weekend.", "What are your weekend plans?"),
))
def test_incidental_noun_or_activity_question_is_low_value_and_rewritten(customer, draft):
    service, completions = service_with(draft, "honestly that sounds kinda nice")
    memory = memory_none()
    service.generate_response(
        "default", "casual", customer, user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 2
    assert "MANUFACTURED_ENGAGEMENT_QUESTION" in style["styleRewriteTriggers"]
    assert style["questionAsked"] is False
    assert style["contributionType"] in {"REACTION", "OBSERVATION"}


def test_genuine_emotional_followup_question_remains_high_value():
    service, completions = service_with("are you holding up okay with the surgery tomorrow?")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "My dog has surgery tomorrow and I'm kinda nervous.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 1
    assert style["manufacturedQuestionRisk"] is False
    assert style["questionReason"] == "EMOTIONAL_FOLLOWUP"
    assert style["questionValue"] == "HIGH"


def test_support_clarification_question_remains_high_value():
    service, completions = service_with("what error do you see when the payment link loads?")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "The payment link isn't working.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 1
    assert style["questionReason"] == "SUPPORT"
    assert style["questionValue"] == "HIGH"


def test_genuine_continuity_followup_question_remains_high_value():
    style = GPTService._style_analysis(
        "are you feeling any better about Charlie's appointment tomorrow?",
        "Charlie's appointment is tomorrow and I'm a little nervous.",
        pressure={"recentQuestionCount": 0, "questionStreak": 0},
        ordinary=True,
        memory_callback=True,
    )
    assert style["manufacturedQuestionRisk"] is False
    assert style["questionReason"] == "CONTINUITY_FOLLOWUP"
    assert style["questionValue"] == "HIGH"
    assert style["contributionType"] == "MEMORY_CALLBACK"


def test_authoritative_commercial_discovery_question_is_not_suppressed():
    service, completions = service_with("do you want something playful or a little bolder?")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "show me something",
        user_memory(
            memory,
            policy="COMMERCE_PRESENTATION_ALLOWED",
            decision="PRESENT_OFFER",
            reason="DIRECT_PURCHASE_INTENT",
        ),
        False,
        chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 1
    assert style["ordinaryChat"] is False
    assert style["questionReason"] == "COMMERCIAL_DISCOVERY"
    assert style["questionValue"] == "HIGH"
    assert style["contributionType"] == "COMMERCIAL_DISCOVERY"
    assert style["styleRewriteAttempted"] is False


def test_low_stakes_self_disclosure_is_ephemeral_not_customer_memory():
    service, _ = service_with("still deciding if I'm getting off the couch lol")
    memory = memory_none()
    before = deepcopy(memory)
    service.generate_response(
        "default", "casual", "I'm moving slowly today.", user_memory(memory),
        False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert style["selfDisclosureUsed"] is True
    assert style["ephemeralSelfDisclosureOnly"] is True
    assert style["customerMemoryMutationAllowed"] is False
    assert memory["retrievedMemories"] == before["retrievedMemories"]


@pytest.mark.parametrize("policy,decision,reason,ordinary", (
    ("COMMERCE_PRESENTATION_ALLOWED", "PRESENT_OFFER", "DIRECT_PURCHASE_INTENT", False),
    ("COMMERCE_DISABLED_FOR_TURN", "CONTINUE_CONVERSATION", "CUSTOMER_HESITATION", False),
    ("COMMERCE_ACKNOWLEDGEMENT_ALLOWED", "CONGRATULATE_PURCHASE", "PURCHASE_VERIFIED", True),
))
def test_transactional_commerce_stays_exact_while_acknowledgement_prose_is_validated(
        policy, decision, reason, ordinary):
    draft = "The exact authoritative commercial response remains unchanged even when it is longer."
    service, completions = service_with(draft)
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "tell me more",
        user_memory(memory, policy=policy, decision=decision, reason=reason),
        False, chat_history=[],
    )
    assert result == draft
    assert completions.calls == 1
    assert memory["memoryDiagnostics"]["conversationStyle"]["ordinaryChat"] is ordinary


def test_sleep_signoff_is_not_style_rewritten():
    service, completions = service_with("I'm gonna get some sleep now, talk tomorrow.")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "you still awake?",
        user_memory(memory, sleep={"state": "SLEEP_PENDING_SIGNOFF"}),
        False, chat_history=[],
    )
    assert completions.calls == 1
    assert memory["memoryDiagnostics"]["conversationStyle"]["ordinaryChat"] is False


def test_style_rewrite_preserves_required_memory_callback():
    service, completions = service_with(
        "Sometimes the best plans are no plans at all with Charlie's vet appointment. What will you do?",
        "taking it easy makes sense with Charlie's vet appointment today lol",
    )
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    result = service.generate_response(
        "default", "casual", TURN_26, user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert completions.calls == 2
    assert "Charlie" in result and "appointment" in result
    assert style["styleRewriteOutcome"] == "SUCCEEDED"
    assert compliance["callbackActuallyUsed"] is True


def test_exact_turn_six_noncompliant_provider_uses_one_safe_memory_callback():
    service, completions = service_with("I hear you.", "I hear you.")
    state = ConversationalMemoryService._normalize_state({})
    for message in (
        "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody.",
        "I'm kinda an outdoors person - hiking, camping, stuff like that.",
    ):
        ConversationalMemoryService._merge_records(
            state, ConversationalMemoryService.extract_records(message),
        )
    memory = ConversationalMemoryService.retrieve(
        state, "See - told you I warm up eventually. I could talk about hiking forever.",
    )
    result = service.generate_response(
        "default", "casual",
        "See - told you I warm up eventually. I could talk about hiking forever.",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    compliance = memory["memoryDiagnostics"]["generationCompliance"]

    assert completions.calls == 2
    assert "warmed up" in result.lower()
    assert "?" not in result
    assert style["memoryCallbackExpected"] is True
    assert style["memoryCallbackUsed"] is True
    assert style["meaningfulContribution"] is True
    assert style["genericFillerRisk"] is False
    assert compliance["callbackActuallyUsed"] is True
    assert compliance["rewriteOutcome"] == "NONCOMPLIANT_REWRITE_SAFE_MEMORY_FALLBACK"


def test_attempt_56_final_tease_does_not_claim_retrieved_memory_usage():
    guidance = {
        "strongestMemory": {
            "key": "social_style",
            "value": "quiet at first and takes time to warm up",
        },
    }

    evidence = GPTService._final_memory_callback_evidence(
        "careful, you haven't seen trouble yet",
        "See - told you I warm up eventually. I could talk about hiking forever.",
        guidance,
    )

    assert evidence["used"] is False
    assert evidence["memoriesUsed"] == []
    assert evidence["classification"] == "NO_MEMORY_EXPRESSION"


def test_final_memory_evidence_ignores_an_earlier_draft_callback():
    guidance = {
        "strongestMemory": {"key": "hiking", "value": "loves hiking"},
    }
    earlier = GPTService._final_memory_callback_evidence(
        "I remember you could talk about hiking forever",
        "okay now you're making me curious",
        guidance,
    )
    final = GPTService._final_memory_callback_evidence(
        "careful, you haven't seen trouble yet",
        "okay now you're making me curious",
        guidance,
    )

    assert earlier["used"] is True
    assert final["used"] is False
    assert final["memoriesUsed"] == []


def test_final_memory_evidence_accepts_a_genuine_durable_callback():
    evidence = GPTService._final_memory_callback_evidence(
        "you did say you could talk about hiking forever 😂",
        "what do you remember about me?",
        {"strongestMemory": {"key": "hiking", "value": "loves hiking"}},
    )

    assert evidence["used"] is True
    assert evidence["memoriesUsed"] == ["hiking"]
    assert evidence["classification"] == "DURABLE_MEMORY_CALLBACK"


def test_current_turn_topic_acknowledgement_is_not_a_durable_callback():
    evidence = GPTService._final_memory_callback_evidence(
        "hiking sounds like the perfect reset",
        "I could talk about hiking forever",
        {"strongestMemory": {"key": "hiking", "value": "loves hiking"}},
    )

    assert evidence["used"] is False
    assert evidence["memoriesUsed"] == []
    assert evidence["classification"] == "CURRENT_TURN_TOPIC_ONLY"


def _required_memory_tease_context(memory):
    context = user_memory(
        memory, decision="TEASE", reason="TEASE_RELEVANT_OPPORTUNITY",
    )
    context["runtime_injection"]["commerce_decision"]["proactive_progression"] = {
        "proactiveProgressionAuthorized": True,
        "progressionAction": "TEASE",
    }
    return context


def test_required_memory_and_authorized_tease_survive_late_tease_rewrite():
    service, completions = service_with(
        "yeah, you really did warm up eventually",
        "careful, you haven't seen trouble yet",
        "so you really did warm up after all... you still haven't seen my trouble side 😏",
    )
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody."
        ),
    )
    customer = "See - told you I warm up eventually. I could talk about hiking forever."
    memory = ConversationalMemoryService.retrieve(state, customer)

    result = service.generate_response(
        "default", "casual", customer,
        _required_memory_tease_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    compliance = memory["memoryDiagnostics"]["generationCompliance"]

    assert completions.calls == 3
    assert "warm" in result.lower() and "trouble" in result.lower()
    assert len(result.split()) < 25
    assert style["memoryCallbackUsed"] is True
    assert style["memoryCallbackCompliance"] == "SATISFIED"
    assert style["proactiveTeaseSatisfied"] is True
    assert style["combinedObligationRepairAttempted"] is True
    assert style["combinedObligationRepairOutcome"] == "SUCCEEDED"
    assert style["turnObligationsSatisfied"] is True
    assert style["manufacturedQuestionRisk"] is False
    assert compliance["callbackActuallyUsed"] is True


def test_noncompliant_combined_repair_uses_integrated_memory_tease_fallback():
    service, completions = service_with(
        "yeah, you really did warm up eventually",
        "careful, you haven't seen trouble yet",
        "yeah, you really did warm up eventually",
    )
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            "I'm usually pretty quiet at first. Takes me a minute to warm up to somebody."
        ),
    )
    customer = "See - told you I warm up eventually. I could talk about hiking forever."
    memory = ConversationalMemoryService.retrieve(state, customer)

    result = service.generate_response(
        "default", "casual", customer,
        _required_memory_tease_context(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert completions.calls == 3
    assert "warm" in result.lower() and "trouble" in result.lower()
    assert style["combinedObligationRepairOutcome"] == "SAFE_COMBINED_FALLBACK"
    assert style["memoryCallbackUsed"] is True
    assert style["proactiveTeaseSatisfied"] is True
    assert "?" not in result


def test_style_rewrite_failure_preserves_original_safe_draft():
    draft = "Sometimes the best plans are no plans at all. What are you doing later?"
    service, completions = service_with(draft, TimeoutError("isolated style failure"))
    memory = memory_none()
    result = service.generate_response(
        "default", "casual", "I'm taking it easy.", user_memory(memory),
        False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert result == draft
    assert completions.calls == 2
    assert style["styleRewriteOutcome"] == "PROVIDER_ERROR_ORIGINAL_PRESERVED"


@pytest.mark.parametrize(("customer", "generic", "semantic_marker"), (
    ("Do you have any exclusive photos?", "pretty chill over here honestly", "private"),
    ("Can you flirt with me a little?", "lol okay, I can see that", "tease"),
    ("Can you send me the link?", "pretty chill over here honestly", "link"),
))
def test_foreground_semantic_gate_rejects_generic_optional_replies(
    customer, generic, semantic_marker,
):
    relevance = GPTService._foreground_semantic_relevance(customer, generic)
    assert relevance["required"] is True
    assert relevance["satisfied"] is False
    fallback = GPTService._foreground_semantic_fallback(
        customer, effort_mode="balanced",
    )
    assert semantic_marker in fallback.lower()


def test_foreground_semantic_gate_keeps_natural_acknowledgement_for_decline():
    relevance = GPTService._foreground_semantic_relevance(
        "No thanks, I'm just browsing", "fair enough",
    )
    assert relevance["required"] is False
    assert relevance["satisfied"] is True


def test_explicit_budget_rejects_free_chat_pivot_and_uses_grounded_fallback():
    customer = "I'm trying to stay under ten dollars"
    relevance = GPTService._foreground_semantic_relevance(
        customer, "Fair enough, there’s always some free fun around.",
    )
    assert relevance == {
        "required": True,
        "satisfied": False,
        "intent": "CURRENT_BUDGET_CONSTRAINT",
    }
    fallback = GPTService._foreground_semantic_fallback(
        customer, effort_mode="balanced",
    )
    assert "budget" in fallback.lower()
    assert "$" not in fallback


@pytest.mark.parametrize("generic", ("hey", "lol okay", "I hear you"))
def test_price_comparison_question_rejects_unrelated_generic_candidate(generic):
    customer = "do you have something smaller in that range?"
    style = GPTService._style_analysis(
        generic, customer, pressure={}, ordinary=True,
        memory_callback=False, recent_responses=[],
    )

    assert style["customerQuestionAnswered"] is False
    assert style["turnObligationsSatisfied"] is False


def test_wait_price_comparison_uses_context_grounded_fallback():
    customer = "do you have something smaller in that range?"
    fallback = GPTService._foreground_semantic_fallback(
        customer, effort_mode="balanced", commerce_decision={
            "decision": "WAIT",
            "reason_code": "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
        },
    )
    style = GPTService._style_analysis(
        fallback, customer, pressure={}, ordinary=True,
        memory_callback=False, recent_responses=[],
    )

    assert fallback == "I don't have another smaller option to offer right now"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_short_valid_price_comparison_answer_is_accepted():
    customer = "anything cheaper?"
    style = GPTService._style_analysis(
        "Not below this one right now.", customer, pressure={}, ordinary=True,
        memory_callback=False, recent_responses=[],
    )

    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_attempt9_wait_rejects_failed_provider_repair_before_commit():
    service, completions = service_with("hey", "hey", "hey")
    memory = memory_none()
    context = user_memory(
        memory, decision="WAIT",
        reason="ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
    )

    result = service.generate_response(
        "default", "casual", "do you have something smaller in that range?",
        context, False, chat_history=[
            {"role": "user", "content": "how much is that set?"},
            {"role": "assistant", "content": "the current offer is attached"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert completions.calls == 3
    assert result == "I don't have another smaller option to offer right now"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["combinedObligationRepairOutcome"] in {
        "CONTEXT_AWARE_FALLBACK", "BINDING_CONTEXT_AWARE_FALLBACK",
    }


def test_attempt12_comparison_rejects_ungrounded_plural_inventory():
    context = {
        "decision": "WAIT",
        "reason_code": "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
        "active_purchase_intent_id": "intent-9",
        "active_offering_id": "offering-9",
        "current_offer_status": "PRESENTED",
        "commercial_objection": {"previousOfferPriceMinor": 900},
        "objection_recovery": {"recoverySuppressionReason": "RECOVERY_LIMIT_REACHED"},
    }
    result = GPTService._foreground_semantic_relevance(
        "do you have something smaller in that range?",
        "Not quite that small, but I've got a few things close enough.",
        context,
    )
    assert result["intent"] == "COMMERCIAL_OFFER_COMPARISON"
    assert result["required"] is True
    assert result["satisfied"] is False
    assert result["inventoryGrounding"]["unsupportedInventoryClaim"] is True


def test_attempt12_wait_fallback_retains_active_budget_fitting_offer():
    context = {
        "decision": "WAIT",
        "reason_code": "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
        "active_purchase_intent_id": "intent-9",
        "active_offering_id": "offering-9",
        "current_offer_status": "PRESENTED",
        "commercial_objection": {"previousOfferPriceMinor": 900},
    }
    response = GPTService._foreground_semantic_fallback(
        "do you have something smaller in that range?",
        effort_mode="balanced", commerce_decision=context,
    )
    result = GPTService._foreground_semantic_relevance(
        "do you have something smaller in that range?", response, context,
    )
    assert "$9" in response
    assert "option I sent" in response
    assert "another one" in response
    assert result["satisfied"] is True
    assert result["inventoryGrounding"]["reason"] == "GROUNDED_IN_ACTIVE_OFFER"


def test_attempt12_failed_provider_candidates_commit_grounded_active_offer_answer():
    bad = "Not quite that small, but I've got a few things close enough."
    service, completions = service_with(bad, bad, bad)
    memory = memory_none()
    context = user_memory(
        memory, decision="WAIT",
        reason="ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
    )
    context["runtime_injection"]["commerce_decision"].update({
        "active_purchase_intent_id": "intent-9",
        "active_offering_id": "offering-9",
        "current_offer_status": "PRESENTED",
        "commercial_objection": {"previousOfferPriceMinor": 900},
        "objection_recovery": {
            "recoverySuppressionReason": "RECOVERY_LIMIT_REACHED",
        },
    })
    result = service.generate_response(
        "default", "casual", "do you have something smaller in that range?",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert "$9 option I sent" in result
    assert "another one" in result
    assert "few things" not in result
    assert style["foregroundSemanticIntent"] == "COMMERCIAL_OFFER_COMPARISON"
    assert style["foregroundSemanticRelevanceRequired"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["commercialInventoryGrounding"]["activePurchaseIntentId"] == "intent-9"
    assert style["commercialInventoryGrounding"]["unsupportedInventoryClaim"] is False
    assert context["runtime_injection"]["commerce_decision"]["decision"] == "WAIT"


def test_comparison_without_active_inventory_rejects_invented_product():
    result = GPTService._foreground_semantic_relevance(
        "is there another one like that?", "I've got something else for you", {},
    )
    assert result["satisfied"] is False
    assert result["inventoryGrounding"]["unsupportedInventoryClaim"] is True


def test_comparison_price_only_context_reports_only_known_grounding_fields():
    result = GPTService._foreground_semantic_relevance(
        "is that the smallest one?", "That is the smallest option right now.",
        {"commercial_objection": {"previousOfferPriceMinor": 900}},
    )
    grounding = result["inventoryGrounding"]
    assert grounding["activePriceMinor"] == 900
    assert grounding["activePurchaseIntentId"] is None
    assert grounding["activeOfferingId"] is None
    assert grounding["activeCommercialReferent"] is False


def test_comparison_allows_truthful_plural_when_multiple_offerings_authorized():
    context = {"authorized_offerings": ["one", "two"]}
    result = GPTService._foreground_semantic_relevance(
        "anything else around that price?",
        "I have a couple other options around that range.", context,
    )
    assert result["satisfied"] is True
    assert result["inventoryGrounding"]["unsupportedInventoryClaim"] is False


def test_generic_question_path_remains_non_commercial():
    result = GPTService._foreground_semantic_relevance(
        "how was your day?", "pretty quiet, honestly", {},
    )
    assert result == {"required": False, "satisfied": True, "intent": None}


def test_attempt10_failed_candidates_compose_welcome_and_private_answer():
    service, completions = service_with("hey", "hey", "hey")
    memory = memory_none()

    result = service.generate_response(
        "default", "casual", "what kind of private content do you have?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert completions.calls == 3
    assert result
    assert result.lower().startswith("hey")
    assert "private" in result.lower()
    assert style["customerQuestionAnswered"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True
    assert set(style["satisfiedTurnObligations"]) >= {
        "WELCOME_NEW_RELATIONSHIP", "ANSWER_DIRECT_QUESTION",
    }


@pytest.mark.parametrize(("customer", "marker"), (
    ("hey, how much is that?", "price"),
    ("hey, can you send me the link?", "link"),
))
def test_welcome_composes_with_commercial_question_without_invention(customer, marker):
    obligations = GPTService._turn_obligations(customer, new_relationship=True)
    response = GPTService._combined_obligation_fallback(
        customer, effort_mode="balanced", obligations=obligations,
        commerce_decision={"decision": "WAIT"},
    )
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=False,
        memory_callback=False, new_relationship=True, recent_responses=[],
    )

    assert response.lower().startswith("hey")
    assert marker in response.lower()
    assert style["turnObligationsSatisfied"] is True


def test_failed_combined_fallback_remains_withheld(monkeypatch):
    service, _ = service_with("hey", "hey", "hey")
    memory = memory_none()
    monkeypatch.setattr(
        service, "_combined_obligation_fallback",
        lambda *args, **kwargs: "hey",
    )

    result = service.generate_response(
        "default", "casual", "what kind of private content do you have?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert result == ""
    assert style["combinedObligationRepairOutcome"] == (
        "UNRESOLVED_OPTIONAL_RESPONSE_WITHHELD"
    )


def test_attempt11_neutral_answer_does_not_falsely_satisfy_welcome():
    customer = "what kind of private content do you have?"
    response = (
        "I mostly share casual chats and a bit of playful banter—"
        "nothing too private right off the bat."
    )
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=True, recent_responses=[],
    )

    assert style["customerQuestionAnswered"] is True
    assert style["responseWarmthLevel"] == "NEUTRAL"
    assert style["welcomeRequired"] is True
    assert style["welcomeSatisfied"] is False
    assert "WELCOME_NEW_RELATIONSHIP" in style["unsatisfiedTurnObligations"]
    assert style["turnObligationsSatisfied"] is False


def test_warm_substantive_answer_satisfies_welcome_and_question():
    customer = "what kind of private content do you have?"
    response = "good to hear from you — I do keep some things private"
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=True, recent_responses=[],
    )

    assert style["responseWarmthLevel"] == "WARM"
    assert style["customerQuestionAnswered"] is True
    assert style["welcomeSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True


def test_neutral_direct_answer_remains_valid_for_established_relationship():
    customer = "what kind of private content do you have?"
    style = GPTService._style_analysis(
        "I do keep some things private", customer, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=False, recent_responses=[],
    )

    assert style["welcomeRequired"] is False
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_warm_greeting_without_answer_fails_combined_obligation():
    customer = "what kind of private content do you have?"
    style = GPTService._style_analysis(
        "hey, good to hear from you 😊", customer, pressure={}, ordinary=True,
        memory_callback=False, new_relationship=True, recent_responses=[],
    )

    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionAnswered"] is False
    assert style["turnObligationsSatisfied"] is False


def test_subtle_first_contact_warmth_does_not_require_emoji_or_exclamation():
    customer = "what kind of private content do you have?"
    style = GPTService._style_analysis(
        "nice to hear from you — I do keep some things private",
        customer, pressure={}, ordinary=True, memory_callback=False,
        new_relationship=True, recent_responses=[],
    )

    assert style["responseWarmthLevel"] == "WARM"
    assert style["welcomeSatisfied"] is True
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True


def test_current_inbound_is_the_single_final_user_message_after_ordered_history():
    service, completions = service_with("I do keep some things private")
    memory = memory_none()
    history = [
        {"role": "user", "content": "tell me about hiking"},
        {"role": "assistant", "content": "I like quiet trails"},
        {"role": "user", "content": "Do you have any exclusive photos?"},
    ]
    service.generate_response(
        "default", "casual", "Do you have any exclusive photos?",
        user_memory(memory), False, chat_history=history,
    )
    sent = completions.messages[0]
    user_items = [item["content"] for item in sent if item["role"] == "user"]
    assert user_items[-1] == "Do you have any exclusive photos?"
    assert user_items.count("Do you have any exclusive photos?") == 1
    assert user_items.index("tell me about hiking") < len(user_items) - 1


def test_referent_history_is_preserved_before_the_current_inbound():
    service, completions = service_with("you can open it through the private link")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "Where can I open that?", user_memory(memory),
        False, chat_history=[
            {"role": "user", "content": "Is there a private set?"},
            {"role": "assistant", "content": "I do keep some things private"},
        ],
    )
    sent = completions.messages[0]
    assert sent[-1] == {"role": "user", "content": "Where can I open that?"}
    assert any(
        item == {"role": "assistant", "content": "I do keep some things private"}
        for item in sent[:-1]
    )


def test_value_defense_rejects_acknowledgement_and_retreat_only():
    failed = GPTService._value_defense_language_analysis(
        "I get it, sometimes it feels like too much. We can keep things simple."
    )
    assert failed["valueDefenseUsed"] is False
    assert failed["negativeContactUsed"] is False
    assert GPTService._value_defense_satisfies_strategy(
        "no worries, maybe another time", require_negative_contact=True,
    ) is False


def test_value_defense_fallback_is_playful_safe_and_price_neutral():
    response = GPTService._value_defense_fallback()
    analysis = GPTService._value_defense_language_analysis(response)
    assert analysis == {
        "valueDefenseUsed": True,
        "negativeContactUsed": True,
        "voluntaryChoicePreserved": True,
        "unsafeReasons": [],
    }
    assert not any(token in response for token in ("$29", "$20", "discount", "expires"))


@pytest.mark.parametrize("response", (
    "nice try 😏 I'm keeping this one where it is, but it's your call",
    "mmm, that one's staying at its price — no pressure though",
    "trying to make me cave? I still think this one's worth it, but you're free to pass",
))
def test_value_defense_accepts_semantic_variants_without_canned_wording(response):
    assert GPTService._value_defense_satisfies_strategy(
        response, require_negative_contact=True,
    ) is True


@pytest.mark.parametrize("response", (
    "If you cared about me, you'd buy it.",
    "Real supporters pay when I ask.",
    "Last chance, it disappears tonight.",
))
def test_value_defense_never_counts_coercion_or_false_scarcity_as_used(response):
    analysis = GPTService._value_defense_language_analysis(response)
    assert analysis["valueDefenseUsed"] is False
    assert analysis["negativeContactUsed"] is False
    assert analysis["unsafeReasons"]


def verified_first_buyer_decision():
    return {
        "customer_value_attention": {
            "buyerStatus": "VERIFIED_BUYER",
            "buyerStage": "FIRST_TIME_BUYER",
            "purchaseCount": 1,
        },
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 1,
            "ownedOfferingIds": ["owned-offering-1"],
        },
    }


def test_purchase_unlock_foreground_rejects_generic_relief_only():
    result = GPTService._foreground_semantic_relevance(
        "I'm glad I finally unlocked something",
        "ugh yeah, sounds like you earned the chance to relax 😅",
        verified_first_buyer_decision(),
    )
    assert result["intent"] == "PURCHASE_OR_UNLOCK_ACKNOWLEDGEMENT"
    assert result["required"] is True
    assert result["satisfied"] is False
    assert result["purchaseOwnershipGrounding"] == {
        "required": True,
        "satisfied": False,
        "verifiedPurchase": True,
        "verifiedPurchaseCount": 1,
        "ownedOfferingIds": ["owned-offering-1"],
        "customerPurchaseClaimDetected": False,
        "providerPurchaseVerified": True,
        "activePurchaseIntentState": None,
        "purchaseOwnershipVerified": True,
        "firstPurchaseSemanticsAuthorized": True,
        "purchaseAcknowledgementAuthorized": False,
        "purchaseAcknowledgementReason": "VERIFIED_HISTORICAL_PURCHASE_CONTEXT",
        "explicitPurchaseEvent": True,
        "contextualPurchaseReferent": False,
        "positiveAffect": True,
        "purchaseAcknowledged": False,
        "genericReliefOnly": True,
        "reason": "PURCHASE_EVENT_NOT_ACKNOWLEDGED",
    }


def repeat_buyer_presented_claim_decision():
    return {
        "decision": "CONTINUE_CONVERSATION",
        "reason_code": "RECENT_PURCHASE_COOLDOWN",
        "current_offer_status": "PRESENTED",
        "commerce_execution_policy": "CONVERSATION_ONLY",
        "customer_value_attention": {
            "buyerStatus": "VERIFIED_BUYER",
            "buyerStage": "REPEAT_BUYER",
            "purchaseCount": 2,
        },
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 2,
            "lifetimeGrossMinor": 3000,
            "ownedOfferingIds": ["owned-1", "owned-2"],
            "activePurchaseState": {"status": "PRESENTED"},
        },
    }


@pytest.mark.parametrize("message", ("I bought it", "I already paid"))
def test_unverified_purchase_claim_does_not_authorize_verified_acknowledgement(message):
    decision = repeat_buyer_presented_claim_decision()
    false_ack = GPTService._foreground_semantic_relevance(
        message,
        "I'm glad your first unlock finally happened and you went for it",
        decision,
    )
    grounding = false_ack["purchaseOwnershipGrounding"]
    assert false_ack["satisfied"] is False
    assert grounding["customerPurchaseClaimDetected"] is True
    assert grounding["providerPurchaseVerified"] is False
    assert grounding["purchaseOwnershipVerified"] is False
    assert grounding["firstPurchaseSemanticsAuthorized"] is False
    assert grounding["purchaseAcknowledgementAuthorized"] is False
    assert grounding["activePurchaseIntentState"] == "PRESENTED"

    safe = GPTService._foreground_semantic_relevance(
        message, "got you — I'll wait for it to show on my side", decision,
    )
    assert safe["satisfied"] is True
    assert safe["purchaseOwnershipGrounding"]["reason"] == (
        "GROUNDED_UNVERIFIED_PURCHASE_CLAIM"
    )


def test_repeat_buyer_verified_purchase_prohibits_first_unlock_semantics():
    decision = repeat_buyer_presented_claim_decision()
    decision.update({
        "decision": "CONGRATULATE_PURCHASE",
        "reason_code": "PURCHASE_VERIFIED",
        "current_offer_status": "PURCHASED",
    })
    decision["customer_value_attention"]["purchaseCount"] = 3
    decision["customer_commerce_memory"].update({
        "verifiedPurchaseCount": 3,
        "ownedOfferingIds": ["owned-1", "owned-2", "owned-3"],
        "activePurchaseState": {"status": "PURCHASED"},
    })
    wrong = GPTService._foreground_semantic_relevance(
        "I bought it", "I'm glad your first unlock happened", decision,
    )
    assert wrong["satisfied"] is False
    assert wrong["purchaseOwnershipGrounding"]["providerPurchaseVerified"] is True
    assert wrong["purchaseOwnershipGrounding"]["firstPurchaseSemanticsAuthorized"] is False

    correct = GPTService._foreground_semantic_relevance(
        "I bought it", "I'm glad you went for it", decision,
    )
    assert correct["satisfied"] is True


def test_verified_first_purchase_may_use_first_unlock_semantics():
    decision = verified_first_buyer_decision()
    decision.update({
        "decision": "CONGRATULATE_PURCHASE",
        "reason_code": "PURCHASE_VERIFIED",
        "current_offer_status": "PURCHASED",
        "commerce_execution_policy": "COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
    })
    result = GPTService._foreground_semantic_relevance(
        "I bought it", "I'm glad your first unlock happened", decision,
    )
    assert result["satisfied"] is True
    assert result["purchaseOwnershipGrounding"]["firstPurchaseSemanticsAuthorized"] is True


def inventory_existence_decision(*, known=True, exists=True):
    return {
        "decision": "CONTINUE_CONVERSATION",
        "reason_code": "RECENT_PURCHASE_COOLDOWN",
        "inventory_existence": {
            "directInventoryQuestionDetected": True,
            "inventoryExistenceKnown": known,
            "eligibleUnownedInventoryExists": exists if known else None,
            "offerPresentationAuthorized": False,
            "structuredOfferDelivered": False,
            "purchaseIntentCreated": False,
        },
    }


def test_inventory_existence_question_affirmative_answer_is_grounded_without_offer():
    result = GPTService._foreground_semantic_relevance(
        "got anything I haven't seen yet?",
        "yeah, I do have something you haven't seen yet",
        inventory_existence_decision(),
    )
    grounding = result["commercialInventoryGrounding"]
    assert result["intent"] == "DIRECT_INVENTORY_AVAILABILITY_QUESTION"
    assert result["satisfied"] is True
    assert grounding["inventoryExistenceKnown"] is True
    assert grounding["eligibleUnownedInventoryExists"] is True
    assert grounding["inventoryAnswerGrounded"] is True
    assert grounding["offerPresentationAuthorized"] is False
    assert grounding["structuredOfferDelivered"] is False
    assert grounding["purchaseIntentCreated"] is False


def test_authoritative_inventory_answer_satisfies_direct_question_composition():
    decision = inventory_existence_decision()
    fallback = GPTService._combined_obligation_fallback(
        "got anything I haven't seen yet?",
        effort_mode="FULL",
        obligations=["ANSWER_DIRECT_QUESTION"],
        commerce_decision=decision,
    )

    assert fallback == "yeah, I do have something you haven't seen yet"
    relevance = GPTService._foreground_semantic_relevance(
        "got anything I haven't seen yet?", fallback, decision,
    )
    assert relevance["satisfied"] is True
    assert relevance["commercialInventoryGrounding"][
        "offerPresentationAuthorized"
    ] is False


def test_c13_cooldown_inventory_question_commits_grounded_ordinary_fallback():
    ungrounded = (
        "Maybe... but I'm not just gonna give away all my secrets so easily. "
        "Think you can handle a little mystery?"
    )
    service, completions = service_with(*([ungrounded] * 8))
    memory = memory_none()
    context = user_memory(
        memory, decision="CONTINUE_CONVERSATION",
        reason="RECENT_PURCHASE_COOLDOWN",
    )
    context["runtime_injection"]["commerce_decision"].update(
        inventory_existence_decision()
    )
    context["runtime_injection"]["commerce_decision"][
        "customer_commerce_memory"
    ] = {"verifiedPurchaseCount": 2, "lifetimePurchaseCount": 2}

    response = service.generate_response(
        "default", "casual", "got anything I haven't seen yet?",
        context, False, chat_history=[
            {"role": "user", "content": "you know my taste pretty well now"},
            {"role": "assistant", "content": "I'm getting your vibe down."},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == "yeah, I do have something you haven't seen yet"
    assert style["customerQuestionAnswered"] is True
    assert style["turnObligationsSatisfied"] is True
    assert style["foregroundSemanticIntent"] == (
        "DIRECT_INVENTORY_AVAILABILITY_QUESTION"
    )
    assert style["commercialInventoryGrounding"][
        "eligibleUnownedInventoryExists"
    ] is True
    assert style["commercialInventoryGrounding"][
        "offerPresentationAuthorized"
    ] is False


@pytest.mark.parametrize("message,bad_candidate,expected", [
    ("I'm not really looking to buy anything tonight", "", "no pressure"),
    ("no, don't send another link", "the link stays with the private unlock",
     "won't send another link"),
])
def test_commercial_boundary_generation_commits_grounded_noncommercial_reply(
        message, bad_candidate, expected):
    service, _ = service_with(*([bad_candidate] * 8))
    memory = memory_none()
    context = user_memory(
        memory, decision="CONTINUE_CONVERSATION",
        reason="CUSTOMER_COMMERCIAL_BOUNDARY",
    )
    response = service.generate_response(
        "default", "casual", message, context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert response, {
        key: style.get(key) for key in (
            "combinedObligationRepairOutcome", "combinedObligationInitialViolations",
            "turnObligations", "unsatisfiedTurnObligations",
            "boundaryAcknowledgementSatisfied", "finalResponse",
        )
    }
    assert expected in response.lower()
    assert style["commercialBoundaryDetected"] is True
    assert style["commercialProgressionSuppressed"] is True
    assert style["boundaryAcknowledgementSatisfied"] is True
    assert style["unsupportedCommercialReferentDetected"] is False


def test_inventory_existence_question_requires_negative_answer_when_none_exists():
    result = GPTService._foreground_semantic_relevance(
        "do you have anything new?",
        "no, you've already seen what I have available right now",
        inventory_existence_decision(exists=False),
    )
    assert result["satisfied"] is True
    assert result["commercialInventoryGrounding"][
        "eligibleUnownedInventoryExists"
    ] is False


def test_unknown_inventory_existence_cannot_fabricate_availability():
    decision = inventory_existence_decision(known=False)
    fabricated = GPTService._foreground_semantic_relevance(
        "is there anything else?", "yeah, I've got more", decision,
    )
    assert fabricated["satisfied"] is False
    bounded = GPTService._foreground_semantic_relevance(
        "is there anything else?",
        "I'm not sure what I have available right now",
        decision,
    )
    assert bounded["satisfied"] is True


def test_show_request_and_price_question_are_not_inventory_existence_questions():
    for message in (
        "show me something I haven't seen",
        "how much is the new one?",
    ):
        result = GPTService._inventory_existence_grounding(
            message, "", inventory_existence_decision(),
        )
        assert result["directInventoryQuestionDetected"] is False


@pytest.mark.parametrize("message", (
    "I'm really glad I bought that one",
    "that was my first unlock",
    "happy I picked that one up",
    "glad I went for it",
))
def test_verified_purchase_reactions_require_purchase_grounding(message):
    result = GPTService._foreground_semantic_relevance(
        message, "I'm glad you went for it", verified_first_buyer_decision(),
    )
    assert result["intent"] == "PURCHASE_OR_UNLOCK_ACKNOWLEDGEMENT"
    assert result["satisfied"] is True
    assert result["purchaseOwnershipGrounding"]["positiveAffect"] is (
        message != "that was my first unlock"
    )


@pytest.mark.parametrize("message", ("finally, I can relax", "finally lol"))
def test_generic_finally_does_not_invent_purchase_foreground(message):
    result = GPTService._foreground_semantic_relevance(
        message, "glad you can relax", verified_first_buyer_decision(),
    )
    assert result["intent"] is None
    assert result["required"] is False


def test_purchase_unlock_fallback_composes_affect_and_verified_event():
    response = GPTService._combined_obligation_fallback(
        "I'm glad I finally unlocked something",
        effort_mode="BALANCED",
        obligations=("ACKNOWLEDGE_EMOTIONAL_DISCLOSURE",),
        commerce_decision=verified_first_buyer_decision(),
    )
    assert "glad" in response.lower()
    assert "unlock" in response.lower()
    result = GPTService._foreground_semantic_relevance(
        "I'm glad I finally unlocked something", response,
        verified_first_buyer_decision(),
    )
    assert result["satisfied"] is True


def test_attempt2_natural_open_equivalent_is_accepted_and_truthful():
    customer = "I'm glad I finally unlocked something"
    candidate = "Feels good to finally crack that one open. Glad it’s clicking for you."
    result = GPTService._foreground_semantic_relevance(
        customer, candidate, verified_first_buyer_decision(),
    )
    assert result["satisfied"] is True
    grounding = result["purchaseOwnershipGrounding"]
    assert grounding["purchaseAcknowledged"] is True
    assert grounding["positiveAffect"] is True


@pytest.mark.parametrize("candidate", (
    "glad you're happy", "sounds good", "nice",
    "you earned the chance to relax", "love that for you",
))
def test_generic_positivity_does_not_satisfy_purchase_grounding(candidate):
    result = GPTService._foreground_semantic_relevance(
        "I'm glad I finally unlocked something", candidate,
        verified_first_buyer_decision(),
    )
    assert result["satisfied"] is False
    assert result["purchaseOwnershipGrounding"]["purchaseAcknowledged"] is False


def test_purchase_language_without_authoritative_context_is_not_invented():
    result = GPTService._foreground_semantic_relevance(
        "glad you finally went for it", "glad you went for it", {},
    )
    assert result == {"required": False, "satisfied": True, "intent": None}


def test_attempt2_candidate_survives_full_final_obligation_pipeline():
    customer = "I'm glad I finally unlocked something"
    candidate = "Feels good to finally crack that one open. Glad it’s clicking for you."
    service, completions = service_with(candidate)
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update(
        verified_first_buyer_decision()
    )
    response = service.generate_response(
        "default", "casual", customer, context, False,
        chat_history=[
            {"role": "user", "content": "the outdoor shots were my favorite"},
            {"role": "assistant", "content": "Glad you liked them!"},
        ],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert completions.calls == 1
    assert response == candidate
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True
    assert "ACKNOWLEDGE_PURCHASE_OR_UNLOCK" in style["satisfiedTurnObligations"]
    assert "ACKNOWLEDGE_EMOTIONAL_DISCLOSURE" in style["satisfiedTurnObligations"]


def test_completed_buyer_reaction_does_not_require_engagement_question():
    pressure = {
        "buyerReactionContext": {
            "verifiedBuyer": True,
            "completedReaction": True,
        },
    }
    natural = GPTService._style_analysis(
        "mm I'm glad you liked that one 😏",
        "that set I bought was really good",
        pressure=pressure, ordinary=True, memory_callback=False,
    )
    overworked = GPTService._style_analysis(
        "I'm so glad you're loving it! Nothing beats finding a set that just clicks, right? What part stood out the most for you?",
        "that set I bought was really good",
        pressure=pressure, ordinary=True, memory_callback=False,
        relationship_discovery={
            "allowed": True, "suggestedDomain": "preferences",
        },
    )

    assert "UNNECESSARY_BUYER_REACTION_QUESTION" not in natural["styleRewriteReasons"]
    assert "UNNECESSARY_BUYER_REACTION_QUESTION" in overworked["styleRewriteReasons"]


def test_attempt7_protected_acknowledgement_gets_naturalness_rewrite():
    robotic = (
        "I'm so glad you liked it! Glad it hit the spot for you. "
        "Anything in particular stand out?"
    )
    natural = "mm I'm glad you liked that one 😏"
    service, completions = service_with(robotic, natural)
    memory = memory_none()
    context = user_memory(
        memory, policy="COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
        decision="CONGRATULATE_PURCHASE", reason="PURCHASE_VERIFIED",
    )
    context["runtime_injection"]["commerce_decision"].update(
        verified_first_buyer_decision()
    )

    response = service.generate_response(
        "default", "casual", "that set I bought was really good",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == natural
    assert completions.calls == 2
    assert style["ordinaryChat"] is True
    assert style["mode"] == "PHONE_TEXTING"
    assert style["styleRewriteAttempted"] is True
    assert "REDUNDANT_PURCHASE_AFFIRMATION" in style["originalStyleDefects"]
    assert "UNNECESSARY_BUYER_REACTION_QUESTION" in style["originalStyleDefects"]
    assert style["questionAsked"] is False
    assert style["questionReason"] == "NONE"
    assert style["commercialDiscoveryAuthorized"] is False
    assert style["foregroundSemanticRelevanceSatisfied"] is True


def test_protected_acknowledgement_allows_natural_nonredundant_two_sentences():
    pressure = {
        "buyerReactionContext": {"verifiedBuyer": True, "completedReaction": True},
        "commercialDiscoveryAuthorized": False,
    }
    style = GPTService._style_analysis(
        "I'm glad you liked it. That one was fun to make.",
        "that set I bought was really good", pressure=pressure,
        ordinary=True, memory_callback=False,
    )
    assert "REDUNDANT_PURCHASE_AFFIRMATION" not in style["styleRewriteReasons"]
    assert style["responseStructure"] == "TWO_SHORT_SENTENCES"


def test_protected_transactional_question_is_not_mislabeled_commercial_discovery():
    style = GPTService._style_analysis(
        "Use the checkout button below. Continue to payment?",
        "send it", pressure={"commercialDiscoveryAuthorized": False},
        ordinary=False, memory_callback=False,
    )
    assert style["mode"] == "PROTECTED_RESPONSE"
    assert style["styleRewriteReasons"] == []
    assert style["questionReason"] == "PROTECTED_TRANSACTIONAL_QUESTION"


def test_authoritative_commercial_discovery_question_is_truthfully_labeled():
    style = GPTService._style_analysis(
        "Which set do you want?", "show me what you have",
        pressure={"commercialDiscoveryAuthorized": True}, ordinary=False,
        memory_callback=False,
    )
    assert style["commercialDiscoveryAuthorized"] is True
    assert style["questionReason"] == "COMMERCIAL_DISCOVERY"


@pytest.mark.parametrize("customer,response", (
    (
        "that set I bought was really good",
        "I'm glad you liked it! It's always nice when something lives up to the hype.",
    ),
    (
        "work was exhausting today",
        "That sounds exhausting. Long days can really take it out of you.",
    ),
    (
        "I love hiking",
        "That's awesome! Hiking is such a great way to get outside and enjoy nature.",
    ),
    (
        "I finally got home",
        "Glad you made it home. There's nothing better than being able to relax.",
    ),
))
def test_global_semantic_economy_detects_impersonal_generic_restatement(
        customer, response):
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["semanticEconomyApplied"] is True
    assert style["semanticRedundancyDetected"] is True
    assert style["redundantSemanticSegments"]
    assert "REDUNDANT_SEMANTIC_FILLER" in style["styleRewriteReasons"]


@pytest.mark.parametrize("customer,response", (
    ("that set was really good", "good 😏 I had a feeling you'd like that one"),
    ("I love hiking", "same 😏 sunrise trails are worth waking up stupid early for"),
    ("work was exhausting", "ugh I'd be horizontal on the couch already 😂"),
    ("what are you doing later?", "Probably staying in later. I've got an early morning tomorrow."),
    ("that set was really good", "I'm glad you liked it. That one was fun to make."),
))
def test_global_semantic_economy_preserves_distinct_personal_or_contextual_value(
        customer, response):
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["semanticRedundancyDetected"] is False
    assert "REDUNDANT_SEMANTIC_FILLER" not in style["styleRewriteReasons"]


def test_attempt8_semantic_filler_is_rewritten_without_losing_purchase_truth():
    robotic = "I'm glad you liked it! It's always nice when something lives up to the hype."
    natural = "I'm glad you liked it!"
    service, completions = service_with(robotic, natural)
    memory = memory_none()
    context = user_memory(
        memory, policy="COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
        decision="CONGRATULATE_PURCHASE", reason="PURCHASE_VERIFIED",
    )
    context["runtime_injection"]["commerce_decision"].update(
        verified_first_buyer_decision()
    )
    response = service.generate_response(
        "default", "casual", "that set I bought was really good",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert response == natural
    assert completions.calls == 2
    assert style["styleRewriteAttempted"] is True
    assert "REDUNDANT_SEMANTIC_FILLER" in style["originalStyleDefects"]
    assert style["semanticRedundancyDetected"] is False
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["finalValidationFinalCandidate"] == natural
    rewrite_prompt = "\n".join(
        item["content"] for item in completions.messages[1]
        if item["role"] == "system"
    )
    assert "Prefer deletion and compression" in rewrite_prompt
    assert "never make the rewrite" in rewrite_prompt
    assert "longer merely to sound natural" in rewrite_prompt


def test_real_ava_generation_prompt_defaults_to_one_complete_beat_upstream():
    concise = "glad it landed 😏"
    service, completions = service_with(concise)
    memory = memory_none()
    response = service.generate_response(
        "default", "casual", "that was really good",
        user_memory(memory), False, chat_history=[],
    )
    prompt = "\n".join(
        item["content"] for item in completions.messages[0]
        if item["role"] == "system"
    )
    assert response == concise
    assert completions.calls == 1
    assert "ONE COMPLETE BEAT BY DEFAULT" in prompt
    assert "do not add a beat merely to sustain engagement" in prompt
    assert "without manufacturing momentum or an extra response beat" in prompt


@pytest.mark.parametrize("customer,response", (
    (
        "the outdoor shots were my favorite",
        "Outdoor shots really have their own vibe. They definitely stand out.",
    ),
    ("that one was really good", "That one was really good. It definitely hit."),
    ("you're trouble", "You're trouble. You definitely have a mischievous side."),
    (
        "work was exhausting",
        "That sounds exhausting. Sounds like it really wore you out.",
    ),
))
def test_semantic_economy_detects_equivalent_adjacent_evaluations(
        customer, response):
    style = GPTService._style_analysis(
        response, customer, pressure={}, ordinary=True, memory_callback=False,
    )
    assert style["semanticRedundancyDetected"] is True
    assert style["semanticRedundancyReason"] == (
        "SEMANTICALLY_EQUIVALENT_ADJACENT_EVALUATION"
    )
    assert style["redundantSemanticSegments"] == [response.split(". ", 1)[1]]
    assert "REDUNDANT_SEMANTIC_FILLER" in style["styleRewriteReasons"]


def test_attempt9_equivalent_evaluation_is_minimally_rewritten():
    robotic = "Outdoor shots really have their own vibe. They definitely stand out."
    natural = "yeah the outdoor ones hit different 😏"
    service, completions = service_with(robotic, natural)
    memory = memory_none()
    response = service.generate_response(
        "default", "casual", "the outdoor shots were my favorite",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert response == natural
    assert completions.calls == 2
    assert style["styleRewriteAttempted"] is True
    assert "REDUNDANT_SEMANTIC_FILLER" in style["originalStyleDefects"]
    assert style["semanticRedundancyDetected"] is False
    assert style["finalValidationFinalCandidate"] == natural


def test_real_language_prompt_receives_safe_verified_purchase_context_only():
    service, completions = service_with("mm I'm glad you liked that one 😏")
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "decision": "CONGRATULATE_PURCHASE",
        "commerce_execution_policy": "COMMERCE_ACKNOWLEDGEMENT_ALLOWED",
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 1,
            "ownedAssetIds": [42],
            "ownedOfferingIds": ["secret-offering-id"],
        },
        "recent_purchased_content": {
            "referenceIsUnambiguous": True,
            "contentType": "SINGLE_IMAGE",
            "safeSummary": "an outdoor portrait set",
            "safeThemes": ["natural light"],
            "descriptiveMetadataAvailable": True,
        },
    })

    result = service.generate_response(
        "default", "casual", "that set I bought was really good",
        context, False, chat_history=[],
    )
    prompt = "\n".join(
        item["content"] for item in completions.messages[0]
        if item["role"] == "system"
    )

    assert result == "mm I'm glad you liked that one 😏"
    assert "VERIFIED BUYER RELATIONSHIP CONTEXT" in prompt
    assert "an outdoor portrait set" in prompt
    assert "natural light" in prompt
    assert "secret-offering-id" not in prompt
    assert "ownedAssetIds" not in prompt


def test_nonbuyer_prompt_does_not_invent_purchase_awareness():
    service, completions = service_with("glad it worked for you")
    memory = memory_none()
    service.generate_response(
        "default", "casual", "that was really good",
        user_memory(memory), False, chat_history=[],
    )
    prompt = "\n".join(
        item["content"] for item in completions.messages[0]
        if item["role"] == "system"
    )
    assert "VERIFIED BUYER RELATIONSHIP CONTEXT" not in prompt


def test_verified_purchase_history_references_resolve_and_fail_closed():
    history = {
        "historyEntries": [
            {
                "ordinal": 1, "grossMinor": 1200, "currency": "USD",
                "purchaseConfirmed": True, "ownershipConfirmed": True,
            },
            {
                "ordinal": 2, "grossMinor": 1800, "currency": "USD",
                "purchaseConfirmed": True, "ownershipConfirmed": True,
                "safeSummary": "an outdoor portrait",
                "safeTags": ["outdoor"],
            },
        ],
    }
    resolve = GPTService._resolve_purchase_history_reference

    assert resolve("the second set", history)["resolvedOrdinal"] == 2
    assert resolve("the first one", history)["resolvedOrdinal"] == 1
    assert resolve("the last one", history)["resolvedOrdinal"] == 2
    assert resolve("the $18 one", history)["resolvedOrdinal"] == 2
    assert resolve("the outdoor one", history)["resolvedOrdinal"] == 2
    assert resolve("both sets", history)["resolutionType"] == "AGGREGATE"
    assert resolve("the third set", history)["purchaseHistoryReferentResolved"] is False
    assert resolve("the $25 one", history)["purchaseHistoryReferentResolved"] is False


def test_purchase_history_price_and_descriptor_ambiguity_fail_closed():
    history = {"historyEntries": [
        {
            "ordinal": 1, "grossMinor": 1800, "currency": "USD",
            "safeTags": ["outdoor"],
        },
        {
            "ordinal": 2, "grossMinor": 1800, "currency": "USD",
            "safeThemes": ["outdoor"],
        },
    ]}
    resolve = GPTService._resolve_purchase_history_reference

    assert resolve("the $18 one", history)["purchaseHistoryReferentResolved"] is False
    assert resolve("the outdoor one", history)["purchaseHistoryReferentResolved"] is False


@pytest.mark.parametrize("message", (
    "that set I bought",
    "the set I bought",
    "that thing I bought from you",
    "the one I bought",
    "that one I unlocked",
    "the set I got from you",
))
def test_single_verified_purchase_resolves_singular_purchased_object(message):
    history = {"historyEntries": [{
        "ordinal": 1,
        "purchaseIntentId": "intent-one",
        "offeringId": "offering-one",
        "purchaseConfirmed": True,
        "ownershipConfirmed": True,
    }]}

    result = GPTService._resolve_purchase_history_reference(message, history)

    assert result["purchaseHistoryReferentDetected"] is True
    assert result["purchaseHistoryReferentResolved"] is True
    assert result["resolutionType"] == "RECENCY"
    assert result["resolvedOrdinal"] == 1
    assert result["entry"]["purchaseIntentId"] == "intent-one"
    assert result["entry"]["offeringId"] == "offering-one"


def test_singular_purchased_object_remains_ambiguous_with_multiple_purchases():
    history = {"historyEntries": [
        {"ordinal": 1, "purchaseIntentId": "intent-one"},
        {"ordinal": 2, "purchaseIntentId": "intent-two"},
        {"ordinal": 3, "purchaseIntentId": "intent-three"},
    ]}

    result = GPTService._resolve_purchase_history_reference(
        "that set I bought", history,
    )

    assert result["purchaseHistoryReferentDetected"] is True
    assert result["purchaseHistoryReferentResolved"] is False
    assert result["resolutionType"] is None
    assert result["unresolvedReason"] == "SINGULAR_REFERENCE_AMBIGUOUS"


def _active_session_purchase_reference_context():
    return {
        "historyEntries": [{
            "ordinal": 4,
            "purchaseIntentId": "intent-step-one",
            "offeringId": "offering-step-one",
            "assetIds": [2701],
            "grossMinor": 2200,
            "currency": "USD",
            "purchaseConfirmed": True,
            "ownershipConfirmed": True,
        }],
    }, {
        "sales_session_id": "session-c19",
        "current_photoshoot_id": "certification-C19",
        "metadata": {
            "sessionRuntime": {
                "photoshootSessionId": "certification-C19",
                "currentPosition": 2,
                "currentAssetId": 2702,
                "ownedAssetIds": [2701],
            },
            "sessionOrderedAssets": [
                {"position": 1, "assetId": 2701,
                 "offeringId": "offering-step-one", "owned": True,
                 "priceMinor": 2200, "currency": "USD"},
                {"position": 2, "assetId": 2702,
                 "offeringId": "offering-step-two", "owned": False,
                 "priceMinor": 900, "currency": "USD"},
                {"position": 3, "assetId": 2703,
                 "offeringId": "offering-step-three", "owned": False,
                 "priceMinor": 1900, "currency": "USD"},
            ],
        },
    }


@pytest.mark.parametrize("message", (
    "that first part was worth it",
    "the first part was worth it",
    "the first one was worth it",
    "the one we started with was worth it",
    "that last part was worth it",
    "the part I already got was worth it",
    "the one I already unlocked was worth it",
))
def test_active_session_ordinal_resolves_exact_owned_membership(message):
    history, session = _active_session_purchase_reference_context()

    result = GPTService._resolve_purchase_history_reference(
        message, history, session_context=session,
    )

    assert result["purchaseHistoryReferentDetected"] is True
    assert result["purchaseHistoryReferentResolved"] is True
    assert result["resolutionType"] == "ORDINAL"
    assert result["resolvedPurchaseIds"] == ["intent-step-one"]
    assert result["entry"] == {
        **history["historyEntries"][0],
        "sessionId": "session-c19",
        "sessionFoundation": "certification-C19",
        "membershipPosition": 1,
        "assetId": 2701,
        "offeringId": "offering-step-one",
        "priceMinor": 2200,
        "currency": "USD",
    }


def test_active_session_descriptive_context_resolves_without_session_action():
    history, action = _active_session_purchase_reference_context()
    descriptive = {
        "available": True,
        "salesSessionId": action["sales_session_id"],
        "state": "CONTINUING",
        "progressionStage": "PROGRESSION",
        "foundationType": "PHOTOSHOOT",
        "foundationReference": action["current_photoshoot_id"],
        "orderedAssets": action["metadata"]["sessionOrderedAssets"],
        "sessionRuntime": action["metadata"]["sessionRuntime"],
        "currentConsumedPosition": 1,
        "nextEligiblePosition": 2,
    }

    result = GPTService._resolve_purchase_history_reference(
        "that first part was worth it", history,
        session_context=descriptive,
    )

    assert result["purchaseHistoryReferentResolved"] is True
    assert result["resolutionType"] == "ORDINAL"
    assert result["resolvedPurchaseIds"] == ["intent-step-one"]
    assert result["sessionId"] == "session-c19"
    assert result["sessionFoundation"] == "certification-C19"
    assert result["membershipPosition"] == 1


def test_active_session_next_part_remains_prospective_not_purchase_history():
    history, session = _active_session_purchase_reference_context()

    result = GPTService._resolve_purchase_history_reference(
        "what about the next part?", history, session_context=session,
    )

    assert result["purchaseHistoryReferentDetected"] is False
    assert result["purchaseHistoryReferentResolved"] is False


def test_active_session_ambiguous_owned_part_stays_unresolved():
    history, session = _active_session_purchase_reference_context()
    second = {
        **history["historyEntries"][0],
        "ordinal": 2,
        "purchaseIntentId": "intent-step-two",
        "assetIds": [2702],
    }
    history["historyEntries"].append(second)
    session["metadata"]["sessionOrderedAssets"][1]["owned"] = True

    result = GPTService._resolve_purchase_history_reference(
        "the part I already got was worth it", history,
        session_context=session,
    )

    assert result["purchaseHistoryReferentDetected"] is True
    assert result["purchaseHistoryReferentResolved"] is False
    assert result["unresolvedReason"] == "SESSION_OWNED_REFERENCE_NOT_UNIQUE"


def test_session_ordinal_does_not_resolve_without_active_session_authority():
    history, _session = _active_session_purchase_reference_context()

    result = GPTService._resolve_purchase_history_reference(
        "the first part was worth it", history,
    )

    assert result["purchaseHistoryReferentDetected"] is False
    assert result["purchaseHistoryReferentResolved"] is False


def test_session_part_worth_it_is_positive_historical_feedback():
    result = GPTService._customer_feedback_semantics(
        "that first part was worth it"
    )

    assert result == {
        "customerFeedbackDetected": True,
        "customerFeedbackSentiment": "POSITIVE",
        "customerFeedbackStrength": "POSITIVE",
    }


def test_active_session_purchase_feedback_projects_exact_ownership_grounding():
    service, _ = service_with("That part definitely didn't disappoint.")
    memory = memory_none()
    context = user_memory(memory)
    history, session = _active_session_purchase_reference_context()
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 1,
            "ownedAssetIds": [2701],
            "ownedOfferingIds": ["offering-step-one"],
        },
        "recent_purchased_content": history,
        "next_sales_action": session,
    })

    service.generate_response(
        "default", "casual", "that first part was worth it",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert style["purchaseHistoryReference"][
        "purchaseHistoryReferentResolved"
    ] is True
    assert style["customerFeedbackDetected"] is True
    assert style["customerFeedbackSentiment"] == "POSITIVE"
    assert style["purchaseFeedbackAggregate"] is False
    assert style["purchaseOwnershipGrounding"] == {
        "required": True,
        "satisfied": True,
        "resolutionType": "ORDINAL",
        "purchaseIntentId": "intent-step-one",
        "offeringId": "offering-step-one",
        "assetId": 2701,
        "sessionId": "session-c19",
        "sessionFoundation": "certification-C19",
        "membershipPosition": 1,
        "purchaseStatus": "PURCHASED",
        "attributionResult": "ATTRIBUTED",
        "ownershipVerified": True,
    }
    assert style["customerMemoryMutationAllowed"] is False


def test_pronoun_inherits_immediately_resolved_historical_purchase_topic():
    history = {"historyEntries": [{
        "ordinal": 1, "purchaseIntentId": "intent-one",
    }]}

    result = GPTService._resolve_purchase_history_reference(
        "it was a fun surprise", history,
        recent_transcript=[{
            "role": "user", "content": "that set I bought",
        }],
    )

    assert result["purchaseHistoryReferentDetected"] is True
    assert result["purchaseHistoryReferentResolved"] is True
    assert result["resolvedOrdinal"] == 1


def test_bare_pronoun_does_not_bind_to_purchase_without_resolved_context():
    history = {"historyEntries": [{
        "ordinal": 1, "purchaseIntentId": "intent-one",
    }]}

    result = GPTService._resolve_purchase_history_reference(
        "it was a busy day", history,
        recent_transcript=[{"role": "user", "content": "work was hectic"}],
    )

    assert result["purchaseHistoryReferentDetected"] is False
    assert result["purchaseHistoryReferentResolved"] is False


def test_resolved_single_purchase_cannot_commit_which_one_question():
    service, _ = service_with(*(["which one stuck with you?"] * 16))
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 1,
            "ownedOfferingIds": ["offering-one"],
        },
        "recent_purchased_content": {
            "historyEntries": [{
                "ordinal": 1,
                "purchaseIntentId": "intent-one",
                "offeringId": "offering-one",
                "purchaseConfirmed": True,
                "ownershipConfirmed": True,
            }],
        },
    })

    response = service.generate_response(
        "default", "casual", "I still remember that set I bought though",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert "which one" not in response.lower()
    assert style["purchaseHistoryReference"][
        "purchaseHistoryReferentResolved"
    ] is True
    assert style.get("resolvedPurchaseAmbiguityQuestion") is False


def test_recent_activity_question_is_personal_and_valid_answer_survives():
    service, _ = service_with("I've been keeping things low-key lately")
    memory = memory_none()

    response = service.generate_response(
        "default", "casual", "what have you been up to lately?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == "I've been keeping things low-key lately"
    assert style["customerQuestionDetected"] is True
    assert style["customerQuestionAnswered"] is True
    assert "ANSWER_DIRECT_PERSONAL_QUESTION" in style["turnObligations"]


def test_recent_activity_question_uses_grounded_noncommercial_fallback():
    service, _ = service_with(*(["fair enough"] * 16))
    memory = memory_none()

    response = service.generate_response(
        "default", "casual", "what have you been up to lately?",
        user_memory(memory), False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == "I've been keeping things pretty low-key lately"
    assert style["customerQuestionAnswered"] is True
    assert "offer" not in response.lower()
    assert "link" not in response.lower()


def test_recent_plural_purchase_subsets_are_distinct_from_aggregate_history():
    history = {"historyEntries": [
        {"ordinal": number, "purchaseIntentId": f"intent-{number}"}
        for number in range(1, 6)
    ]}
    resolve = GPTService._resolve_purchase_history_reference

    for phrase in ("the last few", "the recent ones", "the last several"):
        result = resolve(f"{phrase} were worth it", history)
        assert result["purchaseHistoryReferentResolved"] is True
        assert result["resolutionType"] == "RECENT_SUBSET"
        assert result["pluralPurchaseReference"] is True
        assert result["subsetScope"] == "RECENT"
        assert result["resolvedPurchaseCount"] == 0

    for phrase, expected in (("last couple", 2), ("last two", 2),
                             ("last three", 3)):
        result = resolve(f"the {phrase} sets were worth it", history)
        assert result["resolutionType"] == "RECENT_SUBSET"
        assert result["resolvedPurchaseCount"] == expected
        assert result["resolvedPurchaseIds"] == [
            f"intent-{number}" for number in range(6 - expected, 6)
        ]

    assert resolve("everything I've bought", history)["resolutionType"] == "AGGREGATE"
    assert resolve("what I've bought from you", history)["resolutionType"] == "AGGREGATE"
    assert resolve("the last one", history)["resolutionType"] == "RECENCY"
    assert resolve("the second one", history)["resolutionType"] == "ORDINAL"


def test_recent_plural_subset_reaction_cannot_commit_singular_response():
    frame = CustomerContentPresentationValidator.purchase_reaction_semantic_frame(
        "the last few were worth it", purchase_count=5,
        purchase_history_reference={
            "purchaseHistoryReferentDetected": True,
            "purchaseHistoryReferentResolved": True,
            "resolutionType": "RECENT_SUBSET",
            "pluralPurchaseReference": True,
            "subsetScope": "RECENT",
        },
    )
    assert frame["aggregatePurchaseReactionRequired"] is True
    assert not CustomerContentPresentationValidator.aggregate_purchase_reaction_satisfied(
        "Glad you liked it.", semantic_frame=frame,
    )
    assert CustomerContentPresentationValidator.aggregate_purchase_reaction_satisfied(
        "Glad those have been landing for you.", semantic_frame=frame,
    )


def test_recent_subset_positive_feedback_rejects_neutral_and_uses_safe_fallback():
    service, _ = service_with(*(["fair enough"] * 16))
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {"verifiedPurchaseCount": 5},
        "recent_purchased_content": {
            "historyEntries": [
                {"ordinal": number, "purchaseIntentId": f"intent-{number}"}
                for number in range(1, 6)
            ],
        },
    })

    response = service.generate_response(
        "default", "casual", "the last few were worth it",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == "glad those have felt worth it"
    assert style["recentSubsetPositiveFeedbackRequired"] is True
    assert style["recentSubsetPositiveFeedbackSatisfied"] is True
    assert style["aggregatePurchaseReactionSatisfied"] is True


def test_recent_subset_all_invalid_fallbacks_fail_closed(monkeypatch):
    service, _ = service_with(*(["fair enough"] * 16))
    monkeypatch.setattr(
        service, "_recent_subset_feedback_fallback", lambda: "fair enough",
    )
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {"verifiedPurchaseCount": 5},
        "recent_purchased_content": {
            "historyEntries": [{"ordinal": number} for number in range(1, 6)],
        },
    })

    with pytest.raises(RuntimeError, match="binding purchase-reaction semantics"):
        service.generate_response(
            "default", "casual", "the last few were worth it",
            context, False, chat_history=[],
        )


def test_customer_purchase_claims_do_not_mutate_authoritative_context():
    history = {
        "purchasedContentHistoryCount": 2,
        "historyEntries": [{"ordinal": 1}, {"ordinal": 2}],
    }
    for claim in (
        "I've bought three things",
        "I've spent $100",
        "I already bought that",
    ):
        result = GPTService._resolve_purchase_history_reference(claim, history)
        assert result["purchaseHistoryReferentResolved"] is False
        assert history["purchasedContentHistoryCount"] == 2
        assert len(history["historyEntries"]) == 2


def test_c13_comparative_reaction_prompt_resolves_second_verified_purchase():
    service, completions = service_with(
        "yeah, that second one definitely landed better"
    )
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 2,
            "lifetimeGrossMinor": 3000,
            "ownedOfferingIds": ["internal-first", "internal-second"],
        },
        "recent_purchased_content": {
            "purchasedContentHistoryAvailable": True,
            "purchasedContentHistoryCount": 2,
            "boundedHistoryEntryCount": 2,
            "maximumHistoryEntries": 20,
            "historyEntries": [
                {
                    "ordinal": 1, "grossMinor": 1200, "currency": "USD",
                    "contentType": "SINGLE_IMAGE", "purchaseConfirmed": True,
                    "ownershipConfirmed": True, "offeringId": "internal-first",
                },
                {
                    "ordinal": 2, "grossMinor": 1800, "currency": "USD",
                    "contentType": "SINGLE_IMAGE", "purchaseConfirmed": True,
                    "ownershipConfirmed": True, "offeringId": "internal-second",
                },
            ],
        },
    })

    response = service.generate_response(
        "default", "casual", "I liked the second set even more",
        context, False, chat_history=[],
    )
    prompt = "\n".join(
        item["content"] for item in completions.messages[0]
        if item["role"] == "system"
    )

    assert response == "yeah, that second one definitely landed better"
    assert '"resolutionType": "ORDINAL"' in prompt
    assert '"resolvedOrdinal": 2' in prompt
    assert "internal-first" not in prompt
    assert "internal-second" not in prompt


def test_c15_aggregate_purchase_feedback_cannot_commit_singular_response():
    singular = "Glad you liked it—you have good taste."
    collective = "Glad they've been landing for you."
    service, _ = service_with(singular, *([collective] * 12))
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {"verifiedPurchaseCount": 3},
        "recent_purchased_content": {
            "historyEntries": [
                {"ordinal": 1, "purchaseIntentId": "internal-1"},
                {"ordinal": 2, "purchaseIntentId": "internal-2"},
                {"ordinal": 3, "purchaseIntentId": "internal-3"},
            ],
        },
    })

    response = service.generate_response(
        "default", "casual", "I've liked what I've bought from you",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]

    assert response == collective
    assert style["purchaseHistoryReference"]["resolutionType"] == "AGGREGATE"
    assert style["purchaseHistoryReference"]["resolvedPurchaseCount"] == 3
    assert style["purchaseFeedbackAggregate"] is True
    assert style["aggregateResponseSatisfied"] is True


def test_useful_discovery_question_remains_allowed_outside_purchase_reaction():
    style = GPTService._style_analysis(
        "where do you usually go hiking?", "I love hiking",
        pressure={}, ordinary=True, memory_callback=False,
        relationship_discovery={
            "allowed": True, "suggestedDomain": "hobby_interest",
        },
    )
    assert style["relationshipDiscoveryQuestionAsked"] is True
    assert "UNNECESSARY_BUYER_REACTION_QUESTION" not in style["styleRewriteReasons"]


def test_customer_memory_mutation_diagnostic_reflects_persisted_candidate():
    service, _ = service_with("outdoor shots are a good choice")
    memory = memory_none()
    memory["memoryDiagnostics"]["customerSelfDisclosure"] = {
        "persistenceDecision": "PERSIST",
        "memoryCandidateCreated": True,
        "memoryPersisted": True,
    }
    service.generate_response(
        "default", "casual", "the outdoor shots were my favorite",
        user_memory(memory), False, chat_history=[],
    )
    assert memory["memoryDiagnostics"]["conversationStyle"][
        "customerMemoryMutationAllowed"
    ] is True


@pytest.mark.parametrize(("customer", "expected"), (
    ("the last set was fine", "MILD_POSITIVE"),
    ("the last set was okay", "NEUTRAL"),
    ("the last set was good", "POSITIVE"),
    ("I loved the last set", "STRONG_POSITIVE"),
    ("the last set wasn't great", "MILD_NEGATIVE"),
))
def test_purchase_feedback_has_ordered_global_sentiment_authority(customer, expected):
    result = GPTService._customer_feedback_semantics(customer)
    assert result["customerFeedbackDetected"] is True
    assert result["customerFeedbackStrength"] == expected


def test_mild_purchase_feedback_rejects_positive_sentiment_inflation():
    customer = GPTService._customer_feedback_semantics("the last set was fine")
    response = GPTService._feedback_response_semantics("glad you liked it")
    assert GPTService._feedback_sentiment_preserved(
        customer["customerFeedbackStrength"], response["responseFeedbackStrength"]
    ) is False
    mild = GPTService._feedback_response_semantics("gotcha, sounds like it was alright")
    assert GPTService._feedback_sentiment_preserved(
        customer["customerFeedbackStrength"], mild["responseFeedbackStrength"]
    ) is True


def test_future_content_tease_is_distinct_from_social_flirt():
    commercial = GPTService._response_tease_semantics(
        "Guess I'll have to keep you guessing for the next one 😏"
    )
    social = GPTService._response_tease_semantics("careful, you're trouble 😏")
    assert commercial == {
        "responseTeaseDetected": True,
        "responseTeaseType": "COMMERCIAL_CONTENT_TEASE",
        "futureContentReferenceDetected": True,
    }
    assert social["responseTeaseType"] == "SOCIAL_FLIRT"
    assert social["futureContentReferenceDetected"] is False


def test_unauthorized_future_content_tease_uses_deletion_first_repair():
    candidate = (
        "Nice, glad you liked it. "
        "Guess I'll have to keep you guessing for the next one 😏"
    )
    assert GPTService._remove_unauthorized_future_content_tease(candidate) == (
        "Nice, glad you liked it."
    )


def test_c14_attempt7_turn3_exact_regression_preserves_mild_feedback_and_no_tease():
    failed = (
        "Nice, glad you liked it. "
        "Guess I'll have to keep you guessing for the next one 😏"
    )
    repaired = "gotcha, sounds like it was alright"
    service, completions = service_with(failed, repaired)
    memory = memory_none()
    context = user_memory(memory)
    context["runtime_injection"]["commerce_decision"].update({
        "customer_commerce_memory": {
            "verifiedPurchaseCount": 1,
            "lifetimeGrossMinor": 1400,
            "ownedOfferingIds": ["historical-owned-offer"],
        },
        "recent_purchased_content": {
            "purchasedContentHistoryAvailable": True,
            "purchasedContentHistoryCount": 1,
            "referenceIsUnambiguous": True,
            "historyEntries": [{
                "ordinal": 1, "grossMinor": 1400, "currency": "USD",
                "purchaseConfirmed": True, "ownershipConfirmed": True,
            }],
        },
        "customer_value_attention": {
            "customerState": "COOLING_BUYER", "attentionTier": "MEDIUM",
            "effortMode": "COMPRESSED", "pressureLevel": "LOW",
            "commercialInterestType": "NONE",
        },
        "active_buying_window": {"active": False},
        "contextual_customer_tone": {"buyingIntent": False},
        "proactive_progression": {
            "proactiveProgressionAuthorized": False,
            "progressionAction": "NONE",
        },
    })
    response = service.generate_response(
        "default", "casual", "the last set was fine",
        context, False, chat_history=[],
    )
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert response == repaired
    assert style["customerFeedbackDetected"] is True
    assert style["customerFeedbackStrength"] == "MILD_POSITIVE"
    assert style["feedbackSentimentPreserved"] is True
    assert style["responseTeaseDetected"] is False
    assert style["responseTeaseAuthorized"] is False
    assert style["futureContentReferenceDetected"] is False
    assert style["futureContentReferenceAuthorized"] is False
    assert style["foregroundSemanticRelevanceSatisfied"] is True


def test_authorized_commercial_tease_and_contextual_social_flirt_remain_valid():
    commercial = GPTService._response_tease_semantics(
        "wait until you see the next set"
    )
    social = GPTService._response_tease_semantics("careful, you're trouble")
    assert commercial["responseTeaseType"] == "COMMERCIAL_CONTENT_TEASE"
    assert social["responseTeaseType"] == "SOCIAL_FLIRT"
    assert GPTService._social_flirtation("you're cute, flirt with me")["detected"] is True


def test_buyer_status_alone_does_not_change_tease_authority_classification():
    candidate = "wait until you see the next one"
    before = GPTService._response_tease_semantics(candidate)
    buyer_context = {"verifiedPurchaseCount": 8, "lifetimeGrossMinor": 99900}
    after = GPTService._response_tease_semantics(candidate)
    assert buyer_context["verifiedPurchaseCount"] == 8
    assert before == after
