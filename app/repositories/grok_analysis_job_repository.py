"""Durable, leased work claims for the existing Grok Vision provider stage."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from app.database import get_db_connection


@dataclass(frozen=True)
class GrokAnalysisJob:
    asset_id: int
    creator_profile_id: int
    file_path: str
    file_name: str
    media_type: str
    attempt_number: int


class GrokAnalysisJobRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def claim_next(self, worker_instance_id: str, *, lease_minutes: int = 15) -> GrokAnalysisJob | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT p.asset_id
                        FROM public.asset_intelligence_profiles p
                        JOIN public.business_asset_registrations b ON b.asset_id=p.asset_id
                        JOIN public.content_items c ON c.id=p.asset_id
                        WHERE (p.analysis_status='GROK_PENDING'
                               AND (p.grok_lease_expires_at IS NULL OR p.grok_lease_expires_at <= now()))
                           OR (p.analysis_status='GROK_RUNNING' AND p.grok_lease_expires_at <= now())
                        ORDER BY p.updated_at,p.asset_id
                        FOR UPDATE OF p SKIP LOCKED
                        LIMIT 1
                    ), claimed AS (
                        UPDATE public.asset_intelligence_profiles p
                        SET grok_worker_instance_id=%s,grok_claimed_at=now(),
                            grok_lease_expires_at=now() + (%s * interval '1 minute'),
                            grok_attempt_count=p.grok_attempt_count + 1,updated_at=now()
                        FROM candidate WHERE p.asset_id=candidate.asset_id
                        RETURNING p.asset_id,p.creator_profile_id,p.grok_attempt_count
                    )
                    SELECT claimed.*,c.file_path,COALESCE(c.file_name,c.file_path) AS file_name
                    FROM claimed JOIN public.content_items c ON c.id=claimed.asset_id
                    """,
                    (worker_instance_id, int(lease_minutes)),
                )
                row = cursor.fetchone()
        return self._job(row) if row else None

    def release_claim(self, asset_id: int, worker_instance_id: str) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.asset_intelligence_profiles
                       SET grok_worker_instance_id=NULL,grok_claimed_at=NULL,
                           grok_lease_expires_at=NULL,updated_at=now()
                       WHERE asset_id=%s AND grok_worker_instance_id=%s RETURNING asset_id""",
                    (int(asset_id), worker_instance_id),
                )
                return cursor.fetchone() is not None

    @staticmethod
    def _job(row: Mapping) -> GrokAnalysisJob:
        path = str(row["file_path"])
        suffix = path.rsplit(".", 1)[-1].lower() if "." in path else ""
        media_type = "image" if suffix in {"gif", "jpeg", "jpg", "png", "webp"} else "unknown"
        return GrokAnalysisJob(
            int(row["asset_id"]), int(row["creator_profile_id"]), path,
            str(row["file_name"]), media_type, int(row["grok_attempt_count"]),
        )
