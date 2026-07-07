"""Durable repository for Content Opportunity Intelligence records."""

from __future__ import annotations

import json
import hashlib
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping

from app.database import get_db_connection
from app.models.content_opportunity import (
    ContentDemandSignal,
    ContentOpportunity,
    ContentOpportunityFollowUp,
    ContentOpportunityFollowUpPriority,
    ContentOpportunityFollowUpStatus,
    ContentOpportunityMatchType,
    ContentOpportunityPriority,
    ContentOpportunityResolution,
    ContentOpportunityResolutionSource,
    ContentOpportunityResolutionStatus,
    ContentOpportunitySource,
    ContentOpportunityStatus,
    ContentRequestMatch,
)


class ContentOpportunityRepository:
    """Persist Content Opportunity read-model records in PostgreSQL.

    The repository intentionally stores the canonical dataclass payloads without
    owning matching, recommendation, delivery, or runtime behavior.
    """

    RECORD_TYPES = {
        "signals": "signal_id",
        "matches": "match_id",
        "opportunities": "opportunity_id",
        "resolutions": "resolution_id",
        "follow_ups": "follow_up_id",
    }

    def __init__(
        self,
        _legacy_path: str | None = None,
        *,
        connection_factory: Callable = get_db_connection,
    ) -> None:
        self._connection_factory = connection_factory
        self._namespace = (
            hashlib.sha256(str(_legacy_path).encode("utf-8")).hexdigest()[:12]
            if _legacy_path
            else ""
        )

    def load_records(self) -> Mapping[str, tuple[Any, ...]]:
        raw = {key: [] for key in self.RECORD_TYPES}
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT record_type, payload
                    FROM public.content_opportunity_records
                    WHERE record_type = ANY(%s)
                    ORDER BY created_at ASC, record_id ASC
                    """,
                    ([self._storage_type(key) for key in self.RECORD_TYPES],),
                )
                for row in cursor.fetchall():
                    record_type = self._public_type(row["record_type"])
                    if record_type in raw:
                        raw[record_type].append(dict(row["payload"] or {}))
        return {
            "signals": tuple(
                self._content_demand_signal(item)
                for item in raw.get("signals", ())
            ),
            "matches": tuple(
                self._content_request_match(item)
                for item in raw.get("matches", ())
            ),
            "opportunities": tuple(
                self._content_opportunity(item)
                for item in raw.get("opportunities", ())
            ),
            "resolutions": tuple(
                self._content_opportunity_resolution(item)
                for item in raw.get("resolutions", ())
            ),
            "follow_ups": tuple(
                self._content_opportunity_follow_up(item)
                for item in raw.get("follow_ups", ())
            ),
        }

    def save_records(
        self,
        *,
        signals: tuple[ContentDemandSignal, ...],
        matches: tuple[ContentRequestMatch, ...],
        opportunities: tuple[ContentOpportunity, ...],
        resolutions: tuple[ContentOpportunityResolution, ...],
        follow_ups: tuple[ContentOpportunityFollowUp, ...],
    ) -> None:
        payload = {
            "signals": self._serializable(signals),
            "matches": self._serializable(matches),
            "opportunities": self._serializable(opportunities),
            "resolutions": self._serializable(resolutions),
            "follow_ups": self._serializable(follow_ups),
        }
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                for record_type, id_field in self.RECORD_TYPES.items():
                    records = payload[record_type]
                    record_ids = tuple(
                        str(record.get(id_field) or "")
                        for record in records
                        if record.get(id_field)
                    )
                    if record_ids:
                        cursor.execute(
                            """
                            DELETE FROM public.content_opportunity_records
                            WHERE record_type = %s
                              AND NOT (record_id = ANY(%s))
                            """,
                            (self._storage_type(record_type), list(record_ids)),
                        )
                    else:
                        cursor.execute(
                            """
                            DELETE FROM public.content_opportunity_records
                            WHERE record_type = %s
                            """,
                            (self._storage_type(record_type),),
                        )
                    for record in records:
                        record_id = str(record.get(id_field) or "")
                        if not record_id:
                            continue
                        cursor.execute(
                            """
                            INSERT INTO public.content_opportunity_records (
                                record_type,
                                record_id,
                                payload,
                                created_at,
                                updated_at
                            )
                            VALUES (
                                %s,
                                %s,
                                %s::jsonb,
                                COALESCE(%s::timestamptz, now()),
                                COALESCE(%s::timestamptz, now())
                            )
                            ON CONFLICT (record_type, record_id)
                            DO UPDATE SET
                                payload = EXCLUDED.payload,
                                updated_at = EXCLUDED.updated_at
                            """,
                            (
                                self._storage_type(record_type),
                                record_id,
                                json.dumps(record),
                                record.get("created_at"),
                                record.get("updated_at"),
                            ),
                        )

    @staticmethod
    def _empty() -> Mapping[str, tuple[Any, ...]]:
        return {
            "signals": (),
            "matches": (),
            "opportunities": (),
            "resolutions": (),
            "follow_ups": (),
        }

    def _storage_type(self, record_type: str) -> str:
        if not self._namespace:
            return record_type
        return f"{self._namespace}:{record_type}"

    def _public_type(self, record_type: str) -> str:
        if self._namespace and record_type.startswith(f"{self._namespace}:"):
            return record_type.split(":", 1)[1]
        return record_type

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.content_opportunity_records') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.content_opportunity_records. Run forward migrations before using ContentOpportunityRepository."
            )

    @classmethod
    def _serializable(cls, value: Any) -> Any:
        if is_dataclass(value):
            return {
                field.name: cls._serializable(getattr(value, field.name))
                for field in fields(value)
            }
        if isinstance(value, Enum):
            return value.value
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, Mapping):
            return {
                str(key): cls._serializable(item)
                for key, item in value.items()
            }
        if isinstance(value, (tuple, list)):
            return [cls._serializable(item) for item in value]
        return value

    @classmethod
    def _content_demand_signal(
        cls,
        raw: Mapping[str, Any],
    ) -> ContentDemandSignal:
        return ContentDemandSignal(
            signal_id=str(raw.get("signal_id") or ""),
            customer_id=cls._optional_text(raw.get("customer_id")),
            provider=str(raw.get("provider") or "provider_neutral"),
            provider_customer_id=cls._optional_text(raw.get("provider_customer_id")),
            request_text=str(raw.get("request_text") or ""),
            normalized_terms=cls._tuple(raw.get("normalized_terms")),
            requested_content_type=cls._optional_text(raw.get("requested_content_type")),
            requested_format=cls._optional_text(raw.get("requested_format")),
            source=cls._enum(
                ContentOpportunitySource,
                raw.get("source"),
                ContentOpportunitySource.UNKNOWN,
            ),
            conversation_id=cls._optional_text(raw.get("conversation_id")),
            message_id=cls._optional_text(raw.get("message_id")),
            source_metadata=cls._mapping(raw.get("source_metadata")),
            is_vip=bool(raw.get("is_vip")),
            customer_importance=cls._optional_text(raw.get("customer_importance")),
            created_at=cls._datetime(raw.get("created_at")),
            updated_at=cls._datetime(raw.get("updated_at")),
            notes=cls._tuple(raw.get("notes")),
            metadata=cls._mapping(raw.get("metadata")),
        )

    @classmethod
    def _content_request_match(
        cls,
        raw: Mapping[str, Any],
    ) -> ContentRequestMatch:
        return ContentRequestMatch(
            match_id=str(raw.get("match_id") or ""),
            demand_signal=cls._content_demand_signal(raw.get("demand_signal") or {}),
            match_type=cls._enum(
                ContentOpportunityMatchType,
                raw.get("match_type"),
                ContentOpportunityMatchType.NONE,
            ),
            product_ids=cls._tuple(raw.get("product_ids")),
            experience_ids=cls._tuple(raw.get("experience_ids")),
            asset_ids=cls._tuple(raw.get("asset_ids")),
            confidence=float(raw.get("confidence") or 0.0),
            status=cls._enum(
                ContentOpportunityStatus,
                raw.get("status"),
                ContentOpportunityStatus.MATCHED,
            ),
            can_offer_existing_content=bool(raw.get("can_offer_existing_content")),
            match_evidence=cls._mapping(raw.get("match_evidence")),
            safe_response_guidance=cls._mapping(raw.get("safe_response_guidance")),
            created_at=cls._datetime(raw.get("created_at")),
            updated_at=cls._datetime(raw.get("updated_at")),
            notes=cls._tuple(raw.get("notes")),
            metadata=cls._mapping(raw.get("metadata")),
        )

    @classmethod
    def _content_opportunity(
        cls,
        raw: Mapping[str, Any],
    ) -> ContentOpportunity:
        match_raw = raw.get("match")
        return ContentOpportunity(
            opportunity_id=str(raw.get("opportunity_id") or ""),
            demand_signal=cls._content_demand_signal(raw.get("demand_signal") or {}),
            status=cls._enum(
                ContentOpportunityStatus,
                raw.get("status"),
                ContentOpportunityStatus.UNKNOWN,
            ),
            priority=cls._enum(
                ContentOpportunityPriority,
                raw.get("priority"),
                ContentOpportunityPriority.NORMAL,
            ),
            normalized_terms=cls._tuple(raw.get("normalized_terms")),
            demand_count=int(raw.get("demand_count") or 1),
            match=cls._content_request_match(match_raw) if isinstance(match_raw, Mapping) else None,
            product_ids=cls._tuple(raw.get("product_ids")),
            experience_ids=cls._tuple(raw.get("experience_ids")),
            asset_ids=cls._tuple(raw.get("asset_ids")),
            confidence=float(raw.get("confidence") or 0.0),
            repeat_demand=bool(raw.get("repeat_demand")),
            vip_demand=bool(raw.get("vip_demand")),
            safe_response_guidance=cls._mapping(raw.get("safe_response_guidance")),
            next_recommended_action=str(raw.get("next_recommended_action") or "Review content opportunity"),
            supporting_evidence=cls._mapping(raw.get("supporting_evidence")),
            created_at=cls._datetime(raw.get("created_at")),
            updated_at=cls._datetime(raw.get("updated_at")),
            notes=cls._tuple(raw.get("notes")),
            metadata=cls._mapping(raw.get("metadata")),
        )

    @classmethod
    def _content_opportunity_resolution(
        cls,
        raw: Mapping[str, Any],
    ) -> ContentOpportunityResolution:
        return ContentOpportunityResolution(
            resolution_id=str(raw.get("resolution_id") or ""),
            opportunity_id=str(raw.get("opportunity_id") or ""),
            normalized_terms=cls._tuple(raw.get("normalized_terms")),
            matched_product_ids=cls._tuple(raw.get("matched_product_ids")),
            matched_experience_ids=cls._tuple(raw.get("matched_experience_ids")),
            matched_asset_ids=cls._tuple(raw.get("matched_asset_ids")),
            waiting_customer_ids=cls._tuple(raw.get("waiting_customer_ids")),
            waiting_provider_customer_ids=cls._tuple(raw.get("waiting_provider_customer_ids")),
            request_count=int(raw.get("request_count") or 0),
            customer_count=int(raw.get("customer_count") or 0),
            vip_customer_count=int(raw.get("vip_customer_count") or 0),
            confidence=float(raw.get("confidence") or 0.0),
            evidence=cls._mapping(raw.get("evidence")),
            status=cls._enum(
                ContentOpportunityResolutionStatus,
                raw.get("status"),
                ContentOpportunityResolutionStatus.RESOLUTION_READY,
            ),
            source=cls._enum(
                ContentOpportunityResolutionSource,
                raw.get("source"),
                ContentOpportunityResolutionSource.UNKNOWN,
            ),
            safe_guidance=cls._mapping(raw.get("safe_guidance")),
            created_at=cls._datetime(raw.get("created_at")),
            updated_at=cls._datetime(raw.get("updated_at")),
            notes=cls._tuple(raw.get("notes")),
            metadata=cls._mapping(raw.get("metadata")),
        )

    @classmethod
    def _content_opportunity_follow_up(
        cls,
        raw: Mapping[str, Any],
    ) -> ContentOpportunityFollowUp:
        return ContentOpportunityFollowUp(
            follow_up_id=str(raw.get("follow_up_id") or ""),
            resolution_id=str(raw.get("resolution_id") or ""),
            opportunity_id=str(raw.get("opportunity_id") or ""),
            customer_id=cls._optional_text(raw.get("customer_id")),
            provider=str(raw.get("provider") or "provider_neutral"),
            provider_customer_id=cls._optional_text(raw.get("provider_customer_id")),
            matched_product_ids=cls._tuple(raw.get("matched_product_ids")),
            matched_experience_ids=cls._tuple(raw.get("matched_experience_ids")),
            matched_asset_ids=cls._tuple(raw.get("matched_asset_ids")),
            original_request_text=str(raw.get("original_request_text") or ""),
            normalized_terms=cls._tuple(raw.get("normalized_terms")),
            vip_customer=bool(raw.get("vip_customer")),
            priority=cls._enum(
                ContentOpportunityFollowUpPriority,
                raw.get("priority"),
                ContentOpportunityFollowUpPriority.NORMAL,
            ),
            confidence=float(raw.get("confidence") or 0.0),
            evidence=cls._mapping(raw.get("evidence")),
            status=cls._enum(
                ContentOpportunityFollowUpStatus,
                raw.get("status"),
                ContentOpportunityFollowUpStatus.READY,
            ),
            safe_guidance=cls._mapping(raw.get("safe_guidance")),
            created_at=cls._datetime(raw.get("created_at")),
            updated_at=cls._datetime(raw.get("updated_at")),
            completed_at=cls._optional_datetime(raw.get("completed_at")),
            metadata=cls._mapping(raw.get("metadata")),
        )

    @staticmethod
    def _tuple(value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, str):
            return (value,)
        return tuple(str(item) for item in value if str(item).strip())

    @staticmethod
    def _mapping(value: Any) -> Mapping[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @staticmethod
    def _datetime(value: Any) -> datetime:
        parsed = ContentOpportunityRepository._optional_datetime(value)
        return parsed or datetime.now().astimezone()

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _enum(enum_type, value: Any, default):
        try:
            return enum_type(value)
        except Exception:
            return default
