from datetime import datetime

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService
from app.services.gpt_service import GPTService
from app.test_turn22_future_event_memory import TURN_22, TURN_22_AT, _base_state


TURN_26 = "I'm probably just gonna take it easy tomorrow after work."


def _state_with_charlie_event():
    state = _base_state()
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
            active_records=state["records"],
        ),
    )
    return state


def test_exact_turn26_retrieves_overlapping_charlie_event_without_persisting_weak_plan():
    state = _state_with_charlie_event()
    records = ConversationalMemoryService.extract_records(
        TURN_26, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
        active_records=state["records"],
    )
    assert not any(record["category"] == "event" for record in records)
    result = ConversationalMemoryService.retrieve(state, TURN_26, now=TURN_22_AT)
    events = [record for record in result["retrievedMemories"]
              if record["category"] == "event"]
    assert len(events) == 1
    assert events[0]["value"]["subject"] == "Charlie"
    assert events[0]["value"]["event"] == "vet appointment"
    diagnostics = result["memoryDiagnostics"]
    assert "event" in diagnostics["semanticDomains"]
    assert diagnostics["temporalEventRecall"]["reason"] == "RESOLVED_TEMPORAL_OVERLAP"
    assert diagnostics["temporalEventRecall"]["timezone"] == "America/Chicago"
    assert diagnostics["temporalEventRecall"]["matchedEvents"][0]["scheduledFor"] == "2026-08-28T12:00:00-05:00"
    guidance = diagnostics["continuityGuidance"]
    assert guidance["priority"] == "HIGH"
    assert guidance["relevanceReasons"] == ["RESOLVED_TEMPORAL_OVERLAP"]
    assert guidance["strongestMemory"]["key"] == "charlie_vet_appointment"
    assert guidance["maximumCallbacks"] == 1


@pytest.mark.parametrize("message", (
    TURN_26,
    "Tomorrow should be pretty quiet for me.",
    "What do I have going on tomorrow?",
    "Anything happening Friday?",
    "I haven't figured out my Friday yet.",
))
def test_temporal_overlap_retrieval_matrix(message):
    result = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), message, now=TURN_22_AT,
    )
    assert any(record["category"] == "event"
               and record["value"]["event"] == "vet appointment"
               for record in result["retrievedMemories"])


def test_canonical_weekend_window_does_not_include_friday():
    result = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), "I'm looking forward to the weekend.",
        now=TURN_22_AT,
    )
    assert not any(record["category"] == "event"
                   for record in result["retrievedMemories"])


@pytest.mark.parametrize("message", (
    "I'm listening to music tonight.",
    "That movie was hilarious.",
    "What's your favorite food?",
    "I'm going hiking next month.",
    "Next Friday might be busy.",
    "Tomorrow by Taylor Swift is stuck in my head.",
    "Tomorrow Never Knows is a great song.",
))
def test_temporal_context_false_positive_matrix(message):
    result = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), message, now=TURN_22_AT,
    )
    assert not any(record["category"] == "event"
                   for record in result["retrievedMemories"])


@pytest.mark.parametrize("message", (
    "I'll probably just chill tomorrow.",
    "Maybe I'll watch TV Friday.",
    "I might take it easy this weekend.",
    "Probably just gonna relax tomorrow.",
    "I don't know, maybe I'll do something Saturday.",
    "Tomorrow should be pretty quiet.",
    "I might grab some food later tomorrow.",
))
def test_weak_leisure_does_not_persist(message):
    assert not any(record["category"] == "event"
                   for record in ConversationalMemoryService.extract_records(
                       message, observed_at=TURN_22_AT,
                       customer_timezone="America/Chicago",
                       active_records=_state_with_charlie_event()["records"],
                   ))


def test_legacy_weak_event_is_ignored_by_every_retrieval_route():
    state = _state_with_charlie_event()
    state["records"].append({
        "category": "event",
        "key": "customer_probably_just_gonna_take_it_easy",
        "value": {
            "subject": "customer", "event": "probably just gonna take it easy",
            "status": "upcoming", "temporalCertainty": "TENTATIVE",
            "completionVerified": False, "scheduledFor": "2026-08-28T18:00:00-05:00",
        },
        "status": "current", "metadata": {},
    })
    for message in (
        "I'm taking it easy tomorrow.",
        "What did I say I was doing tomorrow?",
        "Any plans tomorrow?",
    ):
        result = ConversationalMemoryService.retrieve(state, message, now=TURN_22_AT)
        assert "customer_probably_just_gonna_take_it_easy" not in (
            result["memoryDiagnostics"]["retrievedKeys"]
        )


@pytest.mark.parametrize("message, event", (
    ("I might have a job interview Friday.", "job interview"),
    ("I think Charlie's vet appointment is Monday.", "vet appointment"),
    ("I'm probably flying to Denver next weekend.", "flying to denver"),
    ("I may have a doctor appointment tomorrow.", "doctor appointment"),
    ("We might have dinner reservations Saturday.", "dinner reservations"),
))
def test_concrete_tentative_events_remain_durable(message, event):
    records = ConversationalMemoryService.extract_records(
        message, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
        active_records=_state_with_charlie_event()["records"],
    )
    extracted = [record for record in records if record["category"] == "event"]
    assert len(extracted) == 1
    assert extracted[0]["value"]["event"] == event
    assert extracted[0]["value"]["temporalCertainty"] == "TENTATIVE"


def test_turn26_learn_diagnostics_explain_overlap_and_rejected_weak_persistence():
    class Prospect:
        preference_state = _state_with_charlie_event()

    class Repository:
        state = Prospect.preference_state
        def get(self, **_):
            item = Prospect(); item.preference_state = self.state; return item
        def merge_conversational_memory(self, *, values, **_):
            self.state = values
            item = Prospect(); item.preference_state = values; return item

    result = ConversationalMemoryService(repository=Repository()).learn(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=1,
        telegram_chat_id=1, message_text=TURN_26, observed_at=TURN_22_AT,
    )
    diagnostics = result["memoryDiagnostics"]
    assert diagnostics["extractedThisTurn"] == 0
    assert diagnostics["persistedThisTurn"] == 0
    assert diagnostics["eventPersistence"] == {
        "rejected": True, "reason": "INSUFFICIENT_CONTINUITY_SIGNIFICANCE",
    }
    assert diagnostics["temporalEventRecall"]["reason"] == "RESOLVED_TEMPORAL_OVERLAP"
    assert any(record["value"]["subject"] == "Charlie"
               for record in result["retrievedMemories"] if record["category"] == "event")


def test_non_temporal_semantic_memory_gets_one_ranked_continuity_candidate():
    state = _state_with_charlie_event()
    records = []
    records.extend(ConversationalMemoryService.extract_records(
        "I'm mostly into rock. Been listening to a lot of Foo Fighters lately.",
        observed_at=TURN_22_AT,
    ))
    ConversationalMemoryService._merge_records(state, records)
    result = ConversationalMemoryService.retrieve(
        state, "I need some music for the drive home.", now=TURN_22_AT,
    )
    guidance = result["memoryDiagnostics"]["continuityGuidance"]
    assert guidance["priority"] == "HIGH"
    assert guidance["strongestMemory"]["category"] == "preference"
    assert guidance["maximumCallbacks"] == 1
    assert not any(record["category"] in {"pet", "event"}
                   for record in result["retrievedMemories"])


def test_irrelevant_or_absent_memory_has_no_callback_candidate():
    irrelevant = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), "That movie was hilarious.", now=TURN_22_AT,
    )
    assert irrelevant["retrievedMemories"] == []
    assert irrelevant["memoryDiagnostics"]["continuityGuidance"] == {
        "priority": "NONE", "strongestMemory": None,
        "relevanceReasons": [], "conditionalUse": True, "maximumCallbacks": 0,
    }
    absent = ConversationalMemoryService.retrieve(
        {"schemaVersion": 2, "records": []}, "Long day at work.", now=TURN_22_AT,
    )
    assert absent["retrievedMemories"] == []
    assert absent["memoryDiagnostics"]["continuityGuidance"]["priority"] == "NONE"


def test_generation_contract_enforces_genuinely_required_high_continuity():
    class Training:
        def runtime_prompt_block(self, **_): return ""
    class Completions:
        def create(self, **kwargs):
            captured["prompt"] = kwargs["messages"][0]["content"]
            return type("Completion", (), {"choices": [type("Choice", (), {
                "message": type("Message", (), {"content": "honestly that sounds kinda nice 😂"})()
            })()]})()
    captured = {}
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": Completions()})()})()
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    result = service.generate_response("default", "casual", TURN_26, {
        "runtime_injection": {"conversational_memory": memory},
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    assert "Charlie" in result and "appointment" in result
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert compliance["callbackRequired"] is True
    assert compliance["callbackActuallyUsed"] is True
    assert compliance["callbackCompliance"] == "SATISFIED"
    assert compliance["rewriteAttempted"] is True
    assert compliance["rewriteOutcome"] == "NONCOMPLIANT_REWRITE"
    assert compliance["omissionReason"] is None
    assert memory["memoryDiagnostics"]["conversationStyle"][
        "combinedObligationRepairOutcome"
    ] == "SAFE_COMBINED_FALLBACK"
    prompt = captured["prompt"]
    assert "default to no question" in prompt
    assert "Avoid generic aphorisms" in prompt
    assert "not mandatory talking points" in prompt
    assert "elapsed planned event did not necessarily happen" in prompt
    assert "HIGH-RELEVANCE CONVERSATIONAL CONTINUITY" in prompt
    assert '"maximumCallbacks": 1' in prompt
    assert "Do not append a question" in prompt


def _continuity_test_service(responses):
    class Training:
        def runtime_prompt_block(self, **_): return ""
    class Completions:
        def __init__(self):
            self.responses = iter(responses)
            self.calls = 0
            self.messages = []
        def create(self, **kwargs):
            self.calls += 1
            self.messages.append(kwargs["messages"])
            text = next(self.responses)
            return type("Completion", (), {"choices": [type("Choice", (), {
                "message": type("Message", (), {"content": text})()
            })()]})()
    completions = Completions()
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": completions})()})()
    return service, completions


def test_high_temporal_continuity_rewrites_generic_draft_and_reports_actual_use():
    service, completions = _continuity_test_service((
        "A quiet Saturday sounds good. What else are you doing?",
        "That sounds sensible before your sister's flight Saturday.",
    ))
    memory = {"retrievedMemories": [], "memoryDiagnostics": {
        "continuityGuidance": {
            "priority": "HIGH",
            "strongestMemory": {"category": "event", "key": "sister_flight", "value": {
                "subject": "sister", "event": "flight", "scheduledFor": "2026-08-29",
            }},
            "relevanceReasons": ["RESOLVED_TEMPORAL_OVERLAP"],
            "conditionalUse": True, "maximumCallbacks": 1,
        },
    }}
    result = service.generate_response("default", "casual", "Saturday should be quiet.", {
        "runtime_injection": {"conversational_memory": memory},
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert completions.calls == 2
    assert "sister" in result.lower() and "flight" in result.lower()
    assert result.count("?") == 0
    assert compliance["callbackExpected"] is True
    assert compliance["callbackActuallyUsed"] is True
    assert compliance["rewriteAttempted"] is True
    assert compliance["strongestMemoryKey"] == "sister_flight"
    assert compliance["omissionReason"] is None


def test_high_continuity_legitimate_safety_override_does_not_rewrite():
    service, completions = _continuity_test_service(("I need to head to sleep now.",))
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    service.generate_response("default", "casual", TURN_26, {
        "runtime_injection": {
            "conversational_memory": memory,
            "sleep_context": {"state": "SLEEP_PENDING_SIGNOFF"},
        },
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert completions.calls == 1
    assert compliance["callbackExpected"] is False
    assert compliance["callbackActuallyUsed"] is False
    assert compliance["omissionReason"] == "CONVERSATIONAL_AVAILABILITY_OVERRIDE"


def test_no_relevant_memory_keeps_single_pass_generation_natural():
    service, completions = _continuity_test_service(("yeah that sounds pretty relaxing",))
    memory = {"retrievedMemories": [], "memoryDiagnostics": {
        "continuityGuidance": {
            "priority": "NONE", "strongestMemory": None,
            "relevanceReasons": [], "conditionalUse": True, "maximumCallbacks": 0,
        },
    }}
    result = service.generate_response("default", "casual", "A quiet day sounds good.", {
        "runtime_injection": {"conversational_memory": memory},
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    assert result == "yeah that sounds pretty relaxing"
    assert completions.calls == 1
    assert memory["memoryDiagnostics"]["generationCompliance"]["callbackExpected"] is False


def _turn28_commerce_memory(memory, *, policy="COMMERCE_DISABLED_FOR_TURN",
                            decision="CONTINUE_CONVERSATION",
                            reason="RECENT_PURCHASE_COOLDOWN"):
    return {
        "runtime_injection": {
            "conversational_memory": memory,
            "commerce_execution_policy": policy,
            "commerce_decision": {
                "decision": decision,
                "reason_code": reason,
                "selected_opportunity": {
                    "title": "Historical product must not leak",
                    "short_description": "A little surprise",
                    "offering_type": "SINGLE",
                },
            },
        },
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }


def test_turn28_disabled_cooldown_is_ordinary_and_runs_bounded_rewrite():
    service, completions = _continuity_test_service((
        "Sometimes easy nights are the most memorable. Maybe a surprise could shake things up?",
        "Honestly that sounds nice, especially with Charlie's vet appointment tomorrow.",
    ))
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    result = service.generate_response(
        "default", "casual", TURN_26, _turn28_commerce_memory(memory),
        False, chat_history=[],
    )
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert completions.calls == 2
    assert "Charlie" in result
    assert compliance["protectedCommercialSemantics"] is False
    assert compliance["commercialAuthorityReason"] == "COMMERCE_DISABLED_ORDINARY_RESPONSE"
    assert compliance["callbackExpected"] is True
    assert compliance["rewriteAttempted"] is True
    assert compliance["rewriteSucceeded"] is True
    assert compliance["rewriteOutcome"] == "SUCCEEDED"
    assert compliance["omissionReason"] is None
    initial_prompt = completions.messages[0][0]["content"]
    assert "ORDINARY RELATIONSHIP CONVERSATION" in initial_prompt
    assert "Historical product must not leak" not in initial_prompt
    assert "A little surprise" not in initial_prompt
    assert "surprise-content hint" in initial_prompt


def test_turn28_initial_callback_needs_no_rewrite():
    service, completions = _continuity_test_service((
        "Taking it easy makes sense before Charlie's vet appointment tomorrow.",
    ))
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    service.generate_response(
        "default", "casual", TURN_26, _turn28_commerce_memory(memory),
        False, chat_history=[],
    )
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert completions.calls == 1
    assert compliance["callbackActuallyUsed"] is True
    assert compliance["rewriteAttempted"] is False


@pytest.mark.parametrize("policy,decision,reason", (
    ("COMMERCE_PRESENTATION_ALLOWED", "PRESENT_OFFER", "DIRECT_PURCHASE_INTENT"),
    ("COMMERCE_NUDGE_ALLOWED", "NUDGE_ACTIVE_OFFER", "ACTIVE_OFFER_NUDGE_ELIGIBLE"),
    ("COMMERCE_ACKNOWLEDGEMENT_ALLOWED", "CONGRATULATE_PURCHASE", "PURCHASE_VERIFIED"),
    ("COMMERCE_DISABLED_FOR_TURN", "CONTINUE_CONVERSATION", "CUSTOMER_HESITATION"),
    ("COMMERCE_DISABLED_FOR_TURN", "CONTINUE_CONVERSATION", "PRICE_REQUEST"),
))
def test_genuinely_commercial_semantics_protect_response_from_rewrite(
        policy, decision, reason):
    service, completions = _continuity_test_service((
        "The protected commercial response stays exactly as generated.",
    ))
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    result = service.generate_response(
        "default", "casual", TURN_26,
        _turn28_commerce_memory(memory, policy=policy, decision=decision, reason=reason),
        False, chat_history=[],
    )
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert result == "The protected commercial response stays exactly as generated."
    assert completions.calls == 1
    assert compliance["protectedCommercialSemantics"] is True
    assert compliance["callbackExpected"] is False
    assert compliance["rewriteAttempted"] is False
    assert compliance["omissionReason"] == "AUTHORITATIVE_COMMERCIAL_RESPONSE"


def test_continuity_rewrite_provider_failure_uses_required_composition_fallback():
    class Training:
        def runtime_prompt_block(self, **_): return ""
    class Completions:
        calls = 0
        def create(self, **_):
            self.calls += 1
            if self.calls == 1:
                text = "A low-key night sounds good."
                return type("Completion", (), {"choices": [type("Choice", (), {
                    "message": type("Message", (), {"content": text})()
                })()]})()
            raise TimeoutError("isolated rewrite failure")
    completions = Completions()
    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": completions})()})()
    memory = ConversationalMemoryService.retrieve(
        _state_with_charlie_event(), TURN_26, now=TURN_22_AT,
    )
    result = service.generate_response(
        "default", "casual", TURN_26, _turn28_commerce_memory(memory),
        False, chat_history=[],
    )
    compliance = memory["memoryDiagnostics"]["generationCompliance"]
    assert "Charlie" in result and "appointment" in result
    assert completions.calls == 3
    assert compliance["rewriteSucceeded"] is True
    assert compliance["rewriteOutcome"] == "PROVIDER_ERROR"
    assert compliance["omissionReason"] is None
    style = memory["memoryDiagnostics"]["conversationStyle"]
    assert style["combinedObligationRepairOutcome"] == "SAFE_COMBINED_FALLBACK"
