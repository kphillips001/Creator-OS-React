"""Single readiness authority for standalone private-chat PPV presentation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True)
class PrivatePpvReadiness:
    ready: bool
    reason: str | None
    teaser_asset_id: int | None = None
    teaser_path: str | None = None


class PrivatePpvReadinessService:
    """Validate the explicit CHAT teaser contract from current state."""

    EXCLUSION_REASON = "PRIVATE_PPV_PRESENTATION_NOT_READY"

    def evaluate(self, value: Mapping[str, Any]) -> PrivatePpvReadiness:
        creator_id = self._integer(value.get("creator_profile_id"))
        hero_id = self._integer(value.get("hero_asset_id"))
        if not creator_id or not hero_id:
            return self._blocked("OFFERING_IDENTITY_INVALID")
        if not value.get("chat_teaser_id"):
            return self._blocked("CHAT_TEASER_MISSING")
        if value.get("chat_teaser_distribution_use") != "CHAT":
            return self._blocked("CHAT_TEASER_DISTRIBUTION_INVALID")
        if value.get("chat_teaser_status") != "READY":
            return self._blocked("CHAT_TEASER_NOT_READY")
        if self._integer(value.get("chat_teaser_creator_profile_id")) != creator_id:
            return self._blocked("CHAT_TEASER_CREATOR_MISMATCH")
        if self._integer(value.get("chat_teaser_source_asset_id")) != hero_id:
            return self._blocked("CHAT_TEASER_SOURCE_MISMATCH")
        derived_id = self._integer(value.get("chat_teaser_derived_asset_id"))
        if not derived_id:
            return self._blocked("CHAT_TEASER_DERIVED_ASSET_MISSING")
        if derived_id == hero_id:
            return self._blocked("CHAT_TEASER_PAID_ORIGINAL_ALIAS")
        if self._integer(value.get("chat_teaser_derived_creator_profile_id")) != creator_id:
            return self._blocked("CHAT_TEASER_DERIVED_CREATOR_MISMATCH")
        if self._integer(value.get("chat_teaser_derived_source_asset_id")) != hero_id:
            return self._blocked("CHAT_TEASER_DERIVED_SOURCE_MISMATCH")
        if value.get("chat_teaser_derived_distribution_use") != "CHAT":
            return self._blocked("CHAT_TEASER_DERIVED_DISTRIBUTION_INVALID")
        if value.get("chat_teaser_derived_commercial_role") != "SINGLE_IMAGE_CHAT_TEASER":
            return self._blocked("CHAT_TEASER_DERIVED_ROLE_INVALID")
        path = str(value.get("chat_teaser_derivative_path") or "").strip()
        if not path or not Path(path).is_file():
            return self._blocked("CHAT_TEASER_FILE_MISSING")
        return PrivatePpvReadiness(
            ready=True, reason=None, teaser_asset_id=derived_id,
            teaser_path=path,
        )

    @staticmethod
    def _integer(value):
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _blocked(reason):
        return PrivatePpvReadiness(ready=False, reason=reason)
