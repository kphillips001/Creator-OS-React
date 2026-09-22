"""Canonical account and creator scope shared by Ava runtime operator surfaces."""

from __future__ import annotations

import os

from app.repositories.creator_profile_repository import get_active_creator_profile


class AvaRuntimeScopeService:
    """Resolve the configured Ava account to its active creator profile."""

    @staticmethod
    def resolve(*, requested_account_id: int | None = None,
                environment=None) -> tuple[int, int]:
        values = os.environ if environment is None else environment
        raw_account_id = str(values.get("AVA_FANVUE_ACCOUNT_ID", "")).strip()
        if not raw_account_id or not raw_account_id.isdigit() or int(raw_account_id) <= 0:
            raise ValueError("AVA_FANVUE_ACCOUNT_ID must be a positive integer.")
        account_id = int(raw_account_id)
        if requested_account_id is not None and int(requested_account_id) != account_id:
            raise ValueError("Requested account is not the configured Ava runtime account.")
        profile = get_active_creator_profile(str(account_id)) or {}
        creator_profile_id = int(profile.get("id") or 0)
        if creator_profile_id <= 0:
            raise ValueError("The configured Ava account requires an active creator profile.")
        return creator_profile_id, account_id
