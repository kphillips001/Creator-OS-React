"""PostgreSQL persistence for authoritative Asset content commitments."""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from app.database import get_db_connection
from app.models.content_destination import (
    CONTENT_DESTINATION_SCHEMA_VERSION,
    AssetContentDestination,
    ContentDestination,
    ContentDestinationHistoryEntry,
)


class ContentDestinationConflictError(ValueError):
    """Raised when a write would violate one-destination-per-Asset."""


class ContentDestinationRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get(
        self, asset_id: int, *, connection=None, for_update: bool = False,
    ) -> AssetContentDestination | None:
        lock_clause = " FOR UPDATE" if for_update else ""
        if connection is not None:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.asset_content_destinations "
                    f"WHERE asset_id=%s{lock_clause}",
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        else:
            if for_update:
                raise ValueError("A transaction is required for a destination row lock.")
            with self._connection_factory() as managed:
                with managed.cursor() as cursor:
                    cursor.execute(
                        "SELECT * FROM public.asset_content_destinations WHERE asset_id=%s",
                        (int(asset_id),),
                    )
                    row = cursor.fetchone()
        return self._destination_from_row(row) if row else None

    @staticmethod
    def available_inventory_predicate(asset_id_expression: str) -> str:
        """Return the canonical set-based availability predicate for readers."""
        expression = str(asset_id_expression or "").strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*", expression):
            raise ValueError("Asset ID expression must be a qualified SQL identifier.")
        return f"""EXISTS (
            SELECT 1
            FROM public.asset_content_destinations content_destination
            WHERE content_destination.asset_id = {expression}
              AND content_destination.destination = 'AVAILABLE_INVENTORY'
        )"""

    def assign(
        self,
        *,
        asset_id: int,
        destination: ContentDestination,
        creator_profile_id: int | None,
        assigned_by_profile_id: int | None = None,
        source_workflow: str | None = None,
        source_reference: str | None = None,
        reason: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        connection=None,
    ) -> AssetContentDestination:
        """Insert or change the single row for an Asset.

        The Asset primary key makes a second simultaneous destination
        structurally impossible. The database audit trigger records inserts
        and actual destination changes.
        """
        if connection is None:
            with self._connection_factory() as managed_connection:
                result = self._assign_with_connection(
                    managed_connection,
                    asset_id=asset_id,
                    destination=destination,
                    creator_profile_id=creator_profile_id,
                    assigned_by_profile_id=assigned_by_profile_id,
                    source_workflow=source_workflow,
                    source_reference=source_reference,
                    reason=reason,
                    metadata=metadata,
                )
                managed_connection.commit()
                return result
        return self._assign_with_connection(
            connection,
            asset_id=asset_id,
            destination=destination,
            creator_profile_id=creator_profile_id,
            assigned_by_profile_id=assigned_by_profile_id,
            source_workflow=source_workflow,
            source_reference=source_reference,
            reason=reason,
            metadata=metadata,
        )

    def _assign_with_connection(
        self,
        connection,
        *,
        asset_id: int,
        destination: ContentDestination,
        creator_profile_id: int | None,
        assigned_by_profile_id: int | None,
        source_workflow: str | None,
        source_reference: str | None,
        reason: str | None,
        metadata: Mapping[str, Any] | None,
    ) -> AssetContentDestination:
        with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.asset_content_destinations "
                    "WHERE asset_id=%s FOR UPDATE",
                    (int(asset_id),),
                )
                existing = cursor.fetchone()
                if existing is None:
                    cursor.execute(
                        """
                        INSERT INTO public.asset_content_destinations (
                            asset_id, destination, creator_profile_id,
                            assigned_by_profile_id, source_workflow,
                            source_reference, reason, metadata, schema_version
                        )
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                        RETURNING *
                        """,
                        (
                            int(asset_id),
                            destination.value,
                            creator_profile_id,
                            assigned_by_profile_id,
                            source_workflow,
                            source_reference,
                            reason,
                            json.dumps(dict(metadata or {}), default=str),
                            CONTENT_DESTINATION_SCHEMA_VERSION,
                        ),
                    )
                    row = cursor.fetchone()
                elif str(existing["destination"]) == destination.value:
                    row = existing
                else:
                    cursor.execute(
                        """
                        UPDATE public.asset_content_destinations
                        SET destination=%s,
                            assigned_by_profile_id=%s,
                            source_workflow=%s,
                            source_reference=%s,
                            reason=%s,
                            metadata=%s::jsonb,
                            assigned_at=now(),
                            updated_at=now(),
                            schema_version=%s
                        WHERE asset_id=%s
                        RETURNING *
                        """,
                        (
                            destination.value,
                            assigned_by_profile_id,
                            source_workflow,
                            source_reference,
                            reason,
                            json.dumps(dict(metadata or {}), default=str),
                            CONTENT_DESTINATION_SCHEMA_VERSION,
                            int(asset_id),
                        ),
                    )
                    row = cursor.fetchone()
        if row is None:
            raise ContentDestinationConflictError(
                f"Content Destination assignment failed for Asset {asset_id}."
            )
        return self._destination_from_row(row)

    def list_available_asset_ids(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 500,
    ) -> tuple[int, ...]:
        filters = [
            "d.destination=%s",
            "COALESCE(a.is_active, TRUE)=TRUE",
            "COALESCE(a.status, '')<>'archived'",
        ]
        params: list[Any] = [ContentDestination.AVAILABLE_INVENTORY.value]
        if creator_profile_id is not None:
            filters.append("a.creator_profile_id=%s")
            params.append(int(creator_profile_id))
        params.append(max(0, int(limit)))
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT d.asset_id
                    FROM public.asset_content_destinations d
                    JOIN public.content_items a ON a.id=d.asset_id
                    WHERE {' AND '.join(filters)}
                    ORDER BY a.created_at DESC NULLS LAST, d.asset_id DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(int(row["asset_id"]) for row in rows)

    def list_history(
        self, asset_id: int, *, limit: int = 100
    ) -> tuple[ContentDestinationHistoryEntry, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.asset_content_destination_history
                    WHERE asset_id=%s
                    ORDER BY created_at DESC, history_id DESC
                    LIMIT %s
                    """,
                    (int(asset_id), max(0, int(limit))),
                )
                rows = cursor.fetchall()
        return tuple(self._history_from_row(row) for row in rows)

    @classmethod
    def _destination_from_row(
        cls, row: Mapping[str, Any]
    ) -> AssetContentDestination:
        return AssetContentDestination(
            asset_id=int(row["asset_id"]),
            destination=ContentDestination(str(row["destination"])),
            creator_profile_id=row.get("creator_profile_id"),
            assigned_by_profile_id=row.get("assigned_by_profile_id"),
            source_workflow=row.get("source_workflow"),
            source_reference=row.get("source_reference"),
            reason=row.get("reason"),
            metadata=cls._mapping(row.get("metadata")),
            assigned_at=cls._datetime(row.get("assigned_at")),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            schema_version=str(
                row.get("schema_version") or CONTENT_DESTINATION_SCHEMA_VERSION
            ),
        )

    @classmethod
    def _history_from_row(
        cls, row: Mapping[str, Any]
    ) -> ContentDestinationHistoryEntry:
        previous = row.get("previous_destination")
        return ContentDestinationHistoryEntry(
            history_id=int(row["history_id"]),
            asset_id=int(row["asset_id"]),
            event_type=str(row["event_type"]),
            previous_destination=(
                ContentDestination(str(previous)) if previous is not None else None
            ),
            new_destination=ContentDestination(str(row["new_destination"])),
            assigned_by_profile_id=row.get("assigned_by_profile_id"),
            source_workflow=row.get("source_workflow"),
            source_reference=row.get("source_reference"),
            reason=row.get("reason"),
            metadata=cls._mapping(row.get("metadata")),
            created_at=cls._datetime(row.get("created_at")),
            schema_version=str(
                row.get("schema_version") or CONTENT_DESTINATION_SCHEMA_VERSION
            ),
        )

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value)) if value else None
