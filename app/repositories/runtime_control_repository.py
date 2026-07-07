"""Durable PostgreSQL repository for Creator OS runtime control state."""

from __future__ import annotations

import json
import hashlib
from dataclasses import asdict, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Mapping

from app.database import get_db_connection
from app.models.runtime_control import (
    RuntimeControlState,
    RuntimeMode,
    RuntimeObservation,
    RuntimeStatus,
)


class RuntimeControlRepository:
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

    def get_state(self, creator_profile_id: str) -> RuntimeControlState | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.runtime_control_records
                    WHERE creator_profile_id = %s
                    """,
                    (self._storage_profile_id(str(creator_profile_id)),),
                )
                row = cursor.fetchone()
        return self._state(row) if row else None

    def save_state(self, state: RuntimeControlState) -> None:
        payload = self._serializable(state)
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.runtime_control_records (
                        creator_profile_id,
                        mode,
                        status,
                        current_runtime_provider,
                        last_started,
                        last_stopped,
                        active_conversations,
                        pending_deliveries,
                        pending_offers,
                        observed_recommendations,
                        metadata,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s
                    )
                    ON CONFLICT (creator_profile_id)
                    DO UPDATE SET
                        mode = EXCLUDED.mode,
                        status = EXCLUDED.status,
                        current_runtime_provider = EXCLUDED.current_runtime_provider,
                        last_started = EXCLUDED.last_started,
                        last_stopped = EXCLUDED.last_stopped,
                        active_conversations = EXCLUDED.active_conversations,
                        pending_deliveries = EXCLUDED.pending_deliveries,
                        pending_offers = EXCLUDED.pending_offers,
                        observed_recommendations = EXCLUDED.observed_recommendations,
                        metadata = EXCLUDED.metadata,
                        updated_at = EXCLUDED.updated_at
                    """,
                    (
                        self._storage_profile_id(state.creator_profile_id),
                        state.mode.value,
                        state.status.value,
                        state.current_runtime_provider,
                        state.last_started,
                        state.last_stopped,
                        state.active_conversations,
                        state.pending_deliveries,
                        state.pending_offers,
                        json.dumps(payload["observed_recommendations"]),
                        json.dumps(payload["metadata"]),
                        state.updated_at,
                    ),
                )

    def _storage_profile_id(self, creator_profile_id: str) -> str:
        if not self._namespace:
            return creator_profile_id
        return f"{self._namespace}:{creator_profile_id}"

    def _public_profile_id(self, creator_profile_id: str) -> str:
        if self._namespace and creator_profile_id.startswith(f"{self._namespace}:"):
            return creator_profile_id.split(":", 1)[1]
        return creator_profile_id

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.runtime_control_records') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.runtime_control_records. Run forward migrations before using RuntimeControlRepository."
            )

    @classmethod
    def _serializable(cls, value: Any) -> Any:
        if is_dataclass(value):
            return {
                key: cls._serializable(item)
                for key, item in asdict(value).items()
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
    def _state(cls, raw: Mapping[str, Any]) -> RuntimeControlState:
        return RuntimeControlState(
            creator_profile_id=cls._public_profile_id_static(
                str(raw.get("creator_profile_id") or "default")
            ),
            mode=cls._mode(raw.get("mode")),
            status=cls._status(raw.get("status")),
            current_runtime_provider=str(
                raw.get("current_runtime_provider") or "telegram"
            ),
            last_started=cls._optional_datetime(raw.get("last_started")),
            last_stopped=cls._optional_datetime(raw.get("last_stopped")),
            active_conversations=int(raw.get("active_conversations") or 0),
            pending_deliveries=int(raw.get("pending_deliveries") or 0),
            pending_offers=int(raw.get("pending_offers") or 0),
            observed_recommendations=tuple(
                cls._observation(item)
                for item in raw.get("observed_recommendations", ())
                if isinstance(item, Mapping)
            ),
            updated_at=cls._datetime(raw.get("updated_at")),
            metadata=dict(raw.get("metadata") or {}),
        )

    @staticmethod
    def _public_profile_id_static(creator_profile_id: str) -> str:
        if ":" in creator_profile_id:
            prefix, value = creator_profile_id.split(":", 1)
            if len(prefix) == 12 and all(char in "0123456789abcdef" for char in prefix):
                return value
        return creator_profile_id

    @classmethod
    def _observation(cls, raw: Mapping[str, Any]) -> RuntimeObservation:
        return RuntimeObservation(
            observation_id=str(raw.get("observation_id") or ""),
            creator_profile_id=str(raw.get("creator_profile_id") or "default"),
            customer_id=cls._optional_text(raw.get("customer_id")),
            conversation_id=cls._optional_text(raw.get("conversation_id")),
            message_text=str(raw.get("message_text") or ""),
            suggested_reply=cls._optional_text(raw.get("suggested_reply")),
            suggested_offer=dict(raw.get("suggested_offer") or {}),
            suggested_delivery=dict(raw.get("suggested_delivery") or {}),
            suggested_follow_up=dict(raw.get("suggested_follow_up") or {}),
            provider=str(raw.get("provider") or "telegram"),
            created_at=cls._datetime(raw.get("created_at")),
            metadata=dict(raw.get("metadata") or {}),
        )

    @staticmethod
    def _mode(value: Any) -> RuntimeMode:
        try:
            return RuntimeMode(value)
        except Exception:
            return RuntimeMode.OFFLINE

    @staticmethod
    def _status(value: Any) -> RuntimeStatus:
        try:
            return RuntimeStatus(value)
        except Exception:
            return RuntimeStatus.OFFLINE

    @staticmethod
    def _datetime(value: Any) -> datetime:
        parsed = RuntimeControlRepository._optional_datetime(value)
        return parsed or datetime.now(timezone.utc)

    @staticmethod
    def _optional_datetime(value: Any) -> datetime | None:
        if isinstance(value, datetime):
            return value
        if not value:
            return None
        return datetime.fromisoformat(str(value))

    @staticmethod
    def _optional_text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None
