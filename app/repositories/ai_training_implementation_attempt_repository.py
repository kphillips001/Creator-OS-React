"""Queue-owned linkage to canonical Developer Agent implementation attempts."""
from uuid import UUID, uuid4

from psycopg.types.json import Json

from app.database import get_db_connection


class AiTrainingImplementationAttemptRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def prepare(self, work_item_id, *, creator_profile_id, fanvue_account_id,
                brief_version, analysis, task_factory):
        """Serialize preparation so one explicit action creates one next attempt."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_training_work_items
                   WHERE work_item_id=%s AND creator_profile_id=%s AND fanvue_account_id=%s
                   FOR UPDATE""",
                (work_item_id, creator_profile_id, fanvue_account_id),
            )
            row = cursor.fetchone()
            if not row or row["status"] not in {"REQUIRES_IMPLEMENTATION", "IMPLEMENTATION_FAILED"}:
                raise ValueError("Only implementation-required or failed Queue items can be prepared.")
            cursor.execute(
                """SELECT COALESCE(MAX(attempt_number),0)+1 AS next_number
                   FROM public.ai_training_implementation_attempts WHERE work_item_id=%s""",
                (work_item_id,),
            )
            attempt_number = int(cursor.fetchone()["next_number"])
            task = task_factory(attempt_number)
            attempt_id = uuid4()
            cursor.execute(
                """INSERT INTO public.ai_training_implementation_attempts(
                       attempt_id,work_item_id,attempt_number,implementation_brief_version,
                       developer_agent_task_id,status)
                   VALUES(%s,%s,%s,%s,%s,'READY_FOR_IMPLEMENTATION') RETURNING *""",
                (attempt_id, work_item_id, attempt_number, brief_version, task["task_id"]),
            )
            attempt = cursor.fetchone()
            current_analysis = dict(analysis)
            current_analysis.update({
                "implementationAttemptId": str(attempt_id),
                "implementationAttemptNumber": attempt_number,
                "implementationTaskId": str(task["task_id"]),
            })
            current_analysis.pop("implementationExecutionId", None)
            cursor.execute(
                """UPDATE public.ai_training_work_items
                   SET status='READY_FOR_IMPLEMENTATION',analysis=%s,
                       linked_future_task_id=%s,updated_at=NOW(),completed_at=NULL
                   WHERE work_item_id=%s RETURNING *""",
                (Json(current_analysis), task["task_id"], work_item_id),
            )
            return dict(cursor.fetchone()), dict(attempt), dict(task)

    def list(self, work_item_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM public.ai_training_implementation_attempts
                   WHERE work_item_id=%s ORDER BY attempt_number DESC""",
                (work_item_id,),
            )
            return [dict(row) for row in cursor.fetchall()]

    def get(self, attempt_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM public.ai_training_implementation_attempts WHERE attempt_id=%s",
                (attempt_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None

    def attach_execution(self, attempt_id, *, task_id, execution):
        if str(execution.get("task_id")) != str(task_id):
            raise ValueError("The execution does not belong to the current implementation attempt task.")
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_implementation_attempts
                   SET developer_agent_execution_id=%s,status='IMPLEMENTING',approved_at=COALESCE(approved_at,NOW()),
                       started_at=COALESCE(%s,NOW()),updated_at=NOW()
                   WHERE attempt_id=%s AND developer_agent_task_id=%s
                     AND (developer_agent_execution_id IS NULL OR developer_agent_execution_id=%s)
                   RETURNING *""",
                (execution["execution_id"], execution.get("started_at"), attempt_id,
                 task_id, execution["execution_id"]),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("The implementation attempt execution linkage is stale.")
            return dict(row)

    def update_from_execution(self, attempt_id, execution):
        status = {"COMPLETED": "NEEDS_VERIFICATION", "FAILED": "FAILED",
                  "CANCELLED": "FAILED", "INTERRUPTED": "FAILED"}.get(execution["status"])
        if not status:
            return self.get(attempt_id)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_implementation_attempts
                   SET status=%s,completed_at=COALESCE(%s,NOW()),updated_at=NOW()
                   WHERE attempt_id=%s AND developer_agent_execution_id=%s
                     AND developer_agent_task_id=%s RETURNING *""",
                (status, execution.get("completed_at"), attempt_id,
                 execution["execution_id"], execution["task_id"]),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("The execution does not belong to the implementation attempt.")
            return dict(row)

    def verify(self, attempt_id, execution_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_implementation_attempts
                   SET status='VERIFIED',verified_at=NOW(),updated_at=NOW()
                   WHERE attempt_id=%s AND developer_agent_execution_id=%s
                     AND status='NEEDS_VERIFICATION' RETURNING *""",
                (attempt_id, execution_id),
            )
            row = cursor.fetchone()
            if not row:
                raise ValueError("Only the current successful attempt can be verified.")
            return dict(row)

    def supersede_prepared(self, attempt_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.ai_training_implementation_attempts
                   SET status='SUPERSEDED',updated_at=NOW()
                   WHERE attempt_id=%s AND status='READY_FOR_IMPLEMENTATION' RETURNING *""",
                (attempt_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
