from datetime import datetime, timezone

import pytest

from app.services.ava_temporal_context_service import AvaTemporalContextService
from app.services.gpt_service import GPTService
from app.services.live_controlled_test_observer_service import LiveControlledTestObserverService


def _context(at, customer_timezone=None):
    return AvaTemporalContextService(clock=lambda: at).build(
        customer_timezone=customer_timezone,
    )


def _capture_prompt(message, context, response="Natural reply without a clock reference."):
    captured = {}

    class Training:
        def runtime_prompt_block(self, **_): return ""

    class Completions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return type("Completion", (), {"choices": [type("Choice", (), {
                "message": type("Message", (), {"content": response})()
            })()]})()

    service = GPTService(api_key="test", global_training_service=Training())
    service.openai_client = type("Client", (), {"chat": type("Chat", (), {
        "completions": Completions(),
    })()})()
    actual = service.generate_response("default", "casual", message, {
        "runtime_injection": {"time_context": context},
        "creator_profile": {"id": 2, "persona_name": "Ava", "system_prompt": "Stay natural."},
    }, False, chat_history=[])
    return actual, captured["messages"][0]["content"]


def test_dual_clock_evening_for_ava_afternoon_for_customer():
    context = _context(datetime(2026, 8, 26, 21, 14, tzinfo=timezone.utc), "America/Chicago")
    assert context["avaTimezone"] == "America/New_York"
    assert context["avaDayOfWeek"] == "Wednesday"
    assert context["avaDaypart"] == "evening"
    assert context["customerTimezone"] == "America/Chicago"
    assert context["customerDaypart"] == "afternoon"


def test_dual_clock_afternoon_for_both():
    context = _context(datetime(2026, 8, 26, 19, 14, tzinfo=timezone.utc), "America/Chicago")
    assert context["avaDaypart"] == context["customerDaypart"] == "afternoon"


def test_ava_evening_with_unknown_customer_timezone_fails_closed():
    context = _context(datetime(2026, 8, 26, 21, 14, tzinfo=timezone.utc))
    assert context["avaDaypart"] == "evening"
    assert context["customerTimezone"] is None
    assert context["customerLocalTime"] is None
    assert context["customerDayOfWeek"] is None
    assert context["customerDaypart"] is None


@pytest.mark.parametrize("message", (
    "It's still afternoon here and I'm wrapping up work.",
    "What are you doing this afternoon?",
    "What are you doing this evening?",
    "What are you doing tonight?",
))
def test_provider_receives_authoritative_separate_temporal_grounding(message):
    context = _context(datetime(2026, 8, 26, 21, 14, tzinfo=timezone.utc), "America/Chicago")
    _, prompt = _capture_prompt(message, context)
    assert '"avaDaypart": "evening"' in prompt
    assert '"customerDaypart": "afternoon"' in prompt
    assert "describe only the customer" in prompt
    assert "interpret it against Ava's canonical clock" in prompt
    assert "canonical context wins" in prompt


def test_temporally_irrelevant_chat_does_not_require_artificial_time_reference():
    context = _context(datetime(2026, 8, 26, 21, 14, tzinfo=timezone.utc), "America/Chicago")
    reply, prompt = _capture_prompt("That made me laugh.", context)
    assert not any(word in reply.lower() for word in (
        "morning", "afternoon", "evening", "night", "tonight",
    ))
    assert "Do not force a time, weekday, or daypart reference" in prompt


def test_full_analysis_projects_persisted_generation_time_context():
    context = _context(datetime(2026, 8, 26, 21, 14, tzinfo=timezone.utc), "America/Chicago")
    latest = {"decision": {"rawDiagnostics": {"time_context": context}}}
    result = LiveControlledTestObserverService._time(
        latest, {"preference_state": {"timezone": "America/Chicago"}},
    )
    assert result["avaTimezone"] == "America/New_York"
    assert result["avaDaypart"] == "evening"
    assert result["customerTimezone"] == "America/Chicago"
    assert result["customerDaypart"] == "afternoon"
    assert result["source"] == "latest persisted generation decision"


def test_full_analysis_projects_turn_16_inferred_and_persisted_timezone():
    context = _context(
        datetime(2026, 8, 28, 0, 40, tzinfo=timezone.utc),
        "America/Chicago",
    )
    latest = {"decision": {"rawDiagnostics": {"time_context": context}}}
    prospect = {"preference_state": {
        "location": "Chicago", "timezone": "America/Chicago",
        "lastExtraction": {"locationTimezoneInference": {
            "location": "Chicago", "timezone": "America/Chicago",
            "resolved": True,
        }},
    }}
    result = LiveControlledTestObserverService._time(latest, prospect)
    assert result["avaTimezone"] == "America/New_York"
    assert result["customerTimezone"] == "America/Chicago"
    assert result["currentPersistedCustomerTimezone"] == "America/Chicago"
    assert result["avaLocalTime"] != result["customerLocalTime"]
    memory = LiveControlledTestObserverService._memory(None, prospect)
    assert memory["location"] == "Chicago"
    assert memory["timezone"] == "America/Chicago"
    assert memory["lastWrite"]["locationTimezoneInference"] == {
        "location": "Chicago", "timezone": "America/Chicago",
        "resolved": True,
    }


@pytest.mark.parametrize(("at", "message", "target", "assumed", "compatibility"), (
    (datetime(2026, 8, 29, 17, 23, tzinfo=timezone.utc),
     "How's your night going?", "AVA", "NIGHT", "MISMATCH"),
    (datetime(2026, 8, 29, 13, 0, tzinfo=timezone.utc),
     "Good evening", "AVA", "EVENING", "MISMATCH"),
    (datetime(2026, 8, 29, 22, 0, tzinfo=timezone.utc),
     "How's your morning?", "AVA", "MORNING", "MISMATCH"),
    (datetime(2026, 8, 30, 3, 0, tzinfo=timezone.utc),
     "How's your night?", "AVA", "NIGHT", "MATCH"),
    (datetime(2026, 8, 29, 13, 0, tzinfo=timezone.utc),
     "How's your morning?", "AVA", "MORNING", "MATCH"),
    (datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
     "I had a rough morning.", "CUSTOMER", None, "NOT_APPLICABLE"),
    (datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
     "Tonight I'm staying home.", "CUSTOMER", None, "NOT_APPLICABLE"),
    (datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
     "What are you doing later tonight?", "AVA", "NIGHT", "FUTURE_COMPATIBLE"),
    (datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
     "How's your day?", "GENERAL", None, "BROAD_COMPATIBLE"),
    (datetime(2026, 8, 29, 17, 0, tzinfo=timezone.utc),
     "That made me laugh.", "NONE", None, "NOT_APPLICABLE"),
))
def test_temporal_reference_matrix(at, message, target, assumed, compatibility):
    context = _context(at)
    result = AvaTemporalContextService.classify_customer_reference(message, context)
    assert result["customerTemporalReferenceTarget"] == target
    assert result["customerAssumedAvaDaypart"] == assumed
    assert result["temporalCompatibility"] == compatibility
    assert result["customerTimezone"] is None


def test_response_temporal_validation_rejects_false_claim_and_accepts_neutral_answer():
    context = _context(datetime(2026, 8, 29, 17, 23, tzinfo=timezone.utc))
    invalid = AvaTemporalContextService.evaluate_response(
        "How's your night going?", "my night's been great", context,
    )
    broad = AvaTemporalContextService.evaluate_response(
        "How's your night going?", "my day's been pretty chill", context,
    )
    neutral = AvaTemporalContextService.evaluate_response(
        "How's your night going?", "doing pretty good so far", context,
    )
    assert invalid["responseTemporalAlignmentSatisfied"] is False
    assert broad["responseTemporalAlignmentSatisfied"] is False
    assert neutral["responseTemporalAlignmentSatisfied"] is True
    assert neutral["temporalMismatchDetected"] is True


def test_future_routine_appointment_rejects_invented_recovery():
    context = _context(datetime(2026, 8, 29, 17, 23, tzinfo=timezone.utc))
    result = AvaTemporalContextService.evaluate_response(
        "Charlie has his yearly vet appointment Friday.",
        "recovering from vet day can be a full-time job sometimes", context,
    )
    assert result["customerEventTemporalRelation"] == "FUTURE_OR_PLANNED"
    assert result["inventedPostEventState"] is True
    assert result["responseTemporalAlignmentSatisfied"] is False


@pytest.mark.parametrize("response", (
    "That vet appointment always feels like a workout, huh? Definitely earned some chill time after.",
    "A quiet weekend after the appointment will be well deserved.",
))
def test_future_appointment_rejects_anticipatory_post_event_language(response):
    context = _context(datetime(2026, 8, 29, 17, 23, tzinfo=timezone.utc))
    result = AvaTemporalContextService.evaluate_response(
        "Charlie has his yearly vet appointment Friday.", response, context,
    )
    assert result["customerEventTemporalRelation"] == "FUTURE_OR_PLANNED"
    assert result["inventedPostEventState"] is True
    assert result["responseTemporalAlignmentSatisfied"] is False
