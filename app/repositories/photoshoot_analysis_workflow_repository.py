"""Durable leased queue for Photoshoot analysis orchestration."""

from __future__ import annotations

from dataclasses import dataclass
from app.database import get_db_connection


@dataclass(frozen=True)
class PhotoshootAnalysisJob:
    deliverable_id: str
    current_stage: str
    attempt_count: int


class PhotoshootAnalysisWorkflowRepository:
    FAILURES = {"MEMBER_ANALYSIS_FAILED", "PHOTOSHOOT_INTELLIGENCE_FAILED", "NAMING_FAILED"}

    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def enqueue(self, deliverable_id: str):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO public.photoshoot_analysis_workflows (deliverable_id,current_stage)
                    VALUES (%s,'PENDING') ON CONFLICT (deliverable_id) DO NOTHING RETURNING *""", (deliverable_id,))
                row = cur.fetchone()
                if row is None:
                    cur.execute("SELECT * FROM public.photoshoot_analysis_workflows WHERE deliverable_id=%s", (deliverable_id,))
                    row = cur.fetchone()
                return dict(row)

    def get(self, deliverable_id: str):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM public.photoshoot_analysis_workflows WHERE deliverable_id=%s", (deliverable_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def claim_next(self, worker_id: str, lease_minutes: int = 15):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""WITH candidate AS (
                    SELECT deliverable_id,current_stage FROM public.photoshoot_analysis_workflows
                    WHERE current_stage IN ('PENDING','MEMBER_ANALYSIS_PENDING','PHOTOSHOOT_INTELLIGENCE_PENDING','NAMING_PENDING')
                       OR (current_stage IN ('MEMBER_ANALYSIS_RUNNING','PHOTOSHOOT_INTELLIGENCE_RUNNING','NAMING_RUNNING')
                           AND lease_expires_at<=now())
                    ORDER BY updated_at,deliverable_id FOR UPDATE SKIP LOCKED LIMIT 1
                ) UPDATE public.photoshoot_analysis_workflows w SET
                    current_stage=CASE
                      WHEN candidate.current_stage IN ('PENDING','MEMBER_ANALYSIS_PENDING','MEMBER_ANALYSIS_RUNNING') THEN 'MEMBER_ANALYSIS_RUNNING'
                      WHEN candidate.current_stage IN ('PHOTOSHOOT_INTELLIGENCE_PENDING','PHOTOSHOOT_INTELLIGENCE_RUNNING') THEN 'PHOTOSHOOT_INTELLIGENCE_RUNNING'
                      ELSE 'NAMING_RUNNING' END,
                    worker_id=%s,claimed_at=now(),lease_expires_at=now()+(%s*interval '1 minute'),
                    attempt_count=w.attempt_count+1,started_at=COALESCE(w.started_at,now()),updated_at=now()
                    FROM candidate WHERE w.deliverable_id=candidate.deliverable_id
                    RETURNING w.deliverable_id,w.current_stage,w.attempt_count""", (worker_id, int(lease_minutes)))
                row = cur.fetchone()
                return PhotoshootAnalysisJob(str(row["deliverable_id"]), str(row["current_stage"]), int(row["attempt_count"])) if row else None

    def transition(self, deliverable_id: str, worker_id: str, stage: str, *, error=None, member_id=None):
        terminal = stage == "READY"
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE public.photoshoot_analysis_workflows SET current_stage=%s,
                    worker_id=NULL,claimed_at=NULL,lease_expires_at=NULL,
                    last_error_code=%s,last_error_message=%s,failed_member_asset_id=%s,
                    completed_at=CASE WHEN %s THEN now() ELSE NULL END,updated_at=now()
                    WHERE deliverable_id=%s AND worker_id=%s RETURNING *""",
                    (stage, type(error).__name__ if error else None, str(error) if error else None,
                     member_id, terminal, deliverable_id, worker_id))
                row = cur.fetchone()
                return dict(row) if row else None

    def retry(self, deliverable_id: str):
        with self.connection_factory() as conn:
            with conn.cursor() as cur:
                cur.execute("""UPDATE public.photoshoot_analysis_workflows SET
                    current_stage=CASE
                      WHEN current_stage='MEMBER_ANALYSIS_FAILED' THEN 'MEMBER_ANALYSIS_PENDING'
                      WHEN current_stage='PHOTOSHOOT_INTELLIGENCE_FAILED' THEN 'PHOTOSHOOT_INTELLIGENCE_PENDING'
                      WHEN current_stage='NAMING_FAILED' THEN 'NAMING_PENDING' ELSE current_stage END,
                    last_error_code=NULL,last_error_message=NULL,failed_member_asset_id=NULL,updated_at=now()
                    WHERE deliverable_id=%s RETURNING *""", (deliverable_id,))
                row = cur.fetchone(); return dict(row) if row else None
