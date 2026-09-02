from datetime import datetime, timezone

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService


TURN_20 = "I've got a golden retriever named Charlie. He pretty much owns the house 😂"


@pytest.mark.parametrize("message, expected", (
    (TURN_20, {"pet_name": "Charlie", "pet_breed": "golden retriever"}),
    ("I have a dog named Charlie.", {"pet_name": "Charlie", "pet_type": "dog"}),
    ("My dog Charlie is a golden retriever.", {"pet_name": "Charlie", "pet_breed": "golden retriever"}),
    ("Charlie is my golden retriever.", {"pet_name": "Charlie", "pet_breed": "golden retriever"}),
    ("I have a golden retriever. His name is Charlie.", {"pet_name": "Charlie", "pet_breed": "golden retriever"}),
))
def test_bounded_pet_extraction(message, expected):
    records = ConversationalMemoryService.extract_records(message)
    actual = {record["key"]: record["value"] for record in records
              if record["category"] == "pet"}
    assert actual == expected


@pytest.mark.parametrize("message", (
    "That guy is a dog.",
    "I'm dog tired.",
    "Golden retriever energy 😂",
    "Charlie Brown is funny.",
    "I watched a dog video.",
    "My team is the Golden Retrievers.",
    "That app is called Charlie.",
    "I want a dog someday.",
))
def test_pet_false_positive_matrix(message):
    assert not any(record["category"] == "pet"
                   for record in ConversationalMemoryService.extract_records(message))


def _pet_state():
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(TURN_20),
    )
    return state


@pytest.mark.parametrize("message", (
    "My dog was being ridiculous this morning.",
    "Pets make the house feel less empty.",
    "I need to take him to the vet.",
    "He stole my spot on the couch again.",
    "Do you like dogs?",
))
def test_pet_relevant_turn_retrieves_current_pet_facts(message):
    result = ConversationalMemoryService.retrieve(_pet_state(), message)
    assert {record["key"] for record in result["retrievedMemories"]} >= {
        "pet_name", "pet_breed",
    }
    assert "pet" in result["memoryDiagnostics"]["semanticDomains"]


@pytest.mark.parametrize("message", (
    "What are you doing tonight?",
    "I might go hiking this weekend.",
    "The weather looks rough tomorrow.",
    "I've been listening to music all night.",
    "What should I eat for dinner?",
))
def test_unrelated_turn_does_not_retrieve_pet_facts(message):
    assert ConversationalMemoryService.retrieve(
        _pet_state(), message,
    )["retrievedMemories"] == []


def test_pet_corrections_supersede_prior_values():
    state = _pet_state()
    records = ConversationalMemoryService.extract_records(
        "Actually his name is Max, not Charlie.",
    ) + ConversationalMemoryService.extract_records(
        "Charlie's actually a lab, not a golden retriever.",
    )
    ConversationalMemoryService._merge_records(state, records)

    current = {record["key"]: record["value"] for record in state["records"]
               if record["status"] == "current" and record["category"] == "pet"}
    assert current == {"pet_name": "Max", "pet_breed": "lab"}
    assert {(record["key"], record["value"]) for record in state["records"]
            if record["status"] == "superseded" and record["category"] == "pet"} >= {
        ("pet_name", "Charlie"), ("pet_breed", "golden retriever"),
    }


def test_exact_turn20_learning_reports_two_persisted_facts_without_corruption():
    class Prospect:
        preference_state = {"location": "Chicago", "timezone": "America/Chicago"}

    class Repository:
        state = Prospect.preference_state

        def get(self, **_):
            item = Prospect()
            item.preference_state = self.state
            return item

        def merge_conversational_memory(self, *, values, **_):
            self.state = values
            item = Prospect()
            item.preference_state = values
            return item

    repository = Repository()
    result = ConversationalMemoryService(repository=repository).learn(
        creator_profile_id=2, fanvue_account_id="ava", telegram_user_id=1,
        telegram_chat_id=1, message_text=TURN_20,
        observed_at=datetime(2026, 8, 27, tzinfo=timezone.utc),
    )
    diagnostics = result["memoryDiagnostics"]
    assert diagnostics["extractedThisTurn"] >= 2
    assert diagnostics["persistedThisTurn"] >= 2
    assert repository.state["pet"] == {
        "name": "Charlie", "breed": "golden retriever",
    }
    assert repository.state["location"] == "Chicago"
    assert repository.state["timezone"] == "America/Chicago"
