"""PostgreSQL persistence for autonomous issue-resolution history."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection


class AutonomousIssueResolutionRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def create(
        self, *, issue_identifier: str, issue_snapshot: dict[str, Any],
        decision: str, decision_reason: str, required_action: str | None,
        destination_path: str | None, validation_status: str, outcome: str,
    ) -> dict[str, Any]:
        return self._required(
            """INSERT INTO public.autonomous_issue_resolutions(
                   resolution_id,issue_identifier,issue_snapshot,decision,
                   decision_reason,required_action,destination_path,
                   validation_status,outcome,resolved_at
               ) VALUES(%s,%s,%s::JSONB,%s,%s,%s,%s,%s,%s,
                        CASE WHEN %s IN ('USER_ACTION_REQUIRED','ALREADY_RESOLVED')
                             THEN NOW() END) RETURNING *""",
            (uuid4(), issue_identifier, json.dumps(issue_snapshot), decision,
             decision_reason, required_action, destination_path,
             validation_status, outcome, outcome),
        )

    def attach_execution(
        self, resolution_id: UUID, *, task_id: UUID, execution_id: UUID,
    ) -> dict[str, Any]:
        return self._required(
            """UPDATE public.autonomous_issue_resolutions SET
                   developer_agent_task_id=%s,developer_agent_execution_id=%s,
                   updated_at=NOW() WHERE resolution_id=%s RETURNING *""",
            (task_id, execution_id, resolution_id),
        )

    def finalize(
        self, resolution_id: UUID, *, validation_status: str, outcome: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        return self._required(
            """UPDATE public.autonomous_issue_resolutions SET
                   validation_status=%s,outcome=%s,
                   validation_evidence=%s::JSONB,resolved_at=NOW(),updated_at=NOW()
               WHERE resolution_id=%s RETURNING *""",
            (validation_status, outcome, json.dumps(evidence), resolution_id),
        )

    def get(self, resolution_id: UUID) -> dict[str, Any] | None:
        return self._one(
            "SELECT * FROM public.autonomous_issue_resolutions WHERE resolution_id=%s",
            (resolution_id,),
        )

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._all(
            """SELECT * FROM public.autonomous_issue_resolutions
               ORDER BY created_at DESC LIMIT %s""",
            (max(1, min(limit, 100)),),
        )

    def _one(self, query: str, params: tuple) -> dict[str, Any] | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            row = cursor.fetchone()
        return dict(row) if row else None

    def _all(self, query: str, params: tuple) -> list[dict[str, Any]]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]

    def _required(self, query: str, params: tuple) -> dict[str, Any]:
        row = self._one(query, params)
        if row is None:
            raise ValueError("Autonomous issue resolution was not found.")
        return row
