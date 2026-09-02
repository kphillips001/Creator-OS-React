"""Isolated PostgreSQL certification for Turn 16 location memory."""
from __future__ import annotations

import os
from datetime import datetime

import pytest

from app.repositories.telegram_sales_prospect_repository import (
    TelegramSalesProspectRepository,
)
from app.services.conversational_memory_service import ConversationalMemoryService
from app.test_private_chat_settlement_postgres import connection_factory, fixture


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required"
)


def test_turn_16_location_and_timezone_survive_real_repository_reconstruction():
    values = fixture()
    repository = TelegramSalesProspectRepository(
        connection_factory=connection_factory
    )
    message = (
        "It’s still afternoon here in Chicago — what are you up to this evening?"
    )
    learned = ConversationalMemoryService(repository=repository).learn(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
        telegram_chat_id=values["telegram"],
        message_text=message,
    )
    assert learned["timezone"] == "America/Chicago"
    assert learned["memoryDiagnostics"]["locationTimezoneInference"] == {
        "location": "Chicago", "timezone": "America/Chicago", "resolved": True,
    }

    persisted = repository.get(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    assert persisted["location"] == "Chicago"
    assert persisted["timezone"] == "America/Chicago"

    reconstructed = ConversationalMemoryService(
        repository=TelegramSalesProspectRepository(
            connection_factory=connection_factory
        )
    )
    recalled = reconstructed.learn(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
        telegram_chat_id=values["telegram"],
        message_text="Where did I tell you I live?",
    )
    assert recalled["location"] == "Chicago"
    assert recalled["timezone"] == "America/Chicago"
    assert {item["key"] for item in recalled["retrievedMemories"]} >= {
        "location", "timezone",
    }


def test_turn_18_retrieves_persisted_chicago_without_new_location_disclosure():
    values = fixture()
    repository = TelegramSalesProspectRepository(
        connection_factory=connection_factory
    )
    ConversationalMemoryService(repository=repository).learn(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
        telegram_chat_id=values["telegram"],
        message_text="I'm in Chicago.",
    )
    reconstructed = ConversationalMemoryService(
        repository=TelegramSalesProspectRepository(
            connection_factory=connection_factory
        )
    )
    result = reconstructed.learn(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
        telegram_chat_id=values["telegram"],
        message_text="I might get outside this weekend if the weather’s decent.",
    )
    diagnostics = result["memoryDiagnostics"]
    assert result["timezone"] == "America/Chicago"
    assert diagnostics["retrievalAttempted"] is True
    assert diagnostics["extractedThisTurn"] == 0
    assert diagnostics["persistedThisTurn"] == 0
    assert diagnostics["retrievedCount"] >= 1
    assert any(item["key"] == "location" and item["value"] == "Chicago"
               for item in result["retrievedMemories"])


def test_turn_20_pet_memory_survives_reconstruction_retrieves_selectively_and_corrects():
    values = fixture()
    repository = TelegramSalesProspectRepository(connection_factory=connection_factory)
    service = ConversationalMemoryService(repository=repository)
    learned = service.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="I've got a golden retriever named Charlie. He pretty much owns the house 😂",
    )
    assert learned["memoryDiagnostics"]["extractedThisTurn"] >= 2
    persisted = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    assert persisted["pet"] == {"name": "Charlie", "breed": "golden retriever"}

    reconstructed = ConversationalMemoryService(repository=
        TelegramSalesProspectRepository(connection_factory=connection_factory))
    relevant = reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="I need to take him to the vet.",
    )
    assert {item["key"] for item in relevant["retrievedMemories"]} >= {
        "pet_name", "pet_breed",
    }
    unrelated = reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="What should I eat for dinner?",
    )
    assert unrelated["retrievedMemories"] == []

    reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="Actually his name is Max, not Charlie.",
    )
    final_service = ConversationalMemoryService(repository=
        TelegramSalesProspectRepository(connection_factory=connection_factory))
    final_service.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="Charlie's actually a lab, not a golden retriever.",
    )
    final = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    assert final["pet"]["name"] == "Max"
    assert final["pet"]["breed"] == "lab"
    assert sum(record["status"] == "superseded" for record in final["records"]) >= 2


def test_turn_22_future_event_survives_reconstruction_reschedule_and_cancellation():
    values = fixture()
    repository = TelegramSalesProspectRepository(connection_factory=connection_factory)
    service = ConversationalMemoryService(repository=repository)
    at = datetime.fromisoformat("2026-08-27T20:29:29-05:00")
    for message in (
        "I'm in Chicago.",
        "I've got a golden retriever named Charlie.",
        "He's got a vet appointment Friday and somehow he always knows when we're going 😂",
    ):
        learned = service.learn(
            creator_profile_id=values["creator"], fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
            message_text=message, observed_at=at,
        )
    assert learned["memoryDiagnostics"]["extractedThisTurn"] == 1
    persisted = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    event = next(record for record in persisted["records"]
                 if record["category"] == "event" and record["status"] == "current")
    assert event["value"]["subject"] == "Charlie"
    assert event["value"]["scheduledFor"] == "2026-08-28T12:00:00-05:00"
    assert event["metadata"]["timezone"] == "America/Chicago"

    reconstructed = ConversationalMemoryService(repository=
        TelegramSalesProspectRepository(connection_factory=connection_factory))
    relevant = reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="What's going on Friday again?", observed_at=at,
    )
    assert any(item["category"] == "event" for item in relevant["retrievedMemories"])
    unrelated = reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="What music are you listening to?", observed_at=at,
    )
    assert not any(item["category"] == "event"
                   for item in unrelated["retrievedMemories"])

    reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="Actually his appointment got moved to Monday.", observed_at=at,
    )
    after_move = TelegramSalesProspectRepository(
        connection_factory=connection_factory).get(
            creator_profile_id=values["creator"], fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"],
        ).preference_state
    current = [record for record in after_move["records"]
               if record["category"] == "event" and record["status"] == "current"]
    assert len(current) == 1
    assert current[0]["value"]["scheduledFor"] == "2026-08-31T12:00:00-05:00"

    final_service = ConversationalMemoryService(repository=
        TelegramSalesProspectRepository(connection_factory=connection_factory))
    final_service.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="Vet appointment got canceled.", observed_at=at,
    )
    final = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    current = [record for record in final["records"]
               if record["category"] == "event" and record["status"] == "current"]
    assert len(current) == 1
    assert current[0]["value"]["status"] == "cancelled"
    assert sum(record["category"] == "event" and record["status"] == "superseded"
               for record in final["records"]) == 2


def test_turn26_temporal_overlap_survives_restart_and_weak_plan_is_not_persisted():
    values = fixture()
    repository = TelegramSalesProspectRepository(connection_factory=connection_factory)
    at = datetime.fromisoformat("2026-08-27T20:29:29-05:00")
    service = ConversationalMemoryService(repository=repository)
    for message in (
        "I'm in Chicago.",
        "I've got a golden retriever named Charlie.",
        "He's got a vet appointment Friday and somehow he always knows when we're going 😂",
    ):
        service.learn(
            creator_profile_id=values["creator"], fanvue_account_id=values["account"],
            telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
            message_text=message, observed_at=at,
        )
    reconstructed = ConversationalMemoryService(repository=
        TelegramSalesProspectRepository(connection_factory=connection_factory))
    result = reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="I'm probably just gonna take it easy tomorrow after work.",
        observed_at=at,
    )
    diagnostics = result["memoryDiagnostics"]
    assert diagnostics["extractedThisTurn"] == 0
    assert diagnostics["persistedThisTurn"] == 0
    assert diagnostics["eventPersistence"]["rejected"] is True
    assert diagnostics["temporalEventRecall"]["reason"] == "RESOLVED_TEMPORAL_OVERLAP"
    assert diagnostics["continuityGuidance"]["priority"] == "HIGH"
    assert diagnostics["continuityGuidance"]["strongestMemory"]["key"] == (
        "charlie_vet_appointment"
    )
    retrieved = [record for record in result["retrievedMemories"]
                 if record["category"] == "event"]
    assert len(retrieved) == 1
    assert retrieved[0]["value"]["subject"] == "Charlie"
    persisted = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    current_events = [record for record in persisted["records"]
                      if record["category"] == "event" and record["status"] == "current"]
    assert len(current_events) == 1
    assert persisted["location"] == "Chicago"
    assert persisted["timezone"] == "America/Chicago"
    assert persisted["pet"]["name"] == "Charlie"
    assert persisted["pet"]["breed"] == "golden retriever"

    reconstructed.learn(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"], telegram_chat_id=values["telegram"],
        message_text="I might have a job interview Friday.", observed_at=at,
    )
    final = repository.get(
        creator_profile_id=values["creator"], fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    ).preference_state
    interview = next(record for record in final["records"]
                     if record["category"] == "event"
                     and (record["value"] or {}).get("event") == "job interview")
    assert interview["value"]["temporalCertainty"] == "TENTATIVE"
