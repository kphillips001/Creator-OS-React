"""PostgreSQL persistence for Developer Agent tasks, executions and events."""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.services.developer_agent_persistence_sanitizer import (
    sanitize_developer_agent_value,
)


class DeveloperAgentExecutionRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def persistence_ready(self) -> bool:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT to_regclass('public.developer_agent_tasks') IS NOT NULL
                          AND to_regclass('public.developer_agent_executions') IS NOT NULL
                          AND to_regclass('public.developer_agent_events') IS NOT NULL
                          AND to_regclass('public.developer_agent_notifications') IS NOT NULL
                          AND to_regclass('public.developer_agent_reviews') IS NOT NULL
                          AS ready"""
            )
            return bool(cursor.fetchone()["ready"])

    def create_task(
        self, *, issue_identifier: str, investigation_package: str,
        implementation_task: str, repository_path: str, expected_branch: str,
    ) -> dict[str, Any]:
        task_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.developer_agent_tasks(
                    task_id,issue_identifier,investigation_package,
                    implementation_task,repository_path,expected_branch,status
                ) VALUES(%s,%s,%s,%s,%s,%s,'AWAITING_APPROVAL')
                RETURNING *""",
                sanitize_developer_agent_value((
                    task_id, issue_identifier, investigation_package,
                    implementation_task, repository_path, expected_branch,
                )),
            )
            row = cursor.fetchone()
        self.create_notification(
            task_id=task_id, execution_id=None,
            notification_type="TASK_AWAITING_APPROVAL",
            title="Developer Agent task awaiting approval.",
            detail=f"Review the implementation task for {issue_identifier}.",
        )
        return dict(row)

    def get_task(self, task_id: UUID) -> dict[str, Any] | None:
        return self._one(
            "SELECT * FROM public.developer_agent_tasks WHERE task_id=%s",
            (task_id,),
        )

    def approve_task(self, task_id: UUID) -> dict[str, Any]:
        return self._required(
            """UPDATE public.developer_agent_tasks
               SET status='APPROVED',approved_at=NOW(),updated_at=NOW()
               WHERE task_id=%s AND status='AWAITING_APPROVAL' RETURNING *""",
            (task_id,),
        )

    def reject_task(self, task_id: UUID) -> dict[str, Any]:
        return self._required(
            """UPDATE public.developer_agent_tasks
               SET status='REJECTED',updated_at=NOW()
               WHERE task_id=%s AND status='AWAITING_APPROVAL' RETURNING *""",
            (task_id,),
        )

    def create_execution(
        self, *, task_id: UUID, initial_git_status: str,
        initial_branch: str, initial_head: str,
    ) -> dict[str, Any]:
        execution_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.developer_agent_executions(
                    execution_id,task_id,status,initial_git_status,
                    initial_branch,initial_head
                ) VALUES(%s,%s,'QUEUED',%s,%s,%s) RETURNING *""",
                sanitize_developer_agent_value((
                    execution_id, task_id, initial_git_status,
                    initial_branch, initial_head,
                )),
            )
            row = cursor.fetchone()
            cursor.execute(
                """INSERT INTO public.developer_agent_reviews(
                    review_id,execution_id,status
                ) VALUES(%s,%s,'PENDING')""",
                (uuid4(), execution_id),
            )
        return dict(row)

    def get_execution(self, execution_id: UUID) -> dict[str, Any] | None:
        return self._one(
            """SELECT execution.*,task.issue_identifier,task.implementation_task,
                      task.repository_path,task.expected_branch,
                      review.status AS review_status
               FROM public.developer_agent_executions execution
               JOIN public.developer_agent_tasks task USING(task_id)
               LEFT JOIN public.developer_agent_reviews review
                 ON review.execution_id=execution.execution_id
               WHERE execution.execution_id=%s""",
            (execution_id,),
        )

    def list_executions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self._all(
            """SELECT execution.*,task.issue_identifier,task.implementation_task,
                      task.repository_path,task.expected_branch,
                      review.status AS review_status
               FROM public.developer_agent_executions execution
               JOIN public.developer_agent_tasks task USING(task_id)
               LEFT JOIN public.developer_agent_reviews review
                 ON review.execution_id=execution.execution_id
               ORDER BY execution.created_at DESC LIMIT %s""",
            (max(1, min(limit, 100)),),
        )

    def list_events(self, execution_id: UUID) -> list[dict[str, Any]]:
        return self._all(
            """SELECT event_id,event_type,message,event_data,created_at
               FROM public.developer_agent_events
               WHERE execution_id=%s ORDER BY event_id""",
            (execution_id,),
        )

    def add_event(
        self, execution_id: UUID, event_type: str, message: str,
        event_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self._required(
            """INSERT INTO public.developer_agent_events(
                   execution_id,event_type,message,event_data
               ) VALUES(%s,%s,%s,%s::JSONB) RETURNING *""",
            (
                execution_id,
                sanitize_developer_agent_value(event_type),
                sanitize_developer_agent_value(message),
                json.dumps(sanitize_developer_agent_value(event_data or {})),
            ),
        )

    def update_execution(
        self, execution_id: UUID, *, status: str,
        codex_session_id: str | None = None,
        failure_reason: str | None = None,
        cancellation_reason: str | None = None,
        final_report: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        terminal = status in {"COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"}
        return self._required(
            """UPDATE public.developer_agent_executions SET
                   status=%s,
                   codex_session_id=COALESCE(%s,codex_session_id),
                   failure_reason=COALESCE(%s,failure_reason),
                   cancellation_reason=COALESCE(%s,cancellation_reason),
                   final_report=COALESCE(%s::JSONB,final_report),
                   started_at=CASE WHEN %s IN ('STARTING','RUNNING')
                                   THEN COALESCE(started_at,NOW()) ELSE started_at END,
                   completed_at=CASE WHEN %s THEN NOW() ELSE completed_at END,
                   updated_at=NOW()
               WHERE execution_id=%s RETURNING *""",
            (sanitize_developer_agent_value(status),
             sanitize_developer_agent_value(codex_session_id),
             sanitize_developer_agent_value(failure_reason),
             sanitize_developer_agent_value(cancellation_reason),
             json.dumps(sanitize_developer_agent_value(final_report)) if final_report is not None else None,
             status, terminal, execution_id),
        )

    def create_notification(
        self, *, task_id: UUID | None, execution_id: UUID | None,
        notification_type: str, title: str, detail: str,
    ) -> dict[str, Any]:
        return self._required(
            """INSERT INTO public.developer_agent_notifications(
                   notification_id,task_id,execution_id,notification_type,
                   title,detail
               ) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *""",
            (uuid4(), task_id, execution_id,
             sanitize_developer_agent_value(notification_type),
             sanitize_developer_agent_value(title),
             sanitize_developer_agent_value(detail)),
        )

    def list_notifications(self) -> list[dict[str, Any]]:
        return self._all(
            """SELECT * FROM public.developer_agent_notifications
               ORDER BY created_at DESC LIMIT 100""",
            (),
        )

    def mark_notification_read(self, notification_id: UUID) -> dict[str, Any]:
        return self._required(
            """UPDATE public.developer_agent_notifications SET is_read=TRUE
               WHERE notification_id=%s RETURNING *""",
            (notification_id,),
        )

    def update_review(self, execution_id: UUID, status: str) -> dict[str, Any]:
        return self._required(
            """UPDATE public.developer_agent_reviews SET
                   status=%s,reviewed_at=NOW(),updated_at=NOW()
               WHERE execution_id=%s RETURNING *""",
            (status, execution_id),
        )

    def interrupt_running(self) -> int:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.developer_agent_executions SET
                       status='INTERRUPTED',
                       failure_reason='Backend restarted; Codex completion could not be verified.',
                       completed_at=NOW(),updated_at=NOW()
                   WHERE status IN ('QUEUED','STARTING','RUNNING','TESTING',
                                    'WAITING_FOR_INPUT')""",
            )
            return cursor.rowcount

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
            raise ValueError("Developer Agent record was not found or transition is invalid.")
        return row
