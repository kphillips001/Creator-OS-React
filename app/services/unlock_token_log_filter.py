"""Redact bearer-style private-chat Unlock tokens from application logs."""
from __future__ import annotations

import logging
import re


_UNLOCK_TOKEN_IN_PATH = re.compile(
    r"(?P<prefix>/api/v1/commerce/unlock/)[A-Za-z0-9_-]+"
)
_UNLOCK_ALIAS_IN_PATH = re.compile(r"(?P<prefix>/u/)[A-Za-z0-9_-]+")
REDACTED_UNLOCK_PATH = "/api/v1/commerce/unlock/<redacted>"
REDACTED_ALIAS_PATH = "/u/<redacted>"


def redact_unlock_tokens(value: object) -> object:
    if not isinstance(value, str):
        return value
    value = _UNLOCK_TOKEN_IN_PATH.sub(REDACTED_UNLOCK_PATH, value)
    return _UNLOCK_ALIAS_IN_PATH.sub(REDACTED_ALIAS_PATH, value)


class UnlockTokenLogFilter(logging.Filter):
    """Remove complete Unlock tokens without retaining a prefix or suffix."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact_unlock_tokens(record.msg)
        if isinstance(record.args, tuple):
            record.args = tuple(redact_unlock_tokens(value) for value in record.args)
        elif isinstance(record.args, dict):
            record.args = {
                key: redact_unlock_tokens(value) for key, value in record.args.items()
            }
        return True


def install_unlock_token_log_redaction() -> None:
    """Install once on loggers that can contain HTTP request paths."""
    for logger_name in ("uvicorn.access", "uvicorn.error", "private-chat-unlock"):
        logger = logging.getLogger(logger_name)
        if not any(isinstance(item, UnlockTokenLogFilter) for item in logger.filters):
            logger.addFilter(UnlockTokenLogFilter())
        for handler in logger.handlers:
            if not any(
                isinstance(item, UnlockTokenLogFilter) for item in handler.filters
            ):
                handler.addFilter(UnlockTokenLogFilter())
