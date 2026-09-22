from pathlib import Path

from app.repositories.creator_content_publication_repository import CreatorContentPublicationRepository


class Cursor:
    def __init__(self):
        self.calls = []
        self.rows = []

    def execute(self, sql, params=None):
        self.calls.append((" ".join(sql.split()), params))
        if "to_regclass" in sql:
            self.rows = [{"table_ref": "creator_content_publications"}]
        elif "SELECT *" in sql:
            self.rows = []

    def fetchone(self): return self.rows[0] if self.rows else None
    def fetchall(self): return list(self.rows)
    def __enter__(self): return self
    def __exit__(self, *_args): return None


class Connection:
    def __init__(self, cursor): self.value = cursor
    def cursor(self): return self.value
    def __enter__(self): return self
    def __exit__(self, *_args): return None


def test_search_has_no_age_cutoff_ranks_recency_and_bounds_count():
    cursor = Cursor()
    repository = CreatorContentPublicationRepository(connection_factory=lambda: Connection(cursor))
    assert repository.search(creator_profile_id=7, query="red dress", limit=999) == ()
    sql, params = cursor.calls[-1]
    assert "published_at DESC" in sql and "plainto_tsquery" in sql
    assert "interval" not in sql.lower() and "published_at >=" not in sql.lower()
    assert params[-1] == 50


def test_migration_is_empty_infrastructure_with_required_indexes_and_no_backfill():
    forward = Path("migrations/forward/20260919_144_creator_content_publications.sql").read_text()
    rollback = Path("migrations/rollback/20260919_144_creator_content_publications.sql").read_text()
    assert "CREATE TABLE public.creator_content_publications" in forward
    assert "USING GIN" in forward
    assert "telegram_identity_unique" in forward
    assert "INSERT INTO" not in forward.upper()
    assert "SELECT FROM" not in forward.upper()
    assert "DROP TABLE" in rollback.upper()


def test_repository_source_contains_no_age_eligibility_and_uses_conflict_identity():
    source = Path("app/repositories/creator_content_publication_repository.py").read_text()
    assert "ON CONFLICT (platform,destination,telegram_channel_id,telegram_message_id)" in source
    assert "MAX_SEARCH_RESULTS = 50" in source
    assert "timedelta" not in source and "INTERVAL" not in source
