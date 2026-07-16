"""Persistence for canonical Asset Intelligence and raw provider results."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from app.database import get_db_connection
from app.models.asset_intelligence import (
    ASSET_INTELLIGENCE_SCHEMA_VERSION,
    AssetIntelligenceProfile,
    AssetIntelligenceProviderResult,
    AssetIntelligenceStatus,
)


class AssetIntelligenceRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_profile(self, asset_id: int) -> AssetIntelligenceProfile | None:
        with self._connection_factory() as connection:
            self._ensure_tables(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.asset_intelligence_profiles WHERE asset_id = %s",
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        return self._profile_from_row(row) if row else None

    def upsert_profile(
        self,
        profile: AssetIntelligenceProfile,
    ) -> AssetIntelligenceProfile:
        with self._connection_factory() as connection:
            self._ensure_tables(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.asset_intelligence_profiles (
                        asset_id, creator_profile_id, schema_version,
                        analysis_status, analyzed_at, profile_data,
                        error_code, error_message, created_at, updated_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s::jsonb, %s, %s,
                        COALESCE(%s, now()), now()
                    )
                    ON CONFLICT (asset_id) DO UPDATE SET
                        creator_profile_id = EXCLUDED.creator_profile_id,
                        schema_version = EXCLUDED.schema_version,
                        analysis_status = EXCLUDED.analysis_status,
                        analyzed_at = EXCLUDED.analyzed_at,
                        profile_data = EXCLUDED.profile_data,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message,
                        updated_at = now()
                    RETURNING *
                    """,
                    (
                        int(profile.asset_id),
                        int(profile.creator_profile_id),
                        profile.schema_version,
                        profile.analysis_status.value,
                        profile.analyzed_at,
                        json.dumps(profile.to_payload(), default=str),
                        profile.error_code,
                        profile.error_message,
                        profile.created_at,
                    ),
                )
                row = cursor.fetchone()
        return self._profile_from_row(row)

    def save_provider_result(
        self,
        result: AssetIntelligenceProviderResult,
    ) -> AssetIntelligenceProviderResult:
        with self._connection_factory() as connection:
            self._ensure_tables(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.asset_intelligence_provider_results (
                        result_id, asset_id, creator_profile_id, provider, run_id, execution_id,
                        provider_version, status, analyzed_at, raw_response,
                        normalized_fields, field_confidence, error_code,
                        error_message, metadata, created_at
                    ) VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s, %s, %s::jsonb,
                        COALESCE(%s, now())
                    )
                    ON CONFLICT (result_id) DO NOTHING
                    RETURNING *
                    """,
                    (
                        result.result_id,
                        int(result.asset_id),
                        int(result.creator_profile_id),
                        result.provider,
                        result.run_id,
                        result.execution_id,
                        result.provider_version,
                        result.status.value,
                        result.analyzed_at,
                        json.dumps(result.raw_response, default=str),
                        json.dumps(dict(result.normalized_fields), default=str),
                        json.dumps(dict(result.field_confidence), default=str),
                        result.error_code,
                        result.error_message,
                        json.dumps(dict(result.metadata), default=str),
                        result.created_at,
                    ),
                )
                row = cursor.fetchone()
                if row is None:
                    cursor.execute(
                        """
                        SELECT * FROM public.asset_intelligence_provider_results
                        WHERE result_id = %s
                        """,
                        (result.result_id,),
                    )
                    row = cursor.fetchone()
        return self._provider_result_from_row(row)

    def list_provider_results(
        self,
        asset_id: int,
        run_id: str | None = None,
    ) -> tuple[AssetIntelligenceProviderResult, ...]:
        with self._connection_factory() as connection:
            self._ensure_tables(connection)
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT * FROM public.asset_intelligence_provider_results
                    WHERE asset_id = %s AND (%s::text IS NULL OR run_id = %s)
                    ORDER BY created_at, result_id
                    """,
                    (int(asset_id), run_id, run_id),
                )
                rows = cursor.fetchall()
        return tuple(self._provider_result_from_row(row) for row in rows)

    @staticmethod
    def _ensure_tables(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    to_regclass('public.asset_intelligence_profiles') AS profiles,
                    to_regclass('public.asset_intelligence_provider_results') AS results
                """
            )
            row = cursor.fetchone()
        if not row or not row["profiles"] or not row["results"]:
            raise RuntimeError(
                "Asset Intelligence tables are missing; run forward migrations."
            )

    @classmethod
    def _profile_from_row(cls, row: Mapping[str, Any]) -> AssetIntelligenceProfile:
        payload = cls._mapping(row.get("profile_data"))
        tuple_fields = {
            "objects", "clothing", "accessories", "colors",
            "visible_body_regions", "risk_flags", "tags", "themes",
            "keywords", "content_categories", "suggested_collections",
            "suggested_use_cases",
        }
        for name in tuple_fields:
            payload[name] = tuple(payload.get(name) or ())
        return AssetIntelligenceProfile(
            asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            schema_version=str(
                row.get("schema_version") or ASSET_INTELLIGENCE_SCHEMA_VERSION
            ),
            analysis_status=cls._status(row.get("analysis_status")),
            analyzed_at=cls._datetime(row.get("analyzed_at")),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            **payload,
        )

    @classmethod
    def _provider_result_from_row(
        cls,
        row: Mapping[str, Any],
    ) -> AssetIntelligenceProviderResult:
        return AssetIntelligenceProviderResult(
            result_id=str(row["result_id"]),
            asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            provider=str(row["provider"]),
            run_id=row.get("run_id"),
            execution_id=row.get("execution_id"),
            provider_version=row.get("provider_version"),
            status=cls._status(row.get("status")),
            analyzed_at=cls._datetime(row.get("analyzed_at")),
            raw_response=row.get("raw_response"),
            normalized_fields=cls._mapping(row.get("normalized_fields")),
            field_confidence={
                key: float(value)
                for key, value in cls._mapping(row.get("field_confidence")).items()
            },
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            metadata=cls._mapping(row.get("metadata")),
            created_at=cls._datetime(row.get("created_at")),
        )

    @staticmethod
    def _status(value: Any) -> AssetIntelligenceStatus:
        try:
            return AssetIntelligenceStatus(str(value))
        except Exception:
            return AssetIntelligenceStatus.PENDING

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        return datetime.fromisoformat(str(value)) if value else None
