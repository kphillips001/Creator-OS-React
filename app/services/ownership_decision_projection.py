"""Thin fail-closed projections over canonical Ownership Intelligence."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.ownership_intelligence import OwnershipIdentity
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.ownership_intelligence_service import OwnershipIntelligenceService


@dataclass(frozen=True)
class OwnershipDecision:
    owned: bool
    fail_closed: bool
    conflicts: tuple[str, ...] = ()
    insufficiencies: tuple[str, ...] = ()

    @property
    def blocks_offer(self) -> bool:
        return self.owned or self.fail_closed


class OwnershipDecisionProjection:
    """Answer compact legacy caller questions without becoming an authority."""

    def __init__(
        self,
        *,
        ownership_intelligence: OwnershipIntelligenceService | None = None,
        creator_profile_resolver: Any = get_active_creator_profile,
    ) -> None:
        self.ownership_intelligence = (
            ownership_intelligence or OwnershipIntelligenceService()
        )
        self.creator_profile_resolver = creator_profile_resolver

    def asset(
        self, *, fanvue_account_id: int, fanvue_user_id: Any,
        asset_id: int, creator_profile_id: int | None = None,
    ) -> OwnershipDecision:
        answer = self._answer(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            creator_profile_id=creator_profile_id,
        )
        return self._decision(
            answer,
            owned=(
                self.ownership_intelligence.owns_asset(answer, int(asset_id))
                if answer is not None else False
            ),
        )

    def content_tag(
        self, *, fanvue_account_id: int, fanvue_user_id: Any,
        content_tag: str, creator_profile_id: int | None = None,
    ) -> OwnershipDecision:
        answer = self._answer(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
            creator_profile_id=creator_profile_id,
        )
        normalized = str(content_tag or "").strip().casefold()
        owned = bool(answer) and any(
            evidence.proves_ownership
            and str(evidence.details.get("contentTag") or "").strip().casefold()
            == normalized
            for evidence in answer.evidence
        )
        return self._decision(answer, owned=owned)

    def _answer(
        self, *, fanvue_account_id: int, fanvue_user_id: Any,
        creator_profile_id: int | None,
    ):
        profile_id = int(creator_profile_id or 0)
        if profile_id <= 0:
            profile = self.creator_profile_resolver(str(fanvue_account_id)) or {}
            profile_id = int(profile.get("id") or 0)
        if profile_id <= 0 or not fanvue_account_id or fanvue_user_id is None:
            return None
        return self.ownership_intelligence.answer(OwnershipIdentity(
            creator_profile_id=profile_id,
            fanvue_account_id=int(fanvue_account_id),
            legacy_fanvue_user_id=str(fanvue_user_id),
        ))

    @staticmethod
    def _decision(answer, *, owned: bool) -> OwnershipDecision:
        if answer is None:
            return OwnershipDecision(
                owned=False, fail_closed=True,
                insufficiencies=("OWNERSHIP_IDENTITY_INSUFFICIENT",),
            )
        conflicts = tuple(answer.conflicts or ())
        insufficiencies = tuple(answer.insufficiencies or ())
        return OwnershipDecision(
            owned=bool(owned),
            fail_closed=bool(conflicts or insufficiencies),
            conflicts=conflicts,
            insufficiencies=insufficiencies,
        )
