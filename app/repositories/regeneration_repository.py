"""PostgreSQL persistence for regeneration runs and review-pending results."""
from __future__ import annotations

from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.regeneration import RegenerationResult, RegenerationRun


class RegenerationRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def ensure_run(self, *, operation_id, creator_profile_id, source_generated_image_id,
                   source_recipe_id, requested_count) -> RegenerationRun:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """INSERT INTO public.regeneration_runs(operation_id,creator_profile_id,
                   source_generated_image_id,source_recipe_id,requested_count)
                   VALUES(%s,%s,%s,%s,%s) ON CONFLICT(operation_id) DO NOTHING""",
                (operation_id, int(creator_profile_id), source_generated_image_id,
                 source_recipe_id, int(requested_count)),
            )
            for index in range(1, int(requested_count) + 1):
                cursor.execute(
                    """INSERT INTO public.regeneration_results(regeneration_result_id,
                       operation_id,variation_index) VALUES(%s,%s,%s)
                       ON CONFLICT(operation_id,variation_index) DO NOTHING""",
                    (uuid4(), operation_id, index),
                )
        return self.get_run(operation_id)

    def get_run(self, operation_id, *, creator_profile_id: int | None = None) -> RegenerationRun | None:
        clause = " AND creator_profile_id=%s" if creator_profile_id is not None else ""
        params = (operation_id, int(creator_profile_id)) if creator_profile_id is not None else (operation_id,)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"SELECT * FROM public.regeneration_runs WHERE operation_id=%s{clause}", params)
            row = cursor.fetchone()
        return RegenerationRun(**dict(row)) if row else None

    def discover_workspace(self, *, creator_profile_id: int) -> RegenerationRun | None:
        """Newest active run wins, then newest terminal run still needing review."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT r.* FROM public.regeneration_runs r
                JOIN public.background_operations o ON o.operation_id=r.operation_id
                WHERE r.creator_profile_id=%s AND r.workspace_dismissed_at IS NULL
                  AND (o.status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED') OR (
                    r.created_at > COALESCE((
                      SELECT MAX(dismissed.workspace_dismissed_at)
                      FROM public.regeneration_runs dismissed
                      WHERE dismissed.creator_profile_id=r.creator_profile_id
                    ), '-infinity'::timestamptz)
                    AND EXISTS (
                      SELECT 1 FROM public.regeneration_results x
                      WHERE x.operation_id=r.operation_id
                        AND (x.status IN ('PENDING','RUNNING','FAILED','SUBMISSION_AMBIGUOUS')
                             OR (x.status='SUCCEEDED' AND x.disposition='PENDING_REVIEW')))))
                ORDER BY CASE WHEN o.status IN ('QUEUED','RUNNING','WAITING_EXTERNAL','CANCEL_REQUESTED') THEN 0 ELSE 1 END,
                         r.updated_at DESC LIMIT 1""", (int(creator_profile_id),))
            row = cursor.fetchone()
        return RegenerationRun(**dict(row)) if row else None

    def dismiss_workspace(self, operation_id, *, creator_profile_id: int) -> RegenerationRun:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.regeneration_runs SET workspace_dismissed_at=NOW(),updated_at=NOW()
                WHERE operation_id=%s AND creator_profile_id=%s RETURNING *""",
                (operation_id, int(creator_profile_id)))
            row = cursor.fetchone()
        if not row:
            raise KeyError("Regeneration operation not found.")
        return RegenerationRun(**dict(row))

    def results(self, operation_id) -> tuple[RegenerationResult, ...]:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                "SELECT * FROM public.regeneration_results WHERE operation_id=%s ORDER BY variation_index",
                (operation_id,),
            )
            rows = cursor.fetchall()
        return tuple(RegenerationResult(**dict(row)) for row in rows)

    def promote_result(self, operation_id, result_id) -> RegenerationResult:
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.regeneration_results SET disposition='PROMOTED',updated_at=NOW()
                   WHERE operation_id=%s AND regeneration_result_id=%s
                     AND disposition IN ('PENDING_REVIEW','ARCHIVED','PROMOTED') RETURNING *""",
                (operation_id, result_id),
            )
            row = cursor.fetchone()
        if not row:
            raise KeyError("Regeneration result not found or cannot be promoted.")
        return RegenerationResult(**dict(row))

    def archive_result(self, operation_id, result_id) -> RegenerationResult:
        return self._transition_disposition(operation_id, result_id, "ARCHIVED", ("PENDING_REVIEW", "ARCHIVED"))

    def restore_result(self, operation_id, result_id) -> RegenerationResult:
        return self._transition_disposition(operation_id, result_id, "PENDING_REVIEW", ("ARCHIVED", "PENDING_REVIEW"))

    def _transition_disposition(self, operation_id, result_id, target, allowed):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.regeneration_results SET disposition=%s,updated_at=NOW()
                   WHERE operation_id=%s AND regeneration_result_id=%s
                     AND disposition=ANY(%s) RETURNING *""",
                (target, operation_id, result_id, list(allowed)),
            )
            row = cursor.fetchone()
        if not row:
            raise KeyError("Regeneration result disposition transition is not allowed.")
        return RegenerationResult(**dict(row))

    def archived(self, *, creator_profile_id: int, search: str | None = None,
                 page: int = 1, page_size: int = 20):
        pattern = f"%{str(search or '').strip()}%"
        where = "r.creator_profile_id=%s AND x.disposition='ARCHIVED'"
        params = [int(creator_profile_id)]
        if str(search or "").strip():
            where += " AND (x.generated_image_id ILIKE %s OR r.source_generated_image_id ILIKE %s OR gr.provider_id ILIKE %s)"
            params.extend([pattern, pattern, pattern])
        offset = (max(1, int(page)) - 1) * int(page_size)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(f"""SELECT COUNT(*) AS total FROM public.regeneration_results x
                JOIN public.regeneration_runs r ON r.operation_id=x.operation_id
                LEFT JOIN public.generation_recipes gr ON gr.recipe_id=x.generation_recipe_id WHERE {where}""", tuple(params))
            total = int(cursor.fetchone()["total"])
            cursor.execute(f"""SELECT x.*,r.source_generated_image_id,gr.provider_id,gr.provider_model,
                gr.source_workflow FROM public.regeneration_results x
                JOIN public.regeneration_runs r ON r.operation_id=x.operation_id
                LEFT JOIN public.generation_recipes gr ON gr.recipe_id=x.generation_recipe_id
                WHERE {where} ORDER BY x.updated_at DESC LIMIT %s OFFSET %s""", (*params, int(page_size), offset))
            rows = [dict(row) for row in cursor.fetchall()]
        return rows, total

    def update_run_status(self, operation_id, status: str) -> RegenerationRun:
        terminal = status in {"SUCCEEDED", "PARTIAL", "FAILED", "CANCELLED"}
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.regeneration_runs SET status=%s,
                   started_at=CASE WHEN %s='RUNNING' THEN COALESCE(started_at,NOW()) ELSE started_at END,
                   completed_at=CASE WHEN %s THEN NOW() ELSE completed_at END,updated_at=NOW()
                   WHERE operation_id=%s RETURNING *""",
                (status, status, terminal, operation_id),
            )
            row = cursor.fetchone()
        if not row:
            raise KeyError("Regeneration run not found.")
        return RegenerationRun(**dict(row))

    def start_result(self, operation_id, variation_index: int) -> RegenerationResult:
        return self._update_result(
            operation_id, variation_index,
            "status='RUNNING',started_at=COALESCE(started_at,NOW()),error_code=NULL,error_message=NULL",
            (),
        )

    def set_result_job(self, operation_id, variation_index: int, generation_job_id: str) -> RegenerationResult:
        return self._update_result(
            operation_id, variation_index, "generation_job_id=%s", (generation_job_id,),
        )

    def succeed_result(self, operation_id, variation_index: int, *, generation_job_id: str,
                       generation_result_id: str, generated_image_id: str,
                       generation_recipe_id, media_path: str) -> RegenerationResult:
        return self._update_result(
            operation_id, variation_index,
            """status='SUCCEEDED',generation_job_id=%s,generation_result_id=%s,
               generated_image_id=%s,generation_recipe_id=%s,media_path=%s,
               error_code=NULL,error_message=NULL,completed_at=NOW()""",
            (generation_job_id, generation_result_id, generated_image_id,
             generation_recipe_id, media_path),
        )

    def fail_result(self, operation_id, variation_index: int, error, *, code="GENERATION_FAILED",
                    recipe_id=None, ambiguous=False) -> RegenerationResult:
        status = "SUBMISSION_AMBIGUOUS" if ambiguous else "FAILED"
        return self._update_result(
            operation_id, variation_index,
            "status=%s,generation_recipe_id=COALESCE(%s,generation_recipe_id),error_code=%s,error_message=%s,completed_at=NOW()",
            (status, recipe_id, code, str(error)),
        )

    def _update_result(self, operation_id, variation_index, assignments, params):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""UPDATE public.regeneration_results SET {assignments},updated_at=NOW()
                    WHERE operation_id=%s AND variation_index=%s RETURNING *""",
                (*params, operation_id, int(variation_index)),
            )
            row = cursor.fetchone()
        if not row:
            raise KeyError("Regeneration result not found.")
        return RegenerationResult(**dict(row))
