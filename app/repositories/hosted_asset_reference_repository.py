"""PostgreSQL persistence for canonical hosted-reference history."""

from __future__ import annotations

from uuid import uuid4

from app.database import get_db_connection
from app.models.hosted_asset_reference import HostedAssetReference


class HostedAssetReferenceRepository:
    def __init__(self, connection_factory=get_db_connection):
        self._connection_factory = connection_factory

    @staticmethod
    def _record(row) -> HostedAssetReference | None:
        return HostedAssetReference(**dict(row)) if row else None

    def find_current(self, *, asset_id: int, host_name: str, source_checksum: str):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.hosted_asset_references
                       WHERE asset_id=%s AND host_name=%s AND source_checksum=%s
                         AND is_current=TRUE AND status='READY'
                       ORDER BY verified_at DESC NULLS LAST, created_at DESC LIMIT 1""",
                    (int(asset_id), host_name, source_checksum),
                )
                return self._record(cursor.fetchone())

    def save_ready(self, *, asset_id: int, host_name: str, hosted_url: str,
                   source_checksum: str, source_path: str):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_xact_lock(%s)", (int(asset_id),))
                cursor.execute(
                    """UPDATE public.hosted_asset_references SET is_current=FALSE, updated_at=now()
                       WHERE asset_id=%s AND host_name=%s AND source_checksum<>%s AND is_current=TRUE""",
                    (int(asset_id), host_name, source_checksum),
                )
                cursor.execute(
                    """INSERT INTO public.hosted_asset_references
                       (reference_id,asset_id,host_name,hosted_url,source_checksum,source_path,
                        status,is_current,verified_at,last_used_at)
                       VALUES (%s,%s,%s,%s,%s,%s,'READY',TRUE,now(),now())
                       ON CONFLICT (asset_id,host_name,source_checksum) DO UPDATE SET
                         hosted_url=EXCLUDED.hosted_url,source_path=EXCLUDED.source_path,
                         status='READY',is_current=TRUE,verified_at=now(),last_used_at=now(),
                         last_error_code=NULL,last_error_message=NULL,updated_at=now()
                       RETURNING *""",
                    (f"hosted_reference_{uuid4().hex}", int(asset_id), host_name, hosted_url,
                     source_checksum, source_path),
                )
                return self._record(cursor.fetchone())

    def touch_used(self, reference_id: str):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "UPDATE public.hosted_asset_references SET last_used_at=now(),updated_at=now() WHERE reference_id=%s",
                    (reference_id,),
                )

    def touch_verified(self, reference_id: str):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.hosted_asset_references SET verified_at=now(),last_used_at=now(),
                       status='READY',last_error_code=NULL,last_error_message=NULL,updated_at=now()
                       WHERE reference_id=%s""",
                    (reference_id,),
                )

    def mark_stale(self, reference_id: str, *, error_code: str, error_message: str):
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.hosted_asset_references SET status='STALE',is_current=FALSE,
                       last_error_code=%s,last_error_message=%s,updated_at=now() WHERE reference_id=%s""",
                    (error_code, error_message, reference_id),
                )

