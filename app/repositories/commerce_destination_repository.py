"""Persistence for Commerce Destination history and routing intents."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.database import get_db_connection
from app.models.commerce_destination import (
    COMMERCE_DESTINATION_SCHEMA_VERSION,
    CommerceDestination,
    CommerceDestinationHistoryEntry,
    DestinationRoutingIntent,
    DestinationRoutingOwner,
    DestinationRoutingStatus,
)


class CommerceDestinationRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def append_history(
        self,
        entry: CommerceDestinationHistoryEntry,
    ) -> CommerceDestinationHistoryEntry:
        with self._connection_factory() as conn:
            self._ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.commerce_destination_history (
                        history_id,
                        asset_id,
                        registration_id,
                        previous_destination,
                        new_destination,
                        creator_profile_id,
                        creator_identity,
                        source_workflow,
                        source_session_id,
                        reason,
                        idempotency_key,
                        metadata,
                        schema_version,
                        created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s, %s, %s, %s,
                        %s::jsonb, %s, COALESCE(%s::timestamptz, now())
                    )
                    RETURNING *
                    """,
                    (
                        entry.history_id,
                        int(entry.asset_id),
                        entry.registration_id,
                        entry.previous_destination.value
                        if entry.previous_destination
                        else None,
                        entry.new_destination.value if entry.new_destination else None,
                        entry.creator_profile_id,
                        json.dumps(dict(entry.creator_identity or {}), default=str),
                        entry.source_workflow,
                        entry.source_session_id,
                        entry.reason,
                        entry.idempotency_key,
                        json.dumps(dict(entry.metadata or {}), default=str),
                        entry.schema_version,
                        entry.created_at,
                    ),
                )
                row = cursor.fetchone()
        return self._history_from_row(row)

    def history_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> CommerceDestinationHistoryEntry | None:
        if not str(idempotency_key or "").strip():
            return None
        with self._connection_factory() as conn:
            self._ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.commerce_destination_history
                    WHERE idempotency_key = %s
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (str(idempotency_key),),
                )
                row = cursor.fetchone()
        return self._history_from_row(row) if row else None

    def list_history(
        self,
        asset_id: int,
        *,
        limit: int = 100,
    ) -> tuple[CommerceDestinationHistoryEntry, ...]:
        with self._connection_factory() as conn:
            self._ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.commerce_destination_history
                    WHERE asset_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (int(asset_id), int(limit)),
                )
                rows = cursor.fetchall()
        return tuple(self._history_from_row(row) for row in rows)

    def upsert_routing_intent(
        self,
        intent: DestinationRoutingIntent,
    ) -> DestinationRoutingIntent:
        with self._connection_factory() as conn:
            self._ensure_routing_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.commerce_destination_routing_intents (
                        routing_intent_id,
                        asset_id,
                        registration_id,
                        selected_destination,
                        routing_owner,
                        routing_status,
                        source_workflow,
                        downstream_owner_service,
                        downstream_prerequisites,
                        metadata,
                        schema_version,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s,
                        COALESCE(%s::timestamptz, now()), now()
                    )
                    ON CONFLICT (routing_intent_id)
                    DO UPDATE SET
                        selected_destination = EXCLUDED.selected_destination,
                        routing_status = EXCLUDED.routing_status,
                        source_workflow = EXCLUDED.source_workflow,
                        downstream_owner_service = EXCLUDED.downstream_owner_service,
                        downstream_prerequisites = EXCLUDED.downstream_prerequisites,
                        metadata = EXCLUDED.metadata,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = now()
                    RETURNING *
                    """,
                    (
                        intent.routing_intent_id,
                        int(intent.asset_id),
                        intent.registration_id,
                        intent.selected_destination.value,
                        intent.routing_owner.value,
                        intent.routing_status.value,
                        intent.source_workflow,
                        intent.downstream_owner_service,
                        json.dumps(list(intent.downstream_prerequisites), default=str),
                        json.dumps(dict(intent.metadata or {}), default=str),
                        intent.schema_version,
                        intent.created_at,
                    ),
                )
                row = cursor.fetchone()
        return self._intent_from_row(row)

    def list_routing_intents(
        self,
        asset_id: int,
        *,
        include_cancelled: bool = True,
    ) -> tuple[DestinationRoutingIntent, ...]:
        status_filter = "" if include_cancelled else "AND routing_status <> 'CANCELLED'"
        with self._connection_factory() as conn:
            self._ensure_routing_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM public.commerce_destination_routing_intents
                    WHERE asset_id = %s
                    {status_filter}
                    ORDER BY created_at ASC, routing_owner ASC
                    """,
                    (int(asset_id),),
                )
                rows = cursor.fetchall()
        return tuple(self._intent_from_row(row) for row in rows)

    def list_pending_routing_intents(
        self,
        *,
        limit: int = 100,
    ) -> tuple[DestinationRoutingIntent, ...]:
        with self._connection_factory() as conn:
            self._ensure_routing_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.commerce_destination_routing_intents
                    WHERE routing_status = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (DestinationRoutingStatus.ROUTING_PENDING.value, int(limit)),
                )
                rows = cursor.fetchall()
        return tuple(self._intent_from_row(row) for row in rows)

    @staticmethod
    def _ensure_history_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.commerce_destination_history') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.commerce_destination_history. Run forward migrations before using CommerceDestinationRepository."
            )

    @staticmethod
    def _ensure_routing_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.commerce_destination_routing_intents') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.commerce_destination_routing_intents. Run forward migrations before using CommerceDestinationRepository."
            )

    @classmethod
    def _history_from_row(
        cls,
        row: Mapping[str, Any],
    ) -> CommerceDestinationHistoryEntry:
        return CommerceDestinationHistoryEntry(
            history_id=UUID(str(row["history_id"])),
            asset_id=int(row["asset_id"]),
            registration_id=UUID(str(row["registration_id"])),
            previous_destination=cls._destination_or_none(
                row.get("previous_destination")
            ),
            new_destination=cls._destination_or_none(row.get("new_destination")),
            creator_profile_id=row.get("creator_profile_id"),
            creator_identity=cls._mapping(row.get("creator_identity")),
            source_workflow=row.get("source_workflow"),
            source_session_id=row.get("source_session_id"),
            reason=row.get("reason"),
            idempotency_key=row.get("idempotency_key"),
            metadata=cls._mapping(row.get("metadata")),
            created_at=cls._datetime(row.get("created_at")),
            schema_version=str(
                row.get("schema_version") or COMMERCE_DESTINATION_SCHEMA_VERSION
            ),
        )

    @classmethod
    def _intent_from_row(cls, row: Mapping[str, Any]) -> DestinationRoutingIntent:
        return DestinationRoutingIntent(
            routing_intent_id=UUID(str(row["routing_intent_id"])),
            asset_id=int(row["asset_id"]),
            registration_id=UUID(str(row["registration_id"])),
            selected_destination=CommerceDestination(str(row["selected_destination"])),
            routing_owner=DestinationRoutingOwner(str(row["routing_owner"])),
            routing_status=DestinationRoutingStatus(str(row["routing_status"])),
            source_workflow=row.get("source_workflow"),
            downstream_owner_service=row.get("downstream_owner_service"),
            downstream_prerequisites=cls._tuple(row.get("downstream_prerequisites")),
            metadata=cls._mapping(row.get("metadata")),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            schema_version=str(
                row.get("schema_version") or COMMERCE_DESTINATION_SCHEMA_VERSION
            ),
        )

    @staticmethod
    def _destination_or_none(value: Any) -> CommerceDestination | None:
        if value is None:
            return None
        try:
            return CommerceDestination(str(value))
        except Exception:
            return None

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
    def _tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return (value,) if value.strip() else ()
            value = parsed
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item).strip())
        return (str(value),) if str(value).strip() else ()

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        return datetime.fromisoformat(str(value))
