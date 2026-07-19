"""Atomic PostgreSQL persistence for worker heartbeat state."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Mapping

from psycopg.types.json import Json, Jsonb

from app.database import get_db_connection
from app.models.worker_heartbeat import WorkerHeartbeat, WorkerHeartbeatStatus


class WorkerHeartbeatRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def register(self, heartbeat: WorkerHeartbeat) -> WorkerHeartbeat:
        with self.connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.worker_heartbeats (
                        heartbeat_id, worker_name, worker_instance_id, worker_type,
                        creator_profile_id, account_id, process_id, host_name,
                        application_version, status, started_at, last_heartbeat_at,
                        metadata, created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW())
                    ON CONFLICT (worker_instance_id) DO UPDATE SET
                        worker_name=EXCLUDED.worker_name, worker_type=EXCLUDED.worker_type,
                        creator_profile_id=EXCLUDED.creator_profile_id, account_id=EXCLUDED.account_id,
                        process_id=EXCLUDED.process_id, host_name=EXCLUDED.host_name,
                        application_version=EXCLUDED.application_version, status=EXCLUDED.status,
                        started_at=EXCLUDED.started_at, last_heartbeat_at=EXCLUDED.last_heartbeat_at,
                        shutdown_at=NULL, metadata=EXCLUDED.metadata, updated_at=NOW()
                    RETURNING *
                    """,
                    (heartbeat.heartbeat_id, heartbeat.worker_name, heartbeat.worker_instance_id, heartbeat.worker_type,
                     heartbeat.creator_profile_id, heartbeat.account_id, heartbeat.process_id, heartbeat.host_name,
                     heartbeat.application_version, heartbeat.status.value, heartbeat.started_at,
                     heartbeat.last_heartbeat_at, Json(dict(heartbeat.metadata))),
                )
                row = cursor.fetchone()
            conn.commit()
        return WorkerHeartbeat.from_row(row)

    def record_heartbeat(self, instance_id: str, *, status: WorkerHeartbeatStatus, at: datetime, metadata: Mapping[str, Any] | None = None) -> WorkerHeartbeat | None:
        return self._update(instance_id, "status=%s, last_heartbeat_at=%s, metadata=metadata || %s, updated_at=NOW()", (status.value, at, Jsonb(dict(metadata or {}))))

    def record_poll(self, instance_id: str, *, at: datetime) -> WorkerHeartbeat | None:
        return self._update(instance_id, "status='RUNNING', last_poll_at=%s, last_heartbeat_at=%s, updated_at=NOW()", (at, at))

    def record_success(self, instance_id: str, *, at: datetime, idle: bool) -> WorkerHeartbeat | None:
        return self._update(instance_id, "status=%s, last_success_at=%s, last_heartbeat_at=%s, last_error=NULL, updated_at=NOW()", (WorkerHeartbeatStatus.IDLE.value if idle else WorkerHeartbeatStatus.RUNNING.value, at, at))

    def record_failure(self, instance_id: str, *, at: datetime, error: str) -> WorkerHeartbeat | None:
        return self._update(instance_id, "status='DEGRADED', last_failure_at=%s, last_heartbeat_at=%s, last_error=%s, updated_at=NOW()", (at, at, error))

    def record_shutdown(self, instance_id: str, *, at: datetime, status: WorkerHeartbeatStatus) -> WorkerHeartbeat | None:
        return self._update(instance_id, "status=%s, last_heartbeat_at=%s, shutdown_at=%s, updated_at=NOW()", (status.value, at, at if status == WorkerHeartbeatStatus.STOPPED else None))

    def get_by_instance(self, instance_id: str) -> WorkerHeartbeat | None:
        rows = self._select("WHERE worker_instance_id=%s", (instance_id,))
        return rows[0] if rows else None

    def list_latest_per_worker(self, *, creator_profile_id: str | None = None, account_id: int | None = None) -> tuple[WorkerHeartbeat, ...]:
        filters, params = [], []
        if creator_profile_id is not None:
            filters.append("(creator_profile_id=%s OR creator_profile_id IS NULL)"); params.append(str(creator_profile_id))
        if account_id is not None:
            filters.append("(account_id=%s OR account_id IS NULL)"); params.append(account_id)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        with self.connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT DISTINCT ON (worker_name) * FROM public.worker_heartbeats {where} ORDER BY worker_name, last_heartbeat_at DESC", tuple(params))
                rows = cursor.fetchall()
        return tuple(WorkerHeartbeat.from_row(row) for row in rows)

    def list_recent_instances(self, *, since: datetime, creator_profile_id: str | None = None, account_id: int | None = None) -> tuple[WorkerHeartbeat, ...]:
        filters, params = ["last_heartbeat_at >= %s"], [since]
        if creator_profile_id is not None: filters.append("(creator_profile_id=%s OR creator_profile_id IS NULL)"); params.append(str(creator_profile_id))
        if account_id is not None: filters.append("(account_id=%s OR account_id IS NULL)"); params.append(account_id)
        return self._select(f"WHERE {' AND '.join(filters)} ORDER BY last_heartbeat_at DESC", tuple(params))

    def classify_stale_instances(self, *, threshold_seconds: int, now: datetime | None = None) -> tuple[WorkerHeartbeat, ...]:
        cutoff = (now or datetime.now(timezone.utc)) - timedelta(seconds=max(1, threshold_seconds))
        return self._select("WHERE last_heartbeat_at < %s AND status NOT IN ('STOPPED','FAILED') ORDER BY last_heartbeat_at", (cutoff,))

    def _update(self, instance_id: str, assignments: str, params: tuple[Any, ...]) -> WorkerHeartbeat | None:
        with self.connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(f"UPDATE public.worker_heartbeats SET {assignments} WHERE worker_instance_id=%s RETURNING *", (*params, instance_id))
                row = cursor.fetchone()
            conn.commit()
        return WorkerHeartbeat.from_row(row) if row else None

    def _select(self, suffix: str, params: tuple[Any, ...]) -> tuple[WorkerHeartbeat, ...]:
        with self.connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(f"SELECT * FROM public.worker_heartbeats {suffix}", params); rows = cursor.fetchall()
        return tuple(WorkerHeartbeat.from_row(row) for row in rows)

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.worker_heartbeats') AS table_ref"); row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError("Missing public.worker_heartbeats. Apply 20260719_001_worker_heartbeats.sql.")
