"""Atomic PostgreSQL persistence for Photoshoot auto-run workflows."""

from __future__ import annotations

from psycopg.types.json import Jsonb

from app.database import get_db_connection
from app.models.photoshoot_auto_run import PhotoshootAutoRun


class PhotoshootAutoRunRepository:
    CLAIMABLE = ("READY", "PREPARING", "GENERATING", "WAITING_FOR_REVIEW", "APPROVING", "ADVANCING")

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    @staticmethod
    def _model(row):
        return PhotoshootAutoRun(**dict(row)) if row else None

    def get(self, session_id: str):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM public.photoshoot_auto_runs WHERE session_id=%s", (session_id,))
            return self._model(cur.fetchone())

    def start(self, session_id: str, *, current_plan_index: int, total_frames: int,
              current_request_id: str | None, auto_approve_enabled: bool = True):
        mode = "AUTO_APPROVE" if auto_approve_enabled else "MANUAL_REVIEW"
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""INSERT INTO public.photoshoot_auto_runs (
                    session_id,state,current_plan_index,total_frames,current_request_id,
                    started_at,stop_requested,auto_approve_enabled,review_mode)
                VALUES (%s,'READY',%s,%s,%s,now(),false,%s,%s)
                ON CONFLICT (session_id) DO UPDATE SET
                    state=CASE WHEN photoshoot_auto_runs.state IN ('PLAN_COMPLETE','PHOTOSHOOT_COMPLETE')
                               THEN photoshoot_auto_runs.state ELSE 'READY' END,
                    current_plan_index=GREATEST(photoshoot_auto_runs.current_plan_index,EXCLUDED.current_plan_index),
                    total_frames=EXCLUDED.total_frames,
                    current_request_id=COALESCE(EXCLUDED.current_request_id,photoshoot_auto_runs.current_request_id),
                    stop_requested=false,auto_approve_enabled=EXCLUDED.auto_approve_enabled,
                    review_mode=EXCLUDED.review_mode,resumed_at=now(),updated_at=now()
                RETURNING *""", (session_id, current_plan_index, total_frames, current_request_id,
                                  auto_approve_enabled, mode))
            return self._model(cur.fetchone())

    def claim_next(self, worker_id: str, *, lease_minutes: int = 15):
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute("""WITH candidate AS (
                    SELECT session_id FROM public.photoshoot_auto_runs
                    WHERE stop_requested=false AND state=ANY(%s)
                      AND (state<>'WAITING_FOR_REVIEW' OR auto_approve_enabled=true)
                      AND (worker_id IS NULL OR lease_expires_at IS NULL OR lease_expires_at<=now())
                    ORDER BY updated_at,session_id FOR UPDATE SKIP LOCKED LIMIT 1
                ) UPDATE public.photoshoot_auto_runs r SET worker_id=%s,claimed_at=now(),
                    lease_expires_at=now()+(%s*interval '1 minute'),attempt_count=r.attempt_count+1,updated_at=now()
                FROM candidate WHERE r.session_id=candidate.session_id RETURNING r.*""",
                (list(self.CLAIMABLE), worker_id, int(lease_minutes)))
            return self._model(cur.fetchone())

    def transition(self, session_id: str, state: str, *, worker_id: str | None = None,
                   release_lease: bool = True, expected_states=None, **fields):
        allowed = {
            "current_plan_index", "total_frames", "current_request_id", "last_error_code",
            "last_error_message", "failure_stage", "failed_frame_index", "failed_frame_title",
            "failed_provider", "failed_request_id", "failed_generation_job_id", "stop_requested",
            "auto_approve_enabled", "review_mode", "metadata",
        }
        values = {key: value for key, value in fields.items() if key in allowed}
        assignments = ["state=%s", "updated_at=now()"]
        params = [state]
        for key, value in values.items():
            assignments.append(f"{key}=%s")
            params.append(Jsonb(dict(value)) if key == "metadata" else value)
        if state == "PAUSED": assignments.append("paused_at=now()")
        if state in {"READY", "PREPARING"}: assignments.append("resumed_at=now()")
        if state in {"PLAN_COMPLETE", "PHOTOSHOOT_COMPLETE"}: assignments.append("completed_at=now()")
        if release_lease:
            assignments.extend(("worker_id=NULL", "claimed_at=NULL", "lease_expires_at=NULL"))
        params.append(session_id)
        where = "session_id=%s"
        if worker_id is not None:
            where += " AND worker_id=%s"
            params.append(worker_id)
        if expected_states is not None:
            where += " AND state=ANY(%s)"
            params.append(list(expected_states))
        with self.connection_factory() as conn, conn.cursor() as cur:
            cur.execute(f"UPDATE public.photoshoot_auto_runs SET {','.join(assignments)} WHERE {where} RETURNING *", params)
            row = cur.fetchone()
        return self._model(row) if row else self.get(session_id)

    def command(self, session_id: str, command: str):
        mapping = {"pause": "PAUSED", "resume": "READY", "stop": "PAUSED", "retry": "READY"}
        if command not in mapping:
            raise ValueError("Unknown Photoshoot auto-run command.")
        expected = {
            "pause": self.CLAIMABLE,
            "stop": self.CLAIMABLE + ("PAUSED", "FAILED"),
            "resume": ("PAUSED",),
            "retry": ("FAILED",),
        }[command]
        fields = {"stop_requested": command == "stop"}
        if command in {"resume", "retry"}:
            fields.update({"stop_requested": False, "last_error_code": None, "last_error_message": None,
                           "failure_stage": None, "failed_frame_index": None, "failed_frame_title": None,
                           "failed_provider": None, "failed_request_id": None, "failed_generation_job_id": None})
        return self.transition(session_id, mapping[command], expected_states=expected, **fields)
