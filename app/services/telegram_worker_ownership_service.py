"""PostgreSQL-backed singleton ownership for the Ava private-chat listener."""

from __future__ import annotations

from typing import Any, Callable

from app.database import get_database_pool


class TelegramWorkerOwnershipError(RuntimeError):
    """The authoritative Telegram listener lease is unavailable or unhealthy."""


class TelegramWorkerOwnershipService:
    # PostgreSQL advisory locks are session-owned and automatically released
    # when a hard-crashed worker loses its database connection.
    LOCK_KEY = 0x41564154  # "AVAT"

    def __init__(self, *, connection_factory: Callable | None = None,
                 connection_releaser: Callable | None = None) -> None:
        self._pool = None
        if connection_factory is None:
            self._pool = get_database_pool()
            connection_factory = self._pool.getconn
            connection_releaser = self._pool.putconn
        self._connection_factory = connection_factory
        self._connection_releaser = connection_releaser or (lambda connection: connection.close())
        self._connection: Any | None = None

    def acquire(self) -> bool:
        if self._connection is not None:
            return self.check()
        connection = self._connection_factory()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (self.LOCK_KEY,))
                row = cursor.fetchone()
            acquired = bool(row and row["acquired"])
            if not acquired:
                self._connection_releaser(connection)
                return False
            self._connection = connection
            return True
        except Exception:
            self._connection_releaser(connection)
            raise

    def check(self) -> bool:
        if self._connection is None:
            return False
        try:
            with self._connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS healthy")
                row = cursor.fetchone()
            return bool(row and row["healthy"] == 1)
        except Exception as error:
            self.release()
            raise TelegramWorkerOwnershipError("Telegram worker database ownership was lost.") from error

    def release(self) -> None:
        connection, self._connection = self._connection, None
        if connection is None:
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", (self.LOCK_KEY,))
        except Exception:
            pass
        finally:
            self._connection_releaser(connection)
