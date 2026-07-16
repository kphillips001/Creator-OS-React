"""PostgreSQL persistence boundary for intelligence runs and executions."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any

from app.database import get_db_connection
from app.models.asset_intelligence_execution import (
    AssetIntelligenceErrorCode,
    AssetIntelligenceProviderExecution,
    AssetIntelligenceRun,
    AssetIntelligenceRunStatus,
    ProviderExecutionStatus,
)


class AssetIntelligenceRunRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def create_run(self, run: AssetIntelligenceRun) -> AssetIntelligenceRun:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                if run.is_current:
                    cursor.execute(
                        "UPDATE asset_intelligence_runs SET is_current=false, updated_at=now() "
                        "WHERE asset_id=%s AND is_current=true",
                        (run.asset_id,),
                    )
                cursor.execute(
                    """INSERT INTO asset_intelligence_runs
                    (run_id,asset_id,creator_profile_id,schema_version,status,is_current,
                     required_providers,optional_providers,started_at,completed_at,error_summary)
                    VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s::jsonb)
                    RETURNING *""",
                    (run.run_id, run.asset_id, run.creator_profile_id, run.schema_version,
                     run.status.value, run.is_current, json.dumps(run.required_providers),
                     json.dumps(run.optional_providers), run.started_at, run.completed_at,
                     json.dumps(dict(run.error_summary))),
                )
                return self._run(cursor.fetchone())

    def get_run(self, run_id: str) -> AssetIntelligenceRun | None:
        return self._one_run("SELECT * FROM asset_intelligence_runs WHERE run_id=%s", (run_id,))

    def get_current_run(self, asset_id: int) -> AssetIntelligenceRun | None:
        return self._one_run(
            "SELECT * FROM asset_intelligence_runs WHERE asset_id=%s AND is_current=true",
            (asset_id,),
        )

    def list_runs(self, asset_id: int) -> tuple[AssetIntelligenceRun, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM asset_intelligence_runs WHERE asset_id=%s ORDER BY created_at,run_id",
                    (asset_id,),
                )
                return tuple(self._run(row) for row in cursor.fetchall())

    def update_run(self, run: AssetIntelligenceRun) -> AssetIntelligenceRun:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE asset_intelligence_runs SET status=%s,is_current=%s,
                    started_at=%s,completed_at=%s,error_summary=%s::jsonb,updated_at=now()
                    WHERE run_id=%s RETURNING *""",
                    (run.status.value, run.is_current, run.started_at, run.completed_at,
                     json.dumps(dict(run.error_summary)), run.run_id),
                )
                row = cursor.fetchone()
        if not row:
            raise LookupError(f"Analysis run not found: {run.run_id}")
        return self._run(row)

    def next_attempt_number(self, run_id: str, provider_name: str) -> int:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT COALESCE(MAX(attempt_number),0)+1 AS attempt FROM asset_intelligence_provider_executions WHERE run_id=%s AND provider_name=%s",
                    (run_id, provider_name),
                )
                return int(cursor.fetchone()["attempt"])

    def create_execution(self, execution: AssetIntelligenceProviderExecution) -> AssetIntelligenceProviderExecution:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO asset_intelligence_provider_executions
                    (execution_id,run_id,asset_id,creator_profile_id,provider_name,provider_version,
                     attempt_number,is_required,status,result_id,started_at,completed_at,duration_ms,
                     error_code,error_message) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    ON CONFLICT (run_id,provider_name,attempt_number) DO UPDATE SET
                    updated_at=asset_intelligence_provider_executions.updated_at RETURNING *""",
                    (execution.execution_id, execution.run_id, execution.asset_id,
                     execution.creator_profile_id, execution.provider_name, execution.provider_version,
                     execution.attempt_number, execution.is_required, execution.status.value,
                     execution.result_id, execution.started_at, execution.completed_at,
                     execution.duration_ms, execution.error_code.value if execution.error_code else None,
                     execution.error_message),
                )
                return self._execution(cursor.fetchone())

    def complete_execution(self, execution: AssetIntelligenceProviderExecution) -> AssetIntelligenceProviderExecution:
        """Settle once; duplicate/stale callbacks cannot downgrade a success."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE asset_intelligence_provider_executions SET
                    status=%s,result_id=%s,started_at=COALESCE(started_at,%s),completed_at=%s,
                    duration_ms=%s,error_code=%s,error_message=%s,updated_at=now()
                    WHERE execution_id=%s AND status NOT IN ('SUCCEEDED','FAILED','TIMED_OUT','SKIPPED','CANCELLED')
                    RETURNING *""",
                    (execution.status.value, execution.result_id, execution.started_at,
                     execution.completed_at, execution.duration_ms,
                     execution.error_code.value if execution.error_code else None,
                     execution.error_message, execution.execution_id),
                )
                row = cursor.fetchone()
                if not row:
                    cursor.execute("SELECT * FROM asset_intelligence_provider_executions WHERE execution_id=%s", (execution.execution_id,))
                    row = cursor.fetchone()
        if not row:
            raise LookupError(f"Provider execution not found: {execution.execution_id}")
        return self._execution(row)

    def list_executions(self, run_id: str) -> tuple[AssetIntelligenceProviderExecution, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT * FROM asset_intelligence_provider_executions WHERE run_id=%s ORDER BY provider_name,attempt_number", (run_id,))
                return tuple(self._execution(row) for row in cursor.fetchall())

    def latest_executions(self, run_id: str) -> tuple[AssetIntelligenceProviderExecution, ...]:
        executions = self.list_executions(run_id)
        latest: dict[str, AssetIntelligenceProviderExecution] = {}
        for execution in executions:
            current = latest.get(execution.provider_name)
            if current is None or execution.attempt_number > current.attempt_number:
                latest[execution.provider_name] = execution
        return tuple(latest[name] for name in sorted(latest))

    def _one_run(self, sql: str, params: tuple[Any, ...]) -> AssetIntelligenceRun | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                row = cursor.fetchone()
        return self._run(row) if row else None

    @staticmethod
    def _run(row: Mapping[str, Any]) -> AssetIntelligenceRun:
        return AssetIntelligenceRun(
            run_id=str(row["run_id"]), asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]), schema_version=str(row["schema_version"]),
            status=AssetIntelligenceRunStatus(row["status"]), is_current=bool(row["is_current"]),
            required_providers=tuple(row.get("required_providers") or ()),
            optional_providers=tuple(row.get("optional_providers") or ()),
            started_at=row.get("started_at"), completed_at=row.get("completed_at"),
            error_summary=dict(row.get("error_summary") or {}), created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )

    @staticmethod
    def _execution(row: Mapping[str, Any]) -> AssetIntelligenceProviderExecution:
        return AssetIntelligenceProviderExecution(
            execution_id=str(row["execution_id"]), run_id=str(row["run_id"]),
            asset_id=int(row["asset_id"]), creator_profile_id=int(row["creator_profile_id"]),
            provider_name=str(row["provider_name"]), provider_version=row.get("provider_version"),
            attempt_number=int(row["attempt_number"]), is_required=bool(row["is_required"]),
            status=ProviderExecutionStatus(row["status"]), result_id=row.get("result_id"),
            started_at=row.get("started_at"), completed_at=row.get("completed_at"),
            duration_ms=row.get("duration_ms"),
            error_code=AssetIntelligenceErrorCode(row["error_code"]) if row.get("error_code") else None,
            error_message=row.get("error_message"), created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
        )
