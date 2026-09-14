"""Isolated PostgreSQL durability certification for Telegram memory."""
import os
from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app import database
from app.database import get_db_connection
from app.testing.postgres_safety import require_isolated_test_database_url
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository
from app.services.conversational_memory_service import ConversationalMemoryService


def test_conversational_memory_survives_repository_and_service_reconstruction():
    test_database_url = os.getenv("TEST_DATABASE_URL")
    if not test_database_url:
        pytest.skip("TEST_DATABASE_URL is required for PostgreSQL integration tests")
    guarded_url = require_isolated_test_database_url(
        test_database_url, os.getenv("DATABASE_URL"),
    )
    original_url = database.DATABASE_URL
    database.close_database_pool()
    database.DATABASE_URL = guarded_url
    creator_profile_id = 2
    fanvue_account_id = 2
    telegram_user_id = 8_000_000_000 + int(uuid4().hex[:7], 16)
    at = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)
    repository = TelegramSalesProspectRepository()
    try:
        repository.observe(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
        )
        service = ConversationalMemoryService(repository=repository)
        for message in (
            "I'm in Chicago. My dog's name is Charlie and he's a golden retriever.",
            "I'm on a Foo Fighters kick lately.",
            "Charlie's vet appointment is Friday.",
        ):
            service.learn(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_user_id,
                message_text=message,
                observed_at=at,
            )

        restarted_repository = TelegramSalesProspectRepository()
        restarted_service = ConversationalMemoryService(
            repository=restarted_repository,
        )
        pet = restarted_service.learn(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
            message_text="How's Charlie?",
            observed_at=at,
        )
        music = restarted_service.learn(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_user_id,
            message_text="What have I told you about music?",
            observed_at=at,
        )
        row = restarted_repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        current = [item for item in row.preference_state["records"]
                   if item["status"] == "current"]
        assert {item["key"] for item in current} >= {
            "location", "timezone", "pet_name", "pet_type", "pet_breed",
            "music_artist_foo_fighters", "charlie_vet_appointment",
        }
        assert {item["key"] for item in pet["retrievedMemories"]} >= {
            "pet_name", "pet_type", "pet_breed",
        }
        assert [item["value"] for item in music["retrievedMemories"]] == [
            "Foo Fighters",
        ]
    finally:
        with get_db_connection() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "DELETE FROM telegram_sales_prospects "
                    "WHERE creator_profile_id=%s AND fanvue_account_id=%s "
                    "AND telegram_user_id=%s",
                    (creator_profile_id, fanvue_account_id, telegram_user_id),
                )
        database.close_database_pool()
        database.DATABASE_URL = original_url
