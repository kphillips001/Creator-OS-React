"""Durable, leased work claims for the READY-to-chat registration bridge."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from uuid import UUID

from app.database import get_db_connection


@dataclass(frozen=True)
class ReadyAssetChatRegistrationJob:
    asset_id: int
    attempt_number: int


class ReadyAssetChatRegistrationJobRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def claim_next(self, worker_instance_id: str, *, lease_minutes: int = 15) -> ReadyAssetChatRegistrationJob | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.ready_asset_chat_registration_jobs (asset_id)
                    SELECT p.asset_id
                    FROM public.asset_intelligence_profiles p
                    JOIN public.business_asset_registrations b ON b.asset_id = p.asset_id
                    JOIN public.content_intelligence_profiles c ON c.asset_id = p.asset_id
                    WHERE p.analysis_status = 'READY'
                      AND b.commerce_registration_status = 'REGISTERED'
                      AND b.content_intelligence_status = 'COMPLETE'
                      AND b.content_intelligence_ready = TRUE
                      AND c.status = 'COMPLETE'
                      AND b.business_lifecycle_state <> 'RETIRED'
                    ON CONFLICT (asset_id) DO NOTHING
                    """
                )
                cursor.execute(
                    """
                    WITH candidate AS (
                        SELECT j.asset_id
                        FROM public.ready_asset_chat_registration_jobs j
                        JOIN public.asset_intelligence_profiles p ON p.asset_id = j.asset_id
                        JOIN public.business_asset_registrations b ON b.asset_id = j.asset_id
                        JOIN public.content_intelligence_profiles c ON c.asset_id = j.asset_id
                        WHERE (j.status = 'PENDING'
                           OR (j.status = 'RUNNING' AND j.lease_expires_at <= now())
                           OR (j.status = 'FAILED' AND j.lease_expires_at <= now()))
                          AND p.analysis_status = 'READY'
                          AND b.commerce_registration_status = 'REGISTERED'
                          AND b.content_intelligence_status = 'COMPLETE'
                          AND b.content_intelligence_ready = TRUE
                          AND c.status = 'COMPLETE'
                          AND b.business_lifecycle_state <> 'RETIRED'
                        ORDER BY j.updated_at, j.asset_id
                        FOR UPDATE OF j SKIP LOCKED
                        LIMIT 1
                    )
                    UPDATE public.ready_asset_chat_registration_jobs j
                    SET status = 'RUNNING', worker_instance_id = %s, claimed_at = now(),
                        lease_expires_at = now() + (%s * interval '1 minute'),
                        attempt_count = attempt_count + 1, updated_at = now()
                    FROM candidate
                    WHERE j.asset_id = candidate.asset_id
                    RETURNING j.asset_id, j.attempt_count
                    """,
                    (worker_instance_id, int(lease_minutes)),
                )
                row = cursor.fetchone()
        return ReadyAssetChatRegistrationJob(int(row["asset_id"]), int(row["attempt_count"])) if row else None

    def complete(self, asset_id: int, worker_instance_id: str, result) -> bool:
        record = getattr(result, "record", None)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.ready_asset_chat_registration_jobs
                    SET status = 'COMPLETE', worker_instance_id = NULL, claimed_at = NULL,
                        lease_expires_at = NULL, chat_registration_id = %s,
                        availability_state = %s, missing_requirements = %s::jsonb,
                        error_code = NULL, error_message = NULL, completed_at = now(), updated_at = now()
                    WHERE asset_id = %s AND worker_instance_id = %s
                    RETURNING asset_id
                    """,
                    (
                        getattr(record, "chat_registration_id", None),
                        getattr(getattr(result, "availability_state", None), "value", None),
                        json.dumps(list(getattr(result, "block_reasons", ()) or ())),
                        int(asset_id), worker_instance_id,
                    ),
                )
                return cursor.fetchone() is not None

    def fail(self, asset_id: int, worker_instance_id: str, error: Exception) -> bool:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.ready_asset_chat_registration_jobs
                    SET status = 'FAILED', worker_instance_id = NULL, claimed_at = NULL,
                        lease_expires_at = now() + interval '5 minutes', error_code = %s, error_message = %s, updated_at = now()
                    WHERE asset_id = %s AND worker_instance_id = %s
                    RETURNING asset_id
                    """,
                    (type(error).__name__, str(error), int(asset_id), worker_instance_id),
                )
                return cursor.fetchone() is not None
