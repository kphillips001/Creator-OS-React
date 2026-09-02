import atexit
import os
import logging
import time
from contextlib import contextmanager
from threading import Lock
from typing import Any

from dotenv import load_dotenv
from psycopg.rows import dict_row


load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in the .env file.")


_pool: Any | None = None
_pool_pid: int | None = None
_pool_lock = Lock()
_performance_logger = logging.getLogger("creator-os-performance")


def _pool_size(name: str, default: int) -> int:
    try:
        return max(0, int(os.getenv(name, str(default))))
    except (TypeError, ValueError):
        return default


def get_database_pool():
    """Return this process's bounded, lazily created PostgreSQL pool."""
    global _pool, _pool_pid
    process_id = os.getpid()
    if _pool is not None and _pool_pid == process_id:
        return _pool
    with _pool_lock:
        if _pool is not None and _pool_pid != process_id:
            _pool.close()
            _pool = None
        if _pool is None:
            from psycopg_pool import ConnectionPool

            minimum = _pool_size("DATABASE_POOL_MIN_SIZE", 1)
            maximum = max(minimum or 1, _pool_size("DATABASE_POOL_MAX_SIZE", 10))
            _pool = ConnectionPool(
                conninfo=DATABASE_URL,
                min_size=minimum,
                max_size=maximum,
                timeout=float(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30")),
                max_idle=float(os.getenv("DATABASE_POOL_MAX_IDLE_SECONDS", "300")),
                kwargs={"row_factory": dict_row, "autocommit": False},
                check=ConnectionPool.check_connection,
                open=True,
                name=f"creator-os-{process_id}",
            )
            _pool_pid = process_id
    return _pool


def close_database_pool() -> None:
    global _pool, _pool_pid
    with _pool_lock:
        if _pool is not None:
            _pool.close()
        _pool = None
        _pool_pid = None


@contextmanager
def get_db_connection():
    pool = get_database_pool()
    acquisition_started = time.perf_counter()
    with pool.connection() as connection:
        acquisition_ms = (time.perf_counter() - acquisition_started) * 1000
        _performance_logger.info("component=db_pool acquisition_ms=%.2f", acquisition_ms)
        if acquisition_ms >= 100:
            _performance_logger.warning("component=db_pool event=slow_acquisition acquisition_ms=%.2f threshold_ms=100", acquisition_ms)
        try:
            yield connection
            connection.commit()
        except Exception as error:
            connection.rollback()
            print(f"[DB ERROR] Rolling back transaction: {error}")
            raise


atexit.register(close_database_pool)
