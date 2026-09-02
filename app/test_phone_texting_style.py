from copy import deepcopy
from types import SimpleNamespace

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.gpt_service import GPTService
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
    assert "SHORT BY DEFAULT" in prompt
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


@pytest.mark.parametrize("policy,decision,reason", (
    ("COMMERCE_PRESENTATION_ALLOWED", "PRESENT_OFFER", "DIRECT_PURCHASE_INTENT"),
    ("COMMERCE_DISABLED_FOR_TURN", "CONTINUE_CONVERSATION", "CUSTOMER_HESITATION"),
    ("COMMERCE_ACKNOWLEDGEMENT_ALLOWED", "CONGRATULATE_PURCHASE", "PURCHASE_VERIFIED"),
))
def test_protected_commerce_is_never_style_rewritten(policy, decision, reason):
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
    assert memory["memoryDiagnostics"]["conversationStyle"]["ordinaryChat"] is False


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
