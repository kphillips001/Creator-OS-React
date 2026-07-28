"""Single application boundary for authoritative Asset content commitments."""

from __future__ import annotations

from typing import Any, Mapping

from app.models.content_destination import (
    AssetContentDestination,
    ContentDestination,
    ContentDestinationHistoryEntry,
)
from app.repositories.asset_repository import AssetRepository
from app.repositories.content_destination_repository import (
    ContentDestinationRepository,
)


class ContentDestinationService:
    """The only supported application API for Asset destination decisions."""

    def __init__(
        self,
        *,
        destination_repository: ContentDestinationRepository | None = None,
        asset_repository: AssetRepository | None = None,
    ) -> None:
        self.destination_repository = (
            destination_repository or ContentDestinationRepository()
        )
        self.asset_repository = asset_repository or AssetRepository()

    def get_destination(
        self, asset_id: int, *, connection=None, for_update: bool = False,
    ) -> AssetContentDestination:
        asset = self._asset(asset_id, connection=connection)
        existing = (
            self.destination_repository.get(
                int(asset_id), connection=connection, for_update=for_update
            )
            if connection is not None
            else self.destination_repository.get(int(asset_id))
        )
        if existing is not None:
            return existing
        values = dict(
            asset_id=int(asset_id),
            destination=ContentDestination.AVAILABLE_INVENTORY,
            creator_profile_id=getattr(asset, "creator_profile_id", None),
            source_workflow="content_destination_auto_initialization",
            source_reference=f"content_items:{int(asset_id)}",
            reason="Canonical Asset had no Content Destination.",
            metadata={"initialization": "lazy_fallback"},
        )
        if connection is not None:
            values["connection"] = connection
        initialized = self.destination_repository.assign(**values)
        if connection is not None and for_update:
            return self.destination_repository.get(
                int(asset_id), connection=connection, for_update=True
            )
        return initialized

    def assign_destination(
        self,
        asset_id: int,
        destination: ContentDestination | str,
        *,
        assigned_by_profile_id: int | None = None,
        source_workflow: str | None = None,
        source_reference: str | None = None,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        connection=None,
    ) -> AssetContentDestination:
        asset = self._asset(asset_id, connection=connection)
        normalized = self._destination(destination)
        values = dict(
            asset_id=int(asset_id),
            destination=normalized,
            creator_profile_id=getattr(asset, "creator_profile_id", None),
            assigned_by_profile_id=assigned_by_profile_id,
            source_workflow=source_workflow,
            source_reference=source_reference,
            reason=reason,
            metadata=metadata,
        )
        if connection is not None:
            values["connection"] = connection
        return self.destination_repository.assign(**values)

    def commit_to_destination(
        self,
        asset_id: int,
        destination: ContentDestination | str,
        **assignment_context: Any,
    ) -> AssetContentDestination:
        """Make the first immutable commercial commitment for an Asset."""
        normalized = self._destination(destination)
        if normalized == ContentDestination.AVAILABLE_INVENTORY:
            raise ValueError("A commercial commitment requires a committed destination.")
        connection = assignment_context.pop("connection", None)
        current = self.get_destination(asset_id, connection=connection)
        if current.destination == normalized:
            return current
        if current.destination != ContentDestination.AVAILABLE_INVENTORY:
            raise ValueError(
                f"Asset {int(asset_id)} is already committed to "
                f"{current.destination.value}."
            )
        return self.assign_destination(
            asset_id, normalized, connection=connection, **assignment_context
        )

    def is_available_inventory(self, asset_id: int) -> bool:
        return (
            self.get_destination(asset_id).destination
            == ContentDestination.AVAILABLE_INVENTORY
        )

    def is_committed(self, asset_id: int) -> bool:
        return not self.is_available_inventory(asset_id)

    def is_asset_committed(self, asset_id: int) -> bool:
        return self.is_committed(asset_id)

    def available_inventory_predicate(self, asset_id_expression: str) -> str:
        """Provide one set-based predicate for paginated repository readers."""
        return self.destination_repository.available_inventory_predicate(
            asset_id_expression
        )

    def list_available_inventory_assets(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 500,
    ) -> tuple[Any, ...]:
        asset_ids = self.destination_repository.list_available_asset_ids(
            creator_profile_id=creator_profile_id,
            limit=limit,
        )
        assets = {
            int(asset.id): asset
            for asset in self.asset_repository.list_by_ids(asset_ids)
        }
        return tuple(assets[asset_id] for asset_id in asset_ids if asset_id in assets)

    def get_history(
        self, asset_id: int, *, limit: int = 100
    ) -> tuple[ContentDestinationHistoryEntry, ...]:
        self._asset(asset_id)
        return self.destination_repository.list_history(asset_id, limit=limit)

    def _asset(self, asset_id: int, *, connection=None):
        asset = (
            self.asset_repository.get_by_id(int(asset_id), connection=connection)
            if connection is not None
            else self.asset_repository.get_by_id(int(asset_id))
        )
        if asset is None:
            raise KeyError(f"Canonical Asset not found: {asset_id}")
        return asset

    @staticmethod
    def _destination(value: ContentDestination | str) -> ContentDestination:
        if isinstance(value, ContentDestination):
            return value
        try:
            return ContentDestination(str(value).strip().upper())
        except ValueError as error:
            raise ValueError(f"Unsupported Content Destination: {value}") from error
