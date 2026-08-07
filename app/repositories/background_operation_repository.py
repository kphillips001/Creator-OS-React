"""PostgreSQL claim authority for application-wide background operations."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.background_operation import BackgroundOperation


class BackgroundOperationRepository:
    def __init__(self, connection_factory=get_db_connection) -> None:
        self.connection_factory = connection_factory

    def create(self, *, operation_type: str, originating_workspace: str,
               creator_profile_id: int, account_id: int | None, subject_type: str,
               subject_id: str, idempotency_key: str, executor_key: str,
               progress_total: int = 0, current_stage: str | None = None,
               stage_message: str | None = None, result_location: str | None = None,
               cancellation_supported: bool = False,
               metadata: Mapping[str, Any] | None = None) -> tuple[BackgroundOperation, bool]:
        operation_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.background_operations(
                     operation_id,operation_type,originating_workspace,creator_profile_id,
                     account_id,subject_type,subject_id,idempotency_key,executor_key,
                     progress_total,current_stage,stage_message,result_location,
                     cancellation_supported,metadata)
                   VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                   ON CONFLICT (creator_profile_id,idempotency_key)
                   WHERE status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED')
                   DO NOTHING RETURNING *""",
                (operation_id, operation_type, originating_workspace, int(creator_profile_id),
                 account_id, subject_type, subject_id, idempotency_key, executor_key,
                 max(0, int(progress_total)), current_stage, stage_message, result_location,
                 bool(cancellation_supported), json.dumps(dict(metadata or {}))),
            )
            row = cursor.fetchone()
            created = row is not None
            if row is None:
                cursor.execute(
                    """SELECT * FROM public.background_operations
                       WHERE creator_profile_id=%s AND idempotency_key=%s
                         AND status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED')
                       ORDER BY created_at DESC LIMIT 1""",
                    (int(creator_profile_id), idempotency_key),
                )
                row = cursor.fetchone()
            if created:
                self._insert_event(cursor, operation_id, "CREATED", None, "QUEUED",
                                   current_stage, stage_message or "Operation queued", {})
        return BackgroundOperation.from_row(row), created

    def get(self, operation_id: UUID | str, *, creator_profile_id: int,
            account_id: int | None = None) -> BackgroundOperation | None:
        params: list[Any] = [operation_id, int(creator_profile_id)]
        account_clause = ""
        if account_id is not None:
            account_clause = " AND (account_id IS NULL OR account_id=%s)"
            params.append(int(account_id))
        return self._one(
            f"SELECT * FROM public.background_operations WHERE operation_id=%s AND creator_profile_id=%s{account_clause}",
            tuple(params),
        )

    def list_active(self, *, creator_profile_id: int, account_id: int | None = None,
                    workspace: str | None = None, subject_type: str | None = None,
                    subject_id: str | None = None) -> tuple[BackgroundOperation, ...]:
        clauses = ["creator_profile_id=%s", "status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED')"]
        params: list[Any] = [int(creator_profile_id)]
        self._scope(clauses, params, account_id, workspace, subject_type, subject_id)
        return self._all("SELECT * FROM public.background_operations WHERE " + " AND ".join(clauses) + " ORDER BY created_at DESC", tuple(params))

    def list_recent_terminal(self, *, creator_profile_id: int, account_id: int | None = None,
                             workspace: str | None = None, limit: int = 20) -> tuple[BackgroundOperation, ...]:
        clauses = ["creator_profile_id=%s", "status IN ('SUCCEEDED','PARTIAL','FAILED','CANCELLED')"]
        params: list[Any] = [int(creator_profile_id)]
        self._scope(clauses, params, account_id, workspace, None, None)
        params.append(max(1, min(int(limit), 100)))
        return self._all("SELECT * FROM public.background_operations WHERE " + " AND ".join(clauses) + " ORDER BY completed_at DESC NULLS LAST,created_at DESC LIMIT %s", tuple(params))

    def claim_next(self, worker_id: str, *, lease_seconds: int = 60) -> BackgroundOperation | None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """WITH candidate AS (
                     SELECT operation_id,status FROM public.background_operations
                     WHERE status='QUEUED'
                        OR (status IN ('RUNNING','WAITING_EXTERNAL') AND lease_expires_at<NOW())
                     ORDER BY created_at FOR UPDATE SKIP LOCKED LIMIT 1
                   )
                   UPDATE public.background_operations operation
                   SET status='RUNNING',worker_id=%s,lease_expires_at=NOW()+(%s * INTERVAL '1 second'),
                       started_at=COALESCE(operation.started_at,NOW()),attempt_count=attempt_count+1,
                       updated_at=NOW()
                   FROM candidate WHERE operation.operation_id=candidate.operation_id
                   RETURNING operation.*,candidate.status AS claimed_previous_status""",
                (worker_id, max(10, int(lease_seconds))),
            )
            row = cursor.fetchone()
            if row:
                self._insert_event(cursor, row["operation_id"], "CLAIMED",
                                   row["claimed_previous_status"], "RUNNING",
                                   row.get("current_stage"), "Worker claimed operation",
                                   {"worker_id": worker_id})
        return BackgroundOperation.from_row(row) if row else None

    def renew_lease(self, operation_id: UUID | str, worker_id: str, *, lease_seconds: int = 60) -> bool:
        return self._execute(
            """UPDATE public.background_operations SET lease_expires_at=NOW()+(%s * INTERVAL '1 second'),updated_at=NOW()
               WHERE operation_id=%s AND worker_id=%s AND status IN ('RUNNING','WAITING_EXTERNAL') RETURNING operation_id""",
            (max(10, int(lease_seconds)), operation_id, worker_id),
        ) is not None

    def update_progress(self, operation_id: UUID | str, *, current: int, total: int,
                        percent: float, stage: str | None = None, message: str | None = None,
                        result_reference: str | None = None,
                        metadata: Mapping[str, Any] | None = None) -> BackgroundOperation:
        row = self._required(
            """UPDATE public.background_operations SET progress_current=%s,progress_total=%s,
               progress_percent=%s,current_stage=COALESCE(%s,current_stage),stage_message=COALESCE(%s,stage_message),
               result_reference=COALESCE(%s,result_reference),metadata=metadata||%s::jsonb,updated_at=NOW()
               WHERE operation_id=%s RETURNING *""",
            (max(0, int(current)), max(0, int(total)), max(0, min(100, float(percent))),
             stage, message, result_reference, json.dumps(dict(metadata or {})), operation_id),
        )
        self.append_event(operation_id, "PROGRESS", row.status, row.status, stage, message, metadata)
        return row

    def transition(self, operation_id: UUID | str, status: str, *, stage: str | None = None,
                   message: str | None = None, result_reference: str | None = None,
                   error_code: str | None = None, error_message: str | None = None,
                   metadata: Mapping[str, Any] | None = None) -> BackgroundOperation:
        prior = self._one_unscoped(operation_id)
        if prior is None:
            raise KeyError("Background Operation not found.")
        terminal = status in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}
        row = self._required(
            """UPDATE public.background_operations SET status=%s,current_stage=COALESCE(%s,current_stage),
               stage_message=COALESCE(%s,stage_message),result_reference=COALESCE(%s,result_reference),
               error_code=%s,error_message=%s,metadata=metadata||%s::jsonb,
               completed_at=CASE WHEN %s THEN NOW() ELSE completed_at END,
               lease_expires_at=CASE WHEN %s THEN NULL ELSE lease_expires_at END,updated_at=NOW()
               WHERE operation_id=%s RETURNING *""",
            (status, stage, message, result_reference, error_code, error_message,
             json.dumps(dict(metadata or {})), terminal, terminal, operation_id),
        )
        self.append_event(operation_id, status, prior.status, status, stage, message, metadata)
        return row

    def request_cancellation(self, operation_id: UUID | str, *, creator_profile_id: int) -> BackgroundOperation:
        operation = self.get(operation_id, creator_profile_id=creator_profile_id)
        if operation is None:
            raise KeyError("Background Operation not found.")
        if not operation.cancellation_supported:
            raise ValueError("This operation cannot be safely cancelled.")
        if operation.terminal:
            return operation
        next_status = "CANCELLED" if operation.status == "QUEUED" else "CANCEL_REQUESTED"
        row = self._required(
            """UPDATE public.background_operations SET status=%s,cancellation_requested_at=NOW(),
               completed_at=CASE WHEN %s='CANCELLED' THEN NOW() ELSE completed_at END,updated_at=NOW()
               WHERE operation_id=%s AND creator_profile_id=%s RETURNING *""",
            (next_status, next_status, operation_id, int(creator_profile_id)),
        )
        self.append_event(operation_id, next_status, operation.status, next_status,
                          "CANCELLED" if next_status == "CANCELLED" else operation.current_stage,
                          "Cancellation requested", {})
        return row

    def retry(self, operation_id: UUID | str, *, creator_profile_id: int) -> BackgroundOperation:
        operation = self.get(operation_id, creator_profile_id=creator_profile_id)
        if operation is None:
            raise KeyError("Background Operation not found.")
        if operation.status not in {"FAILED", "CANCELLED"}:
            raise ValueError("Only failed or cancelled operations can be retried.")
        row = self._required(
            """UPDATE public.background_operations SET status='QUEUED',completed_at=NULL,error_code=NULL,
               error_message=NULL,worker_id=NULL,lease_expires_at=NULL,progress_current=0,progress_percent=0,
               current_stage='QUEUED',stage_message='Queued for retry',updated_at=NOW()
               WHERE operation_id=%s AND creator_profile_id=%s RETURNING *""",
            (operation_id, int(creator_profile_id)),
        )
        self.append_event(operation_id, "RETRIED", operation.status, "QUEUED",
                          "QUEUED", "Queued for retry", {})
        return row

    def append_event(self, operation_id, event_type, previous_status=None, new_status=None,
                     stage=None, message=None, metadata=None) -> None:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._insert_event(cursor, operation_id, event_type, previous_status, new_status,
                               stage, message, metadata or {})

    @staticmethod
    def _scope(clauses, params, account_id, workspace, subject_type, subject_id):
        if account_id is not None:
            clauses.append("(account_id IS NULL OR account_id=%s)"); params.append(int(account_id))
        if workspace:
            clauses.append("originating_workspace=%s"); params.append(workspace)
        if subject_type:
            clauses.append("subject_type=%s"); params.append(subject_type)
        if subject_id:
            clauses.append("subject_id=%s"); params.append(subject_id)

    @staticmethod
    def _insert_event(cursor, operation_id, event_type, previous_status, new_status,
                      stage, message, metadata):
        cursor.execute(
            """INSERT INTO public.background_operation_events(operation_id,event_type,previous_status,new_status,stage,message,metadata)
               VALUES(%s,%s,%s,%s,%s,%s,%s::jsonb)""",
            (operation_id, event_type, previous_status, new_status, stage, message,
             json.dumps(dict(metadata or {}))),
        )

    def _one_unscoped(self, operation_id):
        return self._one("SELECT * FROM public.background_operations WHERE operation_id=%s", (operation_id,))

    def _one(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); row = cursor.fetchone()
        return BackgroundOperation.from_row(row) if row else None

    def _all(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); rows = cursor.fetchall()
        return tuple(BackgroundOperation.from_row(row) for row in rows)

    def _required(self, query, params):
        value = self._execute(query, params)
        if value is None: raise KeyError("Background Operation not found.")
        return BackgroundOperation.from_row(value)

    def _execute(self, query, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(query, params); return cursor.fetchone()
