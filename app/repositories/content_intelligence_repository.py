"""PostgreSQL repository for canonical Content Intelligence profiles."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any

from app.database import get_db_connection
from app.models.content_intelligence_profile import (
    CONTENT_INTELLIGENCE_ANALYSIS_VERSION,
    CONTENT_INTELLIGENCE_SCHEMA_VERSION,
    ContentIntelligenceProfile,
    ContentIntelligenceProfileStatus,
)


class ContentIntelligenceProfileRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_by_asset_id(self, asset_id: int) -> ContentIntelligenceProfile | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.content_intelligence_profiles
                    WHERE asset_id = %s
                    """,
                    (asset_id,),
                )
                row = cursor.fetchone()
        return self._profile_from_row(row) if row else None

    def upsert_profile(
        self,
        profile: ContentIntelligenceProfile,
    ) -> ContentIntelligenceProfile:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.content_intelligence_profiles (
                        asset_id,
                        status,
                        schema_version,
                        analysis_version,
                        required_components,
                        completed_components,
                        missing_components,
                        retry_count,
                        source_workflow,
                        approval_identity,
                        provenance,
                        content_profile,
                        normalized_context,
                        search_document,
                        error_code,
                        error_message,
                        reanalysis_reason,
                        analysis_started_at,
                        analysis_completed_at,
                        last_successful_analysis_at,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), now()
                    )
                    ON CONFLICT (asset_id)
                    DO UPDATE SET
                        status = EXCLUDED.status,
                        schema_version = EXCLUDED.schema_version,
                        analysis_version = EXCLUDED.analysis_version,
                        required_components = EXCLUDED.required_components,
                        completed_components = EXCLUDED.completed_components,
                        missing_components = EXCLUDED.missing_components,
                        retry_count = EXCLUDED.retry_count,
                        source_workflow = EXCLUDED.source_workflow,
                        approval_identity = EXCLUDED.approval_identity,
                        provenance = EXCLUDED.provenance,
                        content_profile = EXCLUDED.content_profile,
                        normalized_context = EXCLUDED.normalized_context,
                        search_document = EXCLUDED.search_document,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message,
                        reanalysis_reason = EXCLUDED.reanalysis_reason,
                        analysis_started_at = EXCLUDED.analysis_started_at,
                        analysis_completed_at = EXCLUDED.analysis_completed_at,
                        last_successful_analysis_at = EXCLUDED.last_successful_analysis_at,
                        updated_at = now()
                    RETURNING *
                    """,
                    (
                        int(profile.asset_id),
                        profile.status.value,
                        profile.schema_version,
                        profile.analysis_version,
                        json.dumps(list(profile.required_components)),
                        json.dumps(list(profile.completed_components)),
                        json.dumps(list(profile.missing_components)),
                        int(profile.retry_count or 0),
                        profile.source_workflow,
                        json.dumps(dict(profile.approval_identity), default=str),
                        json.dumps(dict(profile.provenance), default=str),
                        json.dumps(dict(profile.content_profile), default=str),
                        json.dumps(dict(profile.normalized_context), default=str),
                        profile.search_document,
                        profile.error_code,
                        profile.error_message,
                        profile.reanalysis_reason,
                        profile.analysis_started_at,
                        profile.analysis_completed_at,
                        profile.last_successful_analysis_at,
                        profile.created_at,
                    ),
                )
                row = cursor.fetchone()
        return self._profile_from_row(row)

    def search_profiles(
        self,
        *,
        query: str | None = None,
        status: str | None = None,
        limit: int = 100,
    ) -> tuple[ContentIntelligenceProfile, ...]:
        filters = []
        params: list[Any] = []
        if status:
            filters.append("status = %s")
            params.append(status)
        if query:
            filters.append(
                "to_tsvector('simple', COALESCE(search_document, '')) @@ plainto_tsquery('simple', %s)"
            )
            params.append(query)
        where = f"WHERE {' AND '.join(filters)}" if filters else ""
        params.append(limit)
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM public.content_intelligence_profiles
                    {where}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    tuple(params),
                )
                rows = cursor.fetchall()
        return tuple(self._profile_from_row(row) for row in rows)

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.content_intelligence_profiles') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.content_intelligence_profiles. Run forward migrations before using ContentIntelligenceProfileRepository."
            )

    @classmethod
    def _profile_from_row(cls, row: Mapping[str, Any]) -> ContentIntelligenceProfile:
        return ContentIntelligenceProfile(
            asset_id=int(row["asset_id"]),
            status=cls._status(row.get("status")),
            schema_version=str(row.get("schema_version") or CONTENT_INTELLIGENCE_SCHEMA_VERSION),
            analysis_version=str(row.get("analysis_version") or CONTENT_INTELLIGENCE_ANALYSIS_VERSION),
            required_components=cls._tuple(row.get("required_components")),
            completed_components=cls._tuple(row.get("completed_components")),
            missing_components=cls._tuple(row.get("missing_components")),
            retry_count=int(row.get("retry_count") or 0),
            source_workflow=row.get("source_workflow"),
            approval_identity=cls._mapping(row.get("approval_identity")),
            provenance=cls._mapping(row.get("provenance")),
            content_profile=cls._mapping(row.get("content_profile")),
            normalized_context=cls._mapping(row.get("normalized_context")),
            search_document=row.get("search_document"),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            reanalysis_reason=row.get("reanalysis_reason"),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            analysis_started_at=cls._datetime(row.get("analysis_started_at")),
            analysis_completed_at=cls._datetime(row.get("analysis_completed_at")),
            last_successful_analysis_at=cls._datetime(row.get("last_successful_analysis_at")),
        )

    @staticmethod
    def _status(value: Any) -> ContentIntelligenceProfileStatus:
        try:
            return ContentIntelligenceProfileStatus(str(value))
        except Exception:
            return ContentIntelligenceProfileStatus.PENDING

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        if isinstance(value, Mapping):
            return dict(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        return {}

    @staticmethod
    def _tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return (value,) if value.strip() else ()
            value = parsed
        if isinstance(value, (list, tuple, set)):
            return tuple(str(item) for item in value if str(item).strip())
        return (str(value),) if str(value).strip() else ()

    @staticmethod
    def _datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        return datetime.fromisoformat(str(value))
