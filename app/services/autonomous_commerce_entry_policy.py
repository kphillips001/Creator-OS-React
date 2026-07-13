"""Policy guard for automatic autonomous commerce entry."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Mapping

from app.models.asset_provenance import (
    ASSET_PROVENANCE_METADATA_KEY,
    AssetProvenanceClassification,
)
from app.models.commerce_destination import CommerceDestination


CHAT_COMMERCE_DESTINATIONS = {
    CommerceDestination.CUSTOMER_CONVERSATIONS.value,
    CommerceDestination.BOTH.value,
}


@dataclass(frozen=True)
class AutonomousCommerceEntryDecision:
    allowed: bool
    asset_id: int | None = None
    reasons: tuple[str, ...] = ()
    provenance_classification: str | None = None
    metadata: Mapping[str, Any] | None = None


class AutonomousCommerceEntryPolicy:
    """Central guard for creator-approved autonomous commerce advancement."""

    def __init__(
        self,
        *,
        asset_repository: Any | None = None,
        content_intelligence_repository: Any | None = None,
    ) -> None:
        self.asset_repository = asset_repository
        self.content_intelligence_repository = content_intelligence_repository

    def can_register_commerce(
        self,
        asset: Any | None,
        *,
        approval_identity: Mapping[str, Any] | None = None,
        content_intelligence_profile: Any | None = None,
    ) -> AutonomousCommerceEntryDecision:
        reasons: list[str] = []
        asset_id = self._asset_id(asset)
        if asset is None:
            reasons.append("canonical_asset_not_found")
        elif str(getattr(asset, "status", "") or "").lower() != "approved":
            reasons.append("asset_not_approved")

        provenance = self._approval_provenance(
            asset,
            approval_identity=approval_identity,
        )
        if provenance != AssetProvenanceClassification.CREATOR_APPROVAL.value:
            reasons.append("creator_approval_provenance_required")
        if not self._approval_identity(asset, approval_identity=approval_identity):
            reasons.append("approval_identity_required")

        if content_intelligence_profile is None:
            content_intelligence_profile = self._content_profile(asset_id)
        if content_intelligence_profile is None:
            reasons.append("content_intelligence_profile_required")

        return self._decision(
            not reasons,
            asset_id=asset_id,
            reasons=reasons,
            provenance=provenance,
        )

    def can_select_destination(
        self,
        business_asset: Any | None,
        *,
        destination: CommerceDestination | str | None = None,
    ) -> AutonomousCommerceEntryDecision:
        reasons: list[str] = []
        if business_asset is None:
            reasons.append("business_asset_not_found")
        provenance = self._business_provenance(business_asset)
        if provenance != AssetProvenanceClassification.CREATOR_APPROVAL.value:
            reasons.append("creator_approval_provenance_required")
        if destination is not None and self._destination_value(destination) is None:
            reasons.append("invalid_commerce_destination")
        if business_asset is not None and not bool(
            getattr(business_asset, "content_intelligence_ready", False)
        ):
            reasons.append("content_intelligence_not_ready")
        return self._decision(
            not reasons,
            asset_id=getattr(business_asset, "asset_id", None),
            reasons=reasons,
            provenance=provenance,
        )

    def can_start_fulfillment(
        self,
        business_asset: Any | None,
        *,
        selected_destination: str | None = None,
    ) -> AutonomousCommerceEntryDecision:
        decision = self.can_select_destination(
            business_asset,
            destination=selected_destination,
        )
        reasons = list(decision.reasons)
        if selected_destination not in CHAT_COMMERCE_DESTINATIONS:
            reasons.append("customer_conversations_destination_required")
        return self._decision(
            not reasons,
            asset_id=getattr(business_asset, "asset_id", None),
            reasons=reasons,
            provenance=decision.provenance_classification,
        )

    def can_register_chat(
        self,
        business_asset: Any | None,
    ) -> AutonomousCommerceEntryDecision:
        return self.can_start_fulfillment(
            business_asset,
            selected_destination=getattr(
                business_asset,
                "selected_commerce_destination",
                None,
            ),
        )

    def _content_profile(self, asset_id: int | None) -> Any | None:
        if asset_id is None or self.content_intelligence_repository is None:
            return None
        getter = getattr(self.content_intelligence_repository, "get_by_asset_id", None)
        if not callable(getter):
            return None
        try:
            return getter(int(asset_id))
        except Exception:
            return None

    def _approval_provenance(
        self,
        asset: Any | None,
        *,
        approval_identity: Mapping[str, Any] | None,
    ) -> str | None:
        metadata = self._metadata(asset)
        asset_provenance = self._mapping(metadata.get(ASSET_PROVENANCE_METADATA_KEY))
        classification = asset_provenance.get("classification")
        if classification:
            return str(classification)
        approval = self._mapping(metadata.get("creator_approval"))
        if approval or approval_identity:
            return AssetProvenanceClassification.CREATOR_APPROVAL.value
        return None

    def _approval_identity(
        self,
        asset: Any | None,
        *,
        approval_identity: Mapping[str, Any] | None,
    ) -> Mapping[str, Any] | None:
        if approval_identity:
            return approval_identity
        approval = self._mapping(self._metadata(asset).get("creator_approval"))
        return approval or None

    def _business_provenance(self, business_asset: Any | None) -> str | None:
        if business_asset is None:
            return None
        provenance = self._mapping(
            getattr(business_asset, "registration_provenance", None)
        )
        asset_provenance = self._mapping(
            provenance.get(ASSET_PROVENANCE_METADATA_KEY)
        )
        classification = asset_provenance.get("classification")
        if classification:
            return str(classification)
        approval = self._mapping(provenance.get("approval_identity"))
        if approval:
            return AssetProvenanceClassification.CREATOR_APPROVAL.value
        return None

    @staticmethod
    def _destination_value(destination: CommerceDestination | str | None) -> str | None:
        if destination is None:
            return None
        try:
            return CommerceDestination(destination).value
        except ValueError:
            return None

    @staticmethod
    def _asset_id(asset: Any | None) -> int | None:
        value = getattr(asset, "id", None)
        try:
            return int(value) if value is not None else None
        except (TypeError, ValueError):
            return None

    @classmethod
    def _metadata(cls, asset: Any | None) -> dict[str, Any]:
        return cls._mapping(getattr(asset, "media_metadata", None))

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                return dict(parsed) if isinstance(parsed, Mapping) else {}
            except json.JSONDecodeError:
                return {}
        return {}

    @staticmethod
    def _decision(
        allowed: bool,
        *,
        asset_id: int | None,
        reasons: list[str],
        provenance: str | None,
    ) -> AutonomousCommerceEntryDecision:
        return AutonomousCommerceEntryDecision(
            allowed=allowed,
            asset_id=asset_id,
            reasons=tuple(dict.fromkeys(reason for reason in reasons if reason)),
            provenance_classification=provenance,
            metadata={"source": "AutonomousCommerceEntryPolicy"},
        )
