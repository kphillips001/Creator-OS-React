from datetime import datetime, timezone

import pytest

from app.services.conversational_memory_service import ConversationalMemoryService


AT = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


def values(message, **kwargs):
    return {(record["category"], record["key"]): record["value"]
            for record in ConversationalMemoryService.extract_records(
                message, observed_at=AT, **kwargs)}


def test_exact_chicago_possessive_pet_turn_extracts_owned_normalized_memory():
    records = ConversationalMemoryService.extract_records(
        "I'm in Chicago. My dog's name is Charlie and he's a golden retriever.",
        observed_at=AT,
    )
    actual = {(item["category"], item["key"]): item for item in records}
    assert actual[("fact", "location")]["value"] == "Chicago"
    assert actual[("fact", "timezone")]["value"] == "America/Chicago"
    assert actual[("fact", "timezone")]["source"] == "deterministic_location_inference"
    assert actual[("pet", "pet_name")]["value"] == "Charlie"
    assert actual[("pet", "pet_type")]["value"] == "dog"
    assert actual[("pet", "pet_breed")]["value"] == "golden retriever"
    assert actual[("entity", "charlie")]["value"] == {
        "name": "Charlie", "type": "dog", "breed": "golden retriever",
        "relationship": "customer's dog",
    }


@pytest.mark.parametrize("message", (
    "My dog's name is Charlie.",
    "My dog's name is Charlie and he's a golden retriever.",
    "My dog's name is Charlie; he's a golden retriever.",
    "My dog is named Charlie.",
    "My dog Charlie is a golden retriever.",
    "I have a golden retriever named Charlie.",
    "I've got a golden retriever named Charlie.",
    "Charlie is my golden retriever.",
))
def test_positive_pet_ownership_matrix(message):
    extracted = values(message)
    assert extracted[("pet", "pet_name")] == "Charlie"
    assert extracted[("pet", "pet_type")] == "dog"


@pytest.mark.parametrize("message", (
    "My friend has a dog named Charlie.",
    "My sister's dog is Charlie.",
    "Ava has a dog named JoJo.",
    "There's a golden retriever named Charlie next door.",
    "I met a dog named Charlie.",
    "My dogs are Charlie and Max and he's a golden retriever.",
))
def test_negative_and_ambiguous_pet_ownership_matrix(message):
    assert not any(category in {"pet", "entity"}
                   for category, _ in values(message))


@pytest.mark.parametrize("message", (
    "I'm on a Foo Fighters kick lately.",
    "I've been listening to Foo Fighters way too much 😂",
    "I love Foo Fighters.",
    "Foo Fighters are probably my favorite band.",
    "I'm really into Foo Fighters lately.",
))
def test_named_music_preference_matrix(message):
    assert values(message)[("preference", "music_artist_foo_fighters")] == "Foo Fighters"


def test_production_music_regression_retains_named_artist_not_anaphora():
    records = ConversationalMemoryService.extract_records(
        "I've been on a Foo Fighters kick lately. Been listening to them way too much 😂",
        observed_at=AT,
    )
    music = [item for item in records
             if item.get("metadata", {}).get("kind") == "artist"]
    assert [(item["key"], item["value"]) for item in music] == [
        ("music_artist_foo_fighters", "Foo Fighters")]


@pytest.mark.parametrize("bad", (
    "them", "them way too much", "way too much", "it", "that", "those guys", "😂",
))
def test_normalized_artist_validation_fails_closed(bad):
    record = ConversationalMemoryService._record(
        "preference", "music_artist_bad", bad, "evidence", AT, .99,
        {"domain": "music", "kind": "artist"},
    )
    valid, rejected = ConversationalMemoryService._validate_extracted_records([record])
    assert valid == []
    assert rejected[0]["reason"] in {
        "NO_ALPHANUMERIC_VALUE", "ANAPHORIC_OR_TRAILING_FRAGMENT",
        "INVALID_ARTIST_FRAGMENT",
    }


def test_repeated_pet_and_music_disclosures_converge_without_current_duplicates():
    state = ConversationalMemoryService._normalize_state({})
    for message in (
        "My dog's name is Charlie.",
        "My dog Charlie is a golden retriever.",
        "I'm on a Foo Fighters kick lately.",
        "I love Foo Fighters.",
    ):
        ConversationalMemoryService._merge_records(
            state, ConversationalMemoryService.extract_records(message, observed_at=AT),
        )
    current = [item for item in state["records"] if item["status"] == "current"]
    assert sum(item["key"] == "pet_name" for item in current) == 1
    assert sum(item["key"] == "pet_type" for item in current) == 1
    assert sum(item["key"] == "pet_breed" for item in current) == 1
    assert sum(item["key"] == "charlie" for item in current) == 1
    assert sum(item["key"] == "music_artist_foo_fighters" for item in current) == 1


def test_bounded_location_music_and_pet_cessation_supersede_current_values():
    state = ConversationalMemoryService._normalize_state({})
    seed = ("I'm in Chicago. My dog's name is Charlie and he's a golden retriever. "
            "I'm on a Foo Fighters kick lately.")
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(seed, observed_at=AT),
    )
    for correction in (
        "I don't live in Chicago anymore. I moved to Denver.",
        "I don't really listen to Foo Fighters anymore.",
        "My dog isn't Charlie — Charlie is my brother's dog.",
    ):
        ConversationalMemoryService._merge_records(
            state, ConversationalMemoryService.extract_records(
                correction, observed_at=AT, active_records=state["records"]),
        )
    current = [item for item in state["records"] if item["status"] == "current"]
    assert next(item for item in current if item["key"] == "location")["value"] == "Denver"
    assert not any(item["key"] == "music_artist_foo_fighters" for item in current)
    assert not any(item["category"] in {"pet", "entity"} for item in current)


def test_future_event_and_selective_retrieval_regression():
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            "My dog's name is Charlie and he's a golden retriever.", observed_at=AT),
    )
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            "Charlie's vet appointment is Friday.", observed_at=AT,
            customer_timezone="America/Chicago", active_records=state["records"]),
    )
    assert any(item["category"] == "event" for item in state["records"])
    assert any(item["key"] == "pet_name" for item in
               ConversationalMemoryService.retrieve(state, "How's Charlie?")["retrievedMemories"])
    assert ConversationalMemoryService.retrieve(state, "Hey")["retrievedMemories"] == []


def test_music_selective_retrieval():
    state = ConversationalMemoryService._normalize_state({})
    ConversationalMemoryService._merge_records(
        state, ConversationalMemoryService.extract_records(
            "I'm on a Foo Fighters kick lately.", observed_at=AT),
    )
    result = ConversationalMemoryService.retrieve(
        state, "What have I told you about music?", now=AT)
    assert [item["value"] for item in result["retrievedMemories"]] == ["Foo Fighters"]


@pytest.mark.parametrize("graduated_mapping_id", (None, 42))
def test_mapped_and_unmapped_prospects_have_identical_learning_semantics(
        graduated_mapping_id):
    class Prospect:
        preference_state = {}

    class Repository:
        state = {}

        def get(self, **_):
            item = Prospect()
            item.preference_state = self.state
            item.graduated_mapping_id = graduated_mapping_id
            return item

        def merge_conversational_memory(self, *, values, **_):
            self.state = values
            return self.get()

    repository = Repository()
    ConversationalMemoryService(repository=repository).learn(
        creator_profile_id=2, fanvue_account_id=2, telegram_user_id=123,
        telegram_chat_id=123,
        message_text=("I'm in Chicago. My dog's name is Charlie and he's a "
                      "golden retriever. I'm on a Foo Fighters kick lately."),
        observed_at=AT,
    )
    current = {item["key"]: item["value"] for item in repository.state["records"]
               if item["status"] == "current"}
    assert current["location"] == "Chicago"
    assert current["pet_name"] == "Charlie"
    assert current["pet_breed"] == "golden retriever"
    assert current["music_artist_foo_fighters"] == "Foo Fighters"
