from contextlib import contextmanager

import pytest

from app import database


class FakeConnection:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class FakePool:
    def __init__(self):
        self.connection_value = FakeConnection()
        self.checked_out = 0

    @contextmanager
    def connection(self):
        self.checked_out += 1
        try:
            yield self.connection_value
        finally:
            self.checked_out -= 1


def test_pooled_connection_commits_and_returns_to_pool(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(database, "get_database_pool", lambda: pool)

    with database.get_db_connection() as connection:
        assert connection is pool.connection_value

    assert connection.commits == 1
    assert connection.rollbacks == 0
    assert pool.checked_out == 0


def test_pooled_connection_rolls_back_and_returns_to_pool(monkeypatch):
    pool = FakePool()
    monkeypatch.setattr(database, "get_database_pool", lambda: pool)

    with pytest.raises(RuntimeError, match="failed transaction"):
        with database.get_db_connection():
            raise RuntimeError("failed transaction")

    assert pool.connection_value.commits == 0
    assert pool.connection_value.rollbacks == 1
    assert pool.checked_out == 0
