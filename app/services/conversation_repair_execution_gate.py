"""Independent fail-closed authority for conversation-derived source repair."""
from __future__ import annotations

import os
from collections.abc import Mapping


class ConversationRepairExecutionDisabled(RuntimeError):
    """Raised before any repair execution side effect is permitted."""


class ConversationRepairExecutionGate:
    ENVIRONMENT_KEY = "CONVERSATION_REPAIR_EXECUTION_ENABLED"
    ENABLED_VALUES = frozenset({"1", "true", "yes", "on", "enabled"})
    DISABLED_MESSAGE = "CONVERSATION REPAIR EXECUTION DISABLED"

    def __init__(self, environment: Mapping[str, str] | None = None):
        self._environment = os.environ if environment is None else environment

    def enabled(self) -> bool:
        value = self._environment.get(self.ENVIRONMENT_KEY)
        if not isinstance(value, str):
            return False
        return value.strip().lower() in self.ENABLED_VALUES

    def require_enabled(self) -> None:
        if not self.enabled():
            raise ConversationRepairExecutionDisabled(self.DISABLED_MESSAGE)
