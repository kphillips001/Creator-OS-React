"""Isolated PostgreSQL certification for permanent reference retrieval."""

import os
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.models.creator_content_publication import CreatorContentPublication
from app.repositories.creator_content_publication_repository import CreatorContentPublicationRepository
from app.services.creator_content_reference_resolver import CreatorContentReferenceResolver
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_isolated_test_database_url


NAME = "20260919_144_creator_content_publications.sql"
ROLLBACK = Path(__file__).resolve().parents[1] / "migrations" / "rollback" / NAME
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def factory():
    url = require_isolated_test_database_url(TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"))
    with connect(url, row_factory=dict_row) as connection:
        yield connection


def test_indexed_full_history_resolution_has_no_age_cutoff():
    url = require_isolated_test_database_url(TEST_DATABASE_URL,
        os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"))
    with connect(url, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS public.creator_content_publications")
        connection.execute("DELETE FROM public.schema_migrations WHERE migration_name=%s", (NAME,))
    try:
        SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        repository = CreatorContentPublicationRepository(connection_factory=factory)
        with factory() as connection:
            row = connection.execute("SELECT id FROM public.creator_profiles ORDER BY id LIMIT 1").fetchone()
        creator = int(row["id"]) if row else 1
        channel = -100000 - uuid4().int % 100000
        now = datetime.now(UTC)
        values = (
            ("recent", 0, "mirror selfie black outfit"),
            ("hike", 14, "hiking picture mountain trail"),
            ("kayak", 180, "yellow kayak waterfall picture"),
        )
        for message_id, (label, days, document) in enumerate(values, 1):
            repository.save_successful(CreatorContentPublication(
                publication_id=str(uuid4()), creator_profile_id=creator,
                platform="telegram", destination="main", telegram_channel_id=channel,
                telegram_message_id=message_id, published_at=now-timedelta(days=days),
                generated_image_id=label, factual_visual_summary=document,
                intelligence_source="TEST", intelligence_version="v1", search_document=document))
        resolver = CreatorContentReferenceResolver(repository=repository)
        two_weeks = resolver.resolve(creator_profile_id=creator,
            inbound="that hiking picture you posted two weeks ago", current_timestamp=now)
        very_old = resolver.resolve(creator_profile_id=creator,
            inbound="that yellow kayak picture by the waterfall", current_timestamp=now)
        assert two_weeks.disposition == "RESOLVED"
        assert two_weeks.context["generatedImageId"] == "hike"
        assert very_old.disposition == "RESOLVED"
        assert very_old.context["generatedImageId"] == "kayak"
    finally:
        with connect(url, autocommit=True) as connection:
            connection.execute(ROLLBACK.read_text(encoding="utf-8"))
            connection.execute("DELETE FROM public.schema_migrations WHERE migration_name=%s", (NAME,))
