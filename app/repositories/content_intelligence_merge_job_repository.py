"""Durable claims and Business Asset readiness updates for deterministic merge work."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.database import get_db_connection


@dataclass(frozen=True)
class ContentIntelligenceMergeJob:
    asset_id: int
    creator_profile_id: int
    attempt_number: int


class ContentIntelligenceMergeJobRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def claim_next(self, worker_instance_id: str, *, lease_minutes: int = 15) -> ContentIntelligenceMergeJob | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT p.asset_id
                        FROM public.asset_intelligence_profiles p
                        JOIN public.business_asset_registrations b ON b.asset_id=p.asset_id
                        WHERE (p.analysis_status='CONTENT_INTELLIGENCE_PENDING'
                               AND (p.content_merge_lease_expires_at IS NULL
                                    OR p.content_merge_lease_expires_at <= now()))
                           OR (p.analysis_status='CONTENT_INTELLIGENCE_RUNNING'
                               AND p.content_merge_lease_expires_at <= now())
                        ORDER BY p.updated_at,p.asset_id
                        FOR UPDATE OF p SKIP LOCKED
                        LIMIT 1
                    ), claimed AS (
                        UPDATE public.asset_intelligence_profiles p
                        SET content_merge_worker_instance_id=%s,
                            content_merge_claimed_at=now(),
                            content_merge_lease_expires_at=now() + (%s * interval '1 minute'),
                            content_merge_attempt_count=p.content_merge_attempt_count + 1,
                            updated_at=now()
                        FROM candidate WHERE p.asset_id=candidate.asset_id
                        RETURNING p.asset_id,p.creator_profile_id,p.content_merge_attempt_count
                    )
                    SELECT * FROM claimed
                    """,
                    (worker_instance_id, int(lease_minutes)),
                )
                row = cursor.fetchone()
        return ContentIntelligenceMergeJob(
            int(row["asset_id"]), int(row["creator_profile_id"]),
            int(row["content_merge_attempt_count"]),
        ) if row else None

    def release_claim(self, asset_id: int, worker_instance_id: str) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.asset_intelligence_profiles
                       SET content_merge_worker_instance_id=NULL,content_merge_claimed_at=NULL,
                           content_merge_lease_expires_at=NULL,updated_at=now()
                       WHERE asset_id=%s AND content_merge_worker_instance_id=%s RETURNING asset_id""",
                    (int(asset_id), worker_instance_id),
                )
                return cursor.fetchone() is not None

    def mark_business_ready(self, asset_id: int) -> bool:
        """Update existing registration only; never create downstream records."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.business_asset_registrations
                       SET content_intelligence_status='COMPLETE',content_intelligence_ready=true,
                           business_lifecycle_state='INTELLIGENCE_READY',
                           commerce_intelligence_refs=COALESCE(commerce_intelligence_refs,'{}'::jsonb)
                               || '{"content_intelligence_status":"COMPLETE","content_intelligence_ready":true}'::jsonb,
                           missing_requirements=(SELECT COALESCE(jsonb_agg(item.value),'[]'::jsonb)
                               FROM jsonb_array_elements(missing_requirements) AS item(value)
                               WHERE item.value <> '"asset_analysis_complete"'::jsonb),
                           warnings=(SELECT COALESCE(jsonb_agg(item.value),'[]'::jsonb)
                               FROM jsonb_array_elements(warnings) AS item(value)
                               WHERE item.value NOT IN (
                                   '"analysis_pending"'::jsonb,'"analysis_failed"'::jsonb,
                                   '"nudenet_failed"'::jsonb,'"vision_failed"'::jsonb,
                                   '"grok_failed"'::jsonb,'"content_intelligence_failed"'::jsonb
                               )),
                           error_code=NULL,error_message=NULL,last_refreshed_at=now(),updated_at=now()
                       WHERE asset_id=%s RETURNING asset_id""",
                    (int(asset_id),),
                )
                return cursor.fetchone() is not None
