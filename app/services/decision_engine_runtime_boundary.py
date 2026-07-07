"""Runtime persistence boundary for DecisionEngine orchestration."""

from __future__ import annotations

from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.memory_repository import update_memory_fields
from app.repositories.send_log_repository import log_send_event
from app.repositories.user_repository import get_user_by_account_and_id


class DecisionEngineRuntimeBoundary:
    """Delegates DecisionEngine runtime persistence to existing repositories."""

    def get_active_creator_profile(self, account_id) -> dict:
        return get_active_creator_profile(account_id)

    def get_user_by_account_and_id(self, account_id, user_id) -> dict | None:
        return get_user_by_account_and_id(account_id, user_id)

    def update_memory_fields(self, account_id, user_id, data: dict):
        return update_memory_fields(account_id, user_id, data)

    def log_send_event(self, **kwargs):
        return log_send_event(**kwargs)
