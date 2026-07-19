"""Logging boundary that keeps heartbeat failures from duplicating business work."""

import logging
from typing import Any, Callable


def record_heartbeat_safely(logger: logging.Logger, operation: str, callback: Callable[[], Any]) -> Any:
    try:
        return callback()
    except Exception as error:
        logger.error("[WORKER HEARTBEAT ERROR] operation=%s error_type=%s error=%s", operation, type(error).__name__, error)
        return None
