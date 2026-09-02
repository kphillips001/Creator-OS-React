from datetime import datetime, timezone

import pytest

from app.services.commercial_objection_service import CommercialObjectionService
from app.services.conversational_memory_domain_classifier import ConversationalMemoryDomainClassifier
from app.services.conversational_memory_service import ConversationalMemoryService


TURN_22 = "He's got a vet appointment Friday and somehow he always knows when we're going 😂"
TURN_22_AT = datetime.fromisoformat("2026-08-27T20:29:29-05:00")


def _base_state():
    state = ConversationalMemoryService._normalize_state({})
    records = []
    records.extend(ConversationalMemoryService.extract_records(
        "I'm in Chicago.", observed_at=TURN_22_AT,
    ))
    records.extend(ConversationalMemoryService.extract_records(
        "I've got a golden retriever named Charlie.", observed_at=TURN_22_AT,
    ))
    ConversationalMemoryService._merge_records(state, records)
    return state


def test_exact_turn22_extracts_linked_chicago_future_event_and_retrieves_pet():
    state = _base_state()
    active = [record for record in state["records"] if record["status"] == "current"]
    classification = ConversationalMemoryDomainClassifier.classify(
        TURN_22, active_records=active,
    )
    assert classification.domains >= {"event", "pet"}
    records = ConversationalMemoryService.extract_records(
        TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
        active_records=active,
    )
    events = [record for record in records if record["category"] == "event"]
    assert len(events) == 1
    event = events[0]
    assert event["value"] == {
        "subject": "Charlie",
        "event": "vet appointment",
        "summary": "Charlie has vet appointment",
        "originalTemporalText": "friday",
        "scheduledFor": "2026-08-28T12:00:00-05:00",
        "resolutionPrecision": "DATE",
        "temporalCertainty": "STATED",
        "status": "upcoming",
        "completionVerified": False,
    }
    assert event["metadata"] == {
        "temporal": True, "timezone": "America/Chicago",
        "timezoneSource": "CUSTOMER_TIMEZONE", "subjectDomain": "pet",
    }
    ConversationalMemoryService._merge_records(state, records)
    result = ConversationalMemoryService.retrieve(state, TURN_22, now=TURN_22_AT)
    assert {record["key"] for record in result["retrievedMemories"]} >= {
        "pet_name", "pet_breed", "charlie_vet_appointment",
    }
    assert state["location"] == "Chicago"
    assert state["timezone"] == "America/Chicago"
    assert state["pet"]["name"] == "Charlie"
    assert state["pet"]["breed"] == "golden retriever"
    assert CommercialObjectionService().evaluate(
        message=TURN_22,
    ).objection_type.value == "NONE"


def test_exact_turn22_learn_reports_persistence_and_event_diagnostics():
    class Prospect:
        preference_state = _base_state()

    class Repository:
        state = Prospect.preference_state

        def get(self, **_):
            item = Prospect(); item.preference_state = self.state; return item

        def merge_conversational_memory(self, *, values, **_):
            self.state = values
            item = Prospect(); item.preference_state = values; return item

    repository = Repository()
    before_pet_count = sum(record["category"] == "pet"
                           for record in repository.state["records"])
    result = ConversationalMemoryService(repository=repository).learn(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=1,
        telegram_chat_id=1, message_text=TURN_22, observed_at=TURN_22_AT,
    )
    diagnostics = result["memoryDiagnostics"]
    assert diagnostics["extractedThisTurn"] == 1
    assert diagnostics["persistedThisTurn"] == 1
    assert diagnostics["eventsExtractedThisTurn"][0]["subject"] == "Charlie"
    assert diagnostics["eventsExtractedThisTurn"][0]["originalTemporalText"] == "friday"
    assert diagnostics["eventsExtractedThisTurn"][0]["scheduledFor"] == "2026-08-28T12:00:00-05:00"
    assert diagnostics["persistenceSource"] == "telegram_sales_prospects.preference_state"
    assert diagnostics["retrievalSource"] == "telegram_sales_prospects.preference_state"
    assert sum(record["category"] == "pet"
               for record in repository.state["records"]) == before_pet_count


@pytest.mark.parametrize("message, subject, event", (
    ("Charlie has a vet appointment Friday.", "Charlie", "vet appointment"),
    ("My dog gets groomed tomorrow.", "Charlie", "groomed"),
    ("My sister is visiting next weekend.", "customer's sister", "visiting"),
    ("I have an interview Tuesday.", "customer", "interview"),
    ("I have a doctor appointment Monday.", "customer", "doctor appointment"),
    ("We're going camping next month.", "customer", "going camping"),
    ("I'm flying to Denver next Thursday.", "customer", "flying to Denver"),
    ("My birthday is Saturday.", "customer", "birthday"),
    ("I've got a concert next weekend.", "customer", "concert"),
))
def test_generalized_future_event_grammar(message, subject, event):
    state = _base_state()
    records = ConversationalMemoryService.extract_records(
        message, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
        active_records=state["records"],
    )
    extracted = [record for record in records if record["category"] == "event"]
    assert len(extracted) == 1
    assert extracted[0]["value"]["subject"] == subject
    assert extracted[0]["value"]["event"] == event.lower()
    assert extracted[0]["value"]["scheduledFor"]


@pytest.mark.parametrize("message", (
    "Friday is my favorite song.",
    "That movie comes out Friday.",
    "I hate Mondays.",
    "Charlie Brown is funny.",
    "Vet bills are expensive.",
    "I might maybe do something someday.",
    "Tomorrow Never Knows is a great song.",
    "My dog acts like every day is Friday.",
))
def test_future_event_false_positive_matrix(message):
    assert not any(record["category"] == "event"
                   for record in ConversationalMemoryService.extract_records(
                       message, observed_at=TURN_22_AT,
                       customer_timezone="America/Chicago",
                       active_records=_base_state()["records"],
                   ))


@pytest.mark.parametrize("message", (
    "How's Charlie doing?",
    "Is he ready for Friday? 😂",
    "What's Charlie up to this weekend?",
    "Hope the vet visit goes okay.",
    "Any plans Friday?",
    "How did his appointment go?",
))
def test_future_event_retrieval_matrix(message):
    state = _base_state()
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
            active_records=state["records"],
        ),
    )
    result = ConversationalMemoryService.retrieve(state, message, now=TURN_22_AT)
    assert any(record["category"] == "event"
               and record["value"]["event"] == "vet appointment"
               for record in result["retrievedMemories"])


@pytest.mark.parametrize("message", (
    "What music are you listening to?", "I'm hungry.",
    "That movie was hilarious.", "What are you wearing?",
    "Work was crazy today.", "Do you like hiking?",
))
def test_unrelated_conversation_omits_future_event(message):
    state = _base_state()
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
            active_records=state["records"],
        ),
    )
    result = ConversationalMemoryService.retrieve(state, message, now=TURN_22_AT)
    assert not any(record["category"] == "event"
                   for record in result["retrievedMemories"])


def test_reschedule_and_cancellation_preserve_history_but_remove_active_schedule():
    state = _base_state()
    first = ConversationalMemoryService.extract_records(
        TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
        active_records=state["records"],
    )
    ConversationalMemoryService._merge_records(state, first)
    moved = ConversationalMemoryService.extract_records(
        "Actually his appointment got moved to Monday.", observed_at=TURN_22_AT,
        customer_timezone="America/Chicago", active_records=state["records"],
    )
    ConversationalMemoryService._merge_records(state, moved)
    current = [record for record in state["records"]
               if record["category"] == "event" and record["status"] == "current"]
    assert len(current) == 1
    assert current[0]["value"]["scheduledFor"] == "2026-08-31T12:00:00-05:00"
    assert any(record["category"] == "event" and record["status"] == "superseded"
               for record in state["records"])
    cancelled = ConversationalMemoryService.extract_records(
        "Vet appointment got canceled.", observed_at=TURN_22_AT,
        customer_timezone="America/Chicago", active_records=state["records"],
    )
    ConversationalMemoryService._merge_records(state, cancelled)
    current = [record for record in state["records"]
               if record["category"] == "event" and record["status"] == "current"]
    assert len(current) == 1
    assert current[0]["value"]["status"] == "cancelled"
    assert ConversationalMemoryService.retrieve(
        state, "Any plans Monday?", now=TURN_22_AT,
    )["retrievedMemories"] == []


def test_elapsed_event_remains_planned_not_verified_completed():
    state = _base_state()
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
            active_records=state["records"],
        ),
    )
    ConversationalMemoryService._refresh_event_lifecycle(
        state, datetime.fromisoformat("2026-08-30T12:00:00-05:00"),
    )
    event = next(record for record in state["records"] if record["category"] == "event")
    assert event["value"]["status"] == "past"
    assert event["value"]["completionVerified"] is False


def test_temporal_only_correction_supersedes_without_duplicate_active_event():
    state = _base_state()
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            TURN_22, observed_at=TURN_22_AT, customer_timezone="America/Chicago",
            active_records=state["records"],
        ),
    )
    correction = ConversationalMemoryService.extract_records(
        "It's actually Saturday, not Friday.", observed_at=TURN_22_AT,
        customer_timezone="America/Chicago", active_records=state["records"],
    )
    ConversationalMemoryService._merge_records(state, correction)
    current = [record for record in state["records"]
               if record["category"] == "event" and record["status"] == "current"]
    assert len(current) == 1
    assert current[0]["value"]["scheduledFor"] == "2026-08-29T12:00:00-05:00"
