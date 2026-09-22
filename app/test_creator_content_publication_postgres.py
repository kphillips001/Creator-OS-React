"""Isolated PostgreSQL forward/rollback certification for publication memory."""

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
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_isolated_test_database_url


NAME = "20260919_144_creator_content_publications.sql"
ROLLBACK = Path(__file__).resolve().parents[1] / "migrations" / "rollback" / NAME
TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not TEST_DATABASE_URL, reason="TEST_DATABASE_URL required")


@contextmanager
def factory():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, row_factory=dict_row) as connection:
        yield connection


def test_forward_idempotency_permanent_search_and_rollback():
    url = require_isolated_test_database_url(
        TEST_DATABASE_URL, os.getenv("CREATOR_OS_PRODUCTION_DATABASE_URL") or os.getenv("DATABASE_URL"),
    )
    with connect(url, autocommit=True) as connection:
        connection.execute("DROP TABLE IF EXISTS public.creator_content_publications")
        connection.execute("DELETE FROM public.schema_migrations WHERE migration_name=%s", (NAME,))
    try:
        SchemaManagerService(connection_factory=factory).reconcile_one(NAME)
        repository = CreatorContentPublicationRepository(connection_factory=factory)
        creator_id = 1
        with factory() as connection:
            row = connection.execute("SELECT id FROM public.creator_profiles ORDER BY id LIMIT 1").fetchone()
            if row:
                creator_id = int(row["id"])
        channel = -100000 - (uuid4().int % 100000)
        ages = (timedelta(hours=13), timedelta(weeks=2), timedelta(days=180))
        for index, age in enumerate(ages, start=1):
            value = CreatorContentPublication(
                publication_id=str(uuid4()), creator_profile_id=creator_id,
                platform="telegram", destination="main", telegram_channel_id=channel,
                telegram_message_id=index, published_at=datetime.now(UTC) - age,
                generated_image_id=f"image-{index}", published_caption=f"archive dress {index}",
                factual_visual_summary="red dress balcony", intelligence_source="TEST_SNAPSHOT",
                intelligence_version="v1", search_document=f"archive red dress balcony {index}",
            )
            assert repository.save_successful(value).telegram_message_id == index
        duplicate = CreatorContentPublication(
            publication_id=str(uuid4()), creator_profile_id=creator_id,
            platform="telegram", destination="main", telegram_channel_id=channel,
            telegram_message_id=1, published_at=datetime.now(UTC), generated_image_id="duplicate",
            intelligence_source="TEST", intelligence_version="v1", search_document="duplicate",
        )
        assert repository.save_successful(duplicate).generated_image_id == "image-1"
        results = repository.search(creator_profile_id=creator_id, query="red dress", limit=2)
        assert len(results) == 2
        assert results[0].published_at > results[1].published_at
        all_results = repository.search(creator_profile_id=creator_id, query="red dress", limit=50)
        assert {item.telegram_message_id for item in all_results} == {1, 2, 3}
    finally:
        with connect(url, autocommit=True) as connection:
            connection.execute(ROLLBACK.read_text(encoding="utf-8"))
            connection.execute("DELETE FROM public.schema_migrations WHERE migration_name=%s", (NAME,))
            assert connection.execute("SELECT to_regclass('public.creator_content_publications')").fetchone()[0] is None
