"""PostgreSQL persistence for Commercial Role assignments and history."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.commercial_role import (
    COMMERCIAL_ROLE_VOCABULARY_VERSION,
    CommercialRole,
    CommercialRoleActorType,
    CommercialRoleAssignment,
    CommercialRoleHistoryEntry,
    CommercialRoleOrigin,
    CommercialRoleState,
)


class CommercialRoleRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get(
        self, *, asset_id: int, creator_profile_id: int, role: CommercialRole,
    ) -> CommercialRoleAssignment | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commercial_role_assignments
                       WHERE asset_id=%s AND creator_profile_id=%s AND role=%s""",
                    (int(asset_id), int(creator_profile_id), role.value),
                )
                row = cursor.fetchone()
        return self._assignment(row) if row else None

    def create(
        self, *, asset_id: int, creator_profile_id: int, role: CommercialRole,
        state: CommercialRoleState, origin: CommercialRoleOrigin,
        rationale: str | None, suggestion_confidence: float | None,
        evidence: Mapping, actor_type: CommercialRoleActorType,
        actor_identifier: str | None, event_type: str,
    ) -> CommercialRoleAssignment:
        assignment_id = uuid4()
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commercial_role_assignments
                       (assignment_id,asset_id,creator_profile_id,role,state,origin,
                        rationale,suggestion_confidence,evidence,assigned_by_type,
                        assigned_by_identifier,vocabulary_version)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s)
                       RETURNING *""",
                    (
                        assignment_id, int(asset_id), int(creator_profile_id),
                        role.value, state.value, origin.value, rationale,
                        suggestion_confidence, json.dumps(dict(evidence or {}), default=str),
                        actor_type.value, actor_identifier,
                        COMMERCIAL_ROLE_VOCABULARY_VERSION,
                    ),
                )
                row = cursor.fetchone()
                self._record_history(
                    cursor, row=row, event_type=event_type, previous_state=None,
                    actor_type=actor_type, actor_identifier=actor_identifier,
                    reason=rationale,
                )
        return self._assignment(row)

    def transition(
        self, *, assignment_id: UUID, creator_profile_id: int,
        expected_state: CommercialRoleState, new_state: CommercialRoleState,
        actor_type: CommercialRoleActorType, actor_identifier: str | None,
        event_type: str, reason: str | None,
        origin: CommercialRoleOrigin | None = None,
    ) -> CommercialRoleAssignment | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commercial_role_assignments
                       WHERE assignment_id=%s AND creator_profile_id=%s
                       FOR UPDATE""",
                    (assignment_id, int(creator_profile_id)),
                )
                current = cursor.fetchone()
                if current is None or current["state"] != expected_state.value:
                    return None
                cursor.execute(
                    """UPDATE public.commercial_role_assignments
                       SET state=%s,
                           origin=COALESCE(%s,origin),
                           assigned_by_type=%s,
                           assigned_by_identifier=%s,
                           updated_at=now()
                       WHERE assignment_id=%s RETURNING *""",
                    (
                        new_state.value, origin.value if origin else None,
                        actor_type.value, actor_identifier, assignment_id,
                    ),
                )
                row = cursor.fetchone()
                self._record_history(
                    cursor, row=row, event_type=event_type,
                    previous_state=expected_state, actor_type=actor_type,
                    actor_identifier=actor_identifier, reason=reason,
                )
        return self._assignment(row)

    def list_for_asset(
        self, *, asset_id: int, creator_profile_id: int,
        states: tuple[CommercialRoleState, ...] | None = None,
    ) -> tuple[CommercialRoleAssignment, ...]:
        clauses = ["asset_id=%s", "creator_profile_id=%s"]
        params: list = [int(asset_id), int(creator_profile_id)]
        if states:
            clauses.append("state=ANY(%s)")
            params.append([state.value for state in states])
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT * FROM public.commercial_role_assignments
                        WHERE {' AND '.join(clauses)}
                        ORDER BY role,created_at,assignment_id""",
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(self._assignment(row) for row in rows)

    def list_history(
        self, *, asset_id: int, creator_profile_id: int,
    ) -> tuple[CommercialRoleHistoryEntry, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commercial_role_history
                       WHERE asset_id=%s AND creator_profile_id=%s
                       ORDER BY created_at,history_id""",
                    (int(asset_id), int(creator_profile_id)),
                )
                rows = cursor.fetchall()
        return tuple(self._history(row) for row in rows)

    @staticmethod
    def _record_history(
        cursor, *, row, event_type: str,
        previous_state: CommercialRoleState | None,
        actor_type: CommercialRoleActorType, actor_identifier: str | None,
        reason: str | None,
    ) -> None:
        cursor.execute(
            """INSERT INTO public.commercial_role_history
               (assignment_id,asset_id,creator_profile_id,role,event_type,
                previous_state,new_state,actor_type,actor_identifier,reason)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (
                row["assignment_id"], row["asset_id"], row["creator_profile_id"],
                row["role"], event_type,
                previous_state.value if previous_state else None,
                row["state"], actor_type.value, actor_identifier, reason,
            ),
        )

    @classmethod
    def _assignment(cls, row) -> CommercialRoleAssignment:
        return CommercialRoleAssignment(
            assignment_id=UUID(str(row["assignment_id"])),
            asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            role=CommercialRole(row["role"]),
            state=CommercialRoleState(row["state"]),
            origin=CommercialRoleOrigin(row["origin"]),
            rationale=row.get("rationale"),
            suggestion_confidence=(
                float(row["suggestion_confidence"])
                if row.get("suggestion_confidence") is not None else None
            ),
            evidence=cls._mapping(row.get("evidence")),
            assigned_by_type=(
                CommercialRoleActorType(row["assigned_by_type"])
                if row.get("assigned_by_type") else None
            ),
            assigned_by_identifier=row.get("assigned_by_identifier"),
            vocabulary_version=str(
                row.get("vocabulary_version")
                or COMMERCIAL_ROLE_VOCABULARY_VERSION
            ),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _history(row) -> CommercialRoleHistoryEntry:
        return CommercialRoleHistoryEntry(
            history_id=int(row["history_id"]),
            assignment_id=UUID(str(row["assignment_id"])),
            asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            role=CommercialRole(row["role"]),
            event_type=str(row["event_type"]),
            previous_state=(
                CommercialRoleState(row["previous_state"])
                if row.get("previous_state") else None
            ),
            new_state=CommercialRoleState(row["new_state"]),
            actor_type=CommercialRoleActorType(row["actor_type"]),
            actor_identifier=row.get("actor_identifier"),
            reason=row.get("reason"),
            created_at=row["created_at"],
        )

    @staticmethod
    def _mapping(value) -> dict:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}
