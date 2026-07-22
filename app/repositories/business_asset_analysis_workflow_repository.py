"""Atomic state persistence for the Business Asset analysis workflow."""

from __future__ import annotations

from collections.abc import Callable

from app.database import get_db_connection
from app.models.asset_intelligence import AssetIntelligenceStatus


class BusinessAssetAnalysisWorkflowRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_state(self, asset_id: int) -> AssetIntelligenceStatus:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT p.analysis_status
                       FROM public.asset_intelligence_profiles p
                       JOIN public.business_asset_registrations b ON b.asset_id=p.asset_id
                       WHERE p.asset_id=%s""",
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        if not row:
            raise LookupError(f"Business Asset analysis profile not found: {asset_id}")
        try:
            return AssetIntelligenceStatus(str(row["analysis_status"]))
        except ValueError as exc:
            raise ValueError(f"Unknown Business Asset analysis state: {row['analysis_status']}") from exc

    def transition(self, asset_id: int, expected: AssetIntelligenceStatus,
                   target: AssetIntelligenceStatus, *, error_code: str | None = None,
                   error_message: str | None = None) -> bool:
        """Compare-and-set both workflow read models in one transaction."""
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.asset_intelligence_profiles
                       SET analysis_status=%s, error_code=%s, error_message=%s, updated_at=now()
                       WHERE asset_id=%s AND analysis_status=%s RETURNING asset_id""",
                    (target.value, error_code, error_message, int(asset_id), expected.value),
                )
                changed = cursor.fetchone() is not None
                if changed:
                    cursor.execute(
                        """UPDATE public.business_asset_registrations
                           SET content_intelligence_status=%s,
                               commerce_intelligence_refs=COALESCE(commerce_intelligence_refs,'{}'::jsonb)
                                   || jsonb_build_object('asset_intelligence_status', %s::text),
                               error_code=%s, error_message=%s,
                               last_refreshed_at=now(), updated_at=now()
                           WHERE asset_id=%s""",
                        (target.value, target.value, error_code, error_message, int(asset_id)),
                    )
        return changed

    def next_asset_to_orchestrate(self) -> int | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT p.asset_id FROM public.asset_intelligence_profiles p
                       JOIN public.business_asset_registrations b ON b.asset_id=p.asset_id
                       WHERE p.analysis_status IN (
                           'REGISTERED','PENDING','NUDENET_RUNNING','VISION_RUNNING',
                           'GROK_RUNNING','CONTENT_INTELLIGENCE_RUNNING',
                           'NUDENET_COMPLETE','VISION_COMPLETE',
                           'GROK_COMPLETE','CONTENT_INTELLIGENCE_COMPLETE'
                       ) ORDER BY p.updated_at,p.asset_id LIMIT 1"""
                )
                row = cursor.fetchone()
        return int(row["asset_id"]) if row else None

    def get_provider_completion(self, asset_id: int, provider: str) -> str | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT status FROM public.asset_intelligence_provider_results
                       WHERE asset_id=%s AND (
                           upper(provider)=upper(%s) OR upper(metadata->>'stage')=upper(%s)
                       )
                       ORDER BY analyzed_at DESC NULLS LAST, created_at DESC LIMIT 1""",
                    (int(asset_id), provider, provider),
                )
                row = cursor.fetchone()
        return str(row["status"]) if row else None
