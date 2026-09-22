"""Isolated PostgreSQL certification for Telegram content-entry attribution."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.creator_content_entry_attribution import CreatorContentEntryAttribution, CreatorContentEntryEvent
from app.models.creator_content_publication import CreatorContentPublication
from app.repositories.creator_content_entry_attribution_repository import CreatorContentEntryAttributionRepository
from app.repositories.creator_content_publication_repository import CreatorContentPublicationRepository
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_isolated_test_database_url

ROOT = Path(__file__).resolve().parents[1]
M144 = "20260919_144_creator_content_publications.sql"
M145 = "20260919_145_creator_content_entry_attributions.sql"
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


def safe_url():
    return require_isolated_test_database_url(
        TEST_DATABASE_URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"))


@contextmanager
def factory():
    with connect(safe_url(), row_factory=dict_row) as connection:
        yield connection


def test_forward_idempotency_entry_history_no_backfill_and_rollback():
    url = safe_url()
    with connect(url, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS public.creator_content_entry_events")
        connection.execute("DROP TABLE IF EXISTS public.creator_content_entry_attributions")
        connection.execute("DROP TABLE IF EXISTS public.creator_content_publications")
        connection.execute("DELETE FROM public.schema_migrations WHERE migration_name IN (%s,%s)", (M144, M145))
    try:
        manager = SchemaManagerService(connection_factory=factory)
        manager.reconcile_one(M144)
        manager.reconcile_one(M145)
        manager.reconcile_one(M145)
        with factory() as connection:
            assert connection.execute("SELECT count(*) count FROM public.creator_content_entry_attributions").fetchone()["count"] == 0
            assert connection.execute("SELECT count(*) count FROM public.creator_content_entry_events").fetchone()["count"] == 0

        publications = CreatorContentPublicationRepository(connection_factory=factory)
        entries = CreatorContentEntryAttributionRepository(connection_factory=factory)
        publication_id = str(uuid4())
        publication = publications.save_successful(CreatorContentPublication(
            publication_id=publication_id, creator_profile_id=7, platform="telegram",
            destination="main", telegram_channel_id=-100777, telegram_message_id=777,
            published_at=datetime.now(UTC), generated_image_id="image-145",
            intelligence_source="TEST", intelligence_version="v1", search_document="entry test"))
        value = CreatorContentEntryAttribution(
            attribution_id=str(uuid4()), creator_profile_id=7, publication_id=publication.publication_id,
            token_digest="a" * 64, token_created_at=datetime.now(UTC))
        first = entries.create_or_get(value)
        second = entries.create_or_get(CreatorContentEntryAttribution(
            attribution_id=str(uuid4()), creator_profile_id=7, publication_id=publication.publication_id,
            token_digest="b" * 64, token_created_at=datetime.now(UTC)))
        assert first.attribution_id == second.attribution_id
        assert first.token_digest == second.token_digest == "a" * 64

        event = CreatorContentEntryEvent(
            entry_event_id=str(uuid4()), attribution_id=first.attribution_id,
            creator_profile_id=7, publication_id=publication.publication_id,
            telegram_user_id=101, telegram_chat_id=101, inbound_telegram_message_id=900,
            observed_at=datetime.now(UTC))
        observed = entries.observe(event)
        repeated = entries.observe(CreatorContentEntryEvent(
            entry_event_id=str(uuid4()), attribution_id=first.attribution_id,
            creator_profile_id=7, publication_id=publication.publication_id,
            telegram_user_id=101, telegram_chat_id=101, inbound_telegram_message_id=900,
            observed_at=datetime.now(UTC)))
        entries.observe(CreatorContentEntryEvent(
            entry_event_id=str(uuid4()), attribution_id=first.attribution_id,
            creator_profile_id=7, publication_id=publication.publication_id,
            telegram_user_id=202, telegram_chat_id=202, inbound_telegram_message_id=901,
            observed_at=datetime.now(UTC)))
        assert observed.entry_event_id == repeated.entry_event_id
        assert len(entries.list_events(creator_profile_id=7, telegram_user_id=101)) == 1
        assert len(entries.list_events(creator_profile_id=7, telegram_user_id=202)) == 1
        history = entries.list_entry_history(creator_profile_id=7, telegram_user_id=101,
            telegram_chat_id=101, limit=5)
        assert len(history) == 1
        assert history[0]["publicationId"] == publication.publication_id
        assert history[0]["provenanceMethod"] == "TELEGRAM_DIRECT_CHAT_DRAFT"
        with factory() as connection:
            assert connection.execute("SELECT count(*) count FROM public.creator_content_entry_attributions").fetchone()["count"] == 1
            assert connection.execute("SELECT count(*) count FROM public.creator_content_entry_events").fetchone()["count"] == 2
    finally:
        with connect(url, autocommit=True) as connection:
            connection.execute((ROOT / "migrations" / "rollback" / M145).read_text(encoding="utf-8"))
            connection.execute((ROOT / "migrations" / "rollback" / M144).read_text(encoding="utf-8"))
            connection.execute("DELETE FROM public.schema_migrations WHERE migration_name IN (%s,%s)", (M144, M145))
            assert connection.execute("SELECT to_regclass('public.creator_content_entry_events')").fetchone()[0] is None
            assert connection.execute("SELECT to_regclass('public.creator_content_entry_attributions')").fetchone()[0] is None