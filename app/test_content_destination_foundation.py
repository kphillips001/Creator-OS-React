from pathlib import Path
from types import SimpleNamespace

import pytest

from app.models.content_destination import (
    AssetContentDestination,
    ContentDestination,
    ContentDestinationHistoryEntry,
)
from app.services.content_destination_service import ContentDestinationService


class Assets:
    def __init__(self):
        self.assets = {
            1: SimpleNamespace(id=1, creator_profile_id=7),
            2: SimpleNamespace(id=2, creator_profile_id=7),
        }

    def get_by_id(self, asset_id):
        return self.assets.get(asset_id)

    def list_by_ids(self, asset_ids):
        return [self.assets[asset_id] for asset_id in asset_ids if asset_id in self.assets]


class Destinations:
    def __init__(self):
        self.rows = {}
        self.history = {}
        self.assign_calls = 0

    def get(self, asset_id):
        return self.rows.get(asset_id)

    @staticmethod
    def available_inventory_predicate(expression):
        if expression != "content_items.id":
            raise ValueError("Asset ID expression must be a qualified SQL identifier.")
        return (
            "EXISTS (SELECT 1 FROM public.asset_content_destinations destination "
            "WHERE destination.asset_id=content_items.id "
            "AND destination.destination='AVAILABLE_INVENTORY')"
        )

    def assign(self, *, asset_id, destination, creator_profile_id, **kwargs):
        self.assign_calls += 1
        previous = self.rows.get(asset_id)
        if previous and previous.destination == destination:
            return previous
        row = AssetContentDestination(
            asset_id=asset_id,
            destination=destination,
            creator_profile_id=creator_profile_id,
            assigned_by_profile_id=kwargs.get("assigned_by_profile_id"),
            source_workflow=kwargs.get("source_workflow"),
            source_reference=kwargs.get("source_reference"),
            reason=kwargs.get("reason"),
            metadata=kwargs.get("metadata") or {},
        )
        self.rows[asset_id] = row
        entries = self.history.setdefault(asset_id, [])
        entries.append(
            ContentDestinationHistoryEntry(
                history_id=len(entries) + 1,
                asset_id=asset_id,
                event_type="CREATED" if previous is None else "CHANGED",
                previous_destination=previous.destination if previous else None,
                new_destination=destination,
                source_workflow=row.source_workflow,
            )
        )
        return row

    def list_available_asset_ids(self, *, creator_profile_id=None, limit=500):
        return tuple(
            asset_id
            for asset_id, row in self.rows.items()
            if row.destination == ContentDestination.AVAILABLE_INVENTORY
            and (creator_profile_id is None or row.creator_profile_id == creator_profile_id)
        )[:limit]

    def list_history(self, asset_id, *, limit=100):
        return tuple(reversed(self.history.get(asset_id, [])))[:limit]


def service():
    destinations = Destinations()
    return (
        ContentDestinationService(
            destination_repository=destinations,
            asset_repository=Assets(),
        ),
        destinations,
    )


def test_asset_defaults_to_available_inventory_and_initialization_is_idempotent():
    content_destinations, repository = service()

    first = content_destinations.get_destination(1)
    second = content_destinations.get_destination(1)

    assert first.destination == ContentDestination.AVAILABLE_INVENTORY
    assert second == first
    assert repository.assign_calls == 1
    assert len(repository.history[1]) == 1


def test_destination_lookup_commitment_and_available_inventory_checks():
    content_destinations, _ = service()
    assert content_destinations.is_available_inventory(1) is True
    assert content_destinations.is_committed(1) is False

    assigned = content_destinations.assign_destination(
        1, ContentDestination.PHOTOSET, source_workflow="test"
    )

    assert content_destinations.get_destination(1) == assigned
    assert content_destinations.is_available_inventory(1) is False
    assert content_destinations.is_committed(1) is True
    assert content_destinations.is_asset_committed(1) is True


def test_one_row_per_asset_prevents_duplicate_active_destination():
    content_destinations, repository = service()
    content_destinations.assign_destination(1, ContentDestination.PHOTOSET)
    content_destinations.assign_destination(1, ContentDestination.BUNDLE)

    assert len(repository.rows) == 1
    assert repository.rows[1].destination == ContentDestination.BUNDLE
    assert [entry.new_destination for entry in repository.history[1]] == [
        ContentDestination.PHOTOSET,
        ContentDestination.BUNDLE,
    ]


def test_duplicate_same_destination_is_idempotent_and_does_not_add_history():
    content_destinations, repository = service()
    first = content_destinations.assign_destination(1, ContentDestination.TEASER)
    second = content_destinations.assign_destination(1, ContentDestination.TEASER)

    assert first == second
    assert len(repository.rows) == 1
    assert len(repository.history[1]) == 1


def test_audit_history_created_for_initialization_and_change():
    content_destinations, _ = service()
    content_destinations.get_destination(1)
    content_destinations.assign_destination(
        1, ContentDestination.SINGLE_PPV, source_workflow="unit_test"
    )

    history = content_destinations.get_history(1)
    assert [entry.event_type for entry in history] == ["CHANGED", "CREATED"]
    assert history[0].previous_destination == ContentDestination.AVAILABLE_INVENTORY
    assert history[0].new_destination == ContentDestination.SINGLE_PPV


def test_available_inventory_query_uses_destination_authority():
    content_destinations, _ = service()
    content_destinations.get_destination(1)
    content_destinations.get_destination(2)
    content_destinations.assign_destination(2, ContentDestination.TELEGRAM_WALL)

    assert [asset.id for asset in content_destinations.list_available_inventory_assets()] == [1]


def test_invalid_destination_and_missing_asset_are_rejected():
    content_destinations, _ = service()
    with pytest.raises(ValueError, match="Unsupported Content Destination"):
        content_destinations.assign_destination(1, "not-a-destination")
    with pytest.raises(KeyError, match="Canonical Asset not found"):
        content_destinations.get_destination(999)


def test_migration_structurally_enforces_backfill_and_automatic_initialization():
    migration = Path(
        "migrations/forward/20260723_001_content_destination_foundation.sql"
    ).read_text(encoding="utf-8")

    assert "asset_id BIGINT PRIMARY KEY" in migration
    assert "ON CONFLICT (asset_id) DO NOTHING" in migration
    assert "FROM public.content_items item" in migration
    assert "'AVAILABLE_INVENTORY'" in migration
    assert "trg_initialize_content_destination" in migration
    assert "trg_audit_asset_content_destination" in migration
    assert "asset_content_destination_history" in migration


def test_set_based_predicate_is_canonical_and_rejects_untrusted_sql():
    content_destinations, _ = service()
    predicate = content_destinations.available_inventory_predicate("content_items.id")
    assert "asset_content_destinations" in predicate
    assert "AVAILABLE_INVENTORY" in predicate
    with pytest.raises(ValueError, match="qualified SQL identifier"):
        content_destinations.available_inventory_predicate("content_items.id OR TRUE")


def test_commit_is_idempotent_and_rejects_a_second_commercial_destination():
    content_destinations, repository = service()

    first = content_destinations.commit_to_destination(1, ContentDestination.PHOTOSET)
    second = content_destinations.commit_to_destination(1, ContentDestination.PHOTOSET)

    assert first == second
    assert len(repository.history[1]) == 2  # AVAILABLE_INVENTORY initialization + commitment
    with pytest.raises(ValueError, match="already committed to PHOTOSET"):
        content_destinations.commit_to_destination(1, ContentDestination.BUNDLE)
