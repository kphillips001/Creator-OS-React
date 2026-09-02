"""Fail-closed, request-local authorization for the launch smoke-test customer."""

from __future__ import annotations

import os
import hashlib
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass


_ACTIVE_IDENTITY: ContextVar[tuple[int, int] | None] = ContextVar(
    "controlled_autonomy_test_identity", default=None,
)


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {
        "1", "true", "yes", "on", "enabled",
    }


def _positive_int(value: str | None) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


@dataclass(frozen=True)
class ControlledAutonomyDecision:
    allowed: bool
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed": self.allowed,
            "blocked": not self.allowed,
            "reason": self.reason,
            "source": "controlled_telegram_test_boundary",
        }


class ControlledAutonomyTestService:
    """Authorize exactly one configured numeric Telegram user/private chat."""

    ENABLED_ENV = "CONTROLLED_AUTONOMY_TEST_ENABLED"
    USER_ENV = "CONTROLLED_AUTONOMY_TELEGRAM_USER_ID"
    CHAT_ENV = "CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID"

    def configured_identity(self) -> tuple[int, int] | None:
        if not _enabled(os.getenv(self.ENABLED_ENV)):
            return None
        user_id = _positive_int(os.getenv(self.USER_ENV))
        chat_id = _positive_int(os.getenv(self.CHAT_ENV))
        if user_id is None or chat_id is None:
            return None
        return user_id, chat_id

    def decide(self, *, telegram_user_id: int, telegram_chat_id: int) -> ControlledAutonomyDecision:
        configured = self.configured_identity()
        supplied = (
            _positive_int(str(telegram_user_id)),
            _positive_int(str(telegram_chat_id)),
        )
        if configured is None:
            return ControlledAutonomyDecision(False, "controlled_autonomy_test_disabled")
        if None in supplied or supplied != configured:
            return ControlledAutonomyDecision(False, "controlled_autonomy_test_identity_mismatch")
        return ControlledAutonomyDecision(True, "controlled_autonomy_test_allowlisted")

    @contextmanager
    def scope(self, *, telegram_user_id: int, telegram_chat_id: int):
        decision = self.decide(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
        )
        if not decision.allowed:
            raise PermissionError(decision.reason)
        token = _ACTIVE_IDENTITY.set((int(telegram_user_id), int(telegram_chat_id)))
        try:
            yield decision
        finally:
            _ACTIVE_IDENTITY.reset(token)

    def active_decision(self) -> ControlledAutonomyDecision:
        active = _ACTIVE_IDENTITY.get()
        configured = self.configured_identity()
        if active is not None and configured is not None and active == configured:
            return ControlledAutonomyDecision(True, "controlled_autonomy_test_allowlisted")
        return ControlledAutonomyDecision(False, "controlled_autonomy_test_context_absent")

    def audit_metadata(self) -> dict[str, object]:
        configured = self.configured_identity()
        fingerprint = None
        if configured is not None:
            fingerprint = hashlib.sha256(
                f"{configured[0]}:{configured[1]}".encode("utf-8")
            ).hexdigest()[:12]
        return {
            "controlled_autonomy_test_enabled": configured is not None,
            "controlled_autonomy_identity_configured": configured is not None,
            "controlled_autonomy_identity_fingerprint": fingerprint,
        }
