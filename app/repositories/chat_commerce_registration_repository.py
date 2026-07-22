"""Persistence for Chat Commerce Registration inventory records."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.database import get_db_connection
from app.models.chat_commerce_registration import (
    CHAT_COMMERCE_REGISTRATION_SCHEMA_VERSION,
    ChatAvailabilityState,
    ChatCommerceAssetRecord,
)


class ChatCommerceRegistrationRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_by_asset_id(self, asset_id: int) -> ChatCommerceAssetRecord | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.chat_commerce_registrations
                    WHERE asset_id = %s
                    """,
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def upsert_record(
        self,
        record: ChatCommerceAssetRecord,
    ) -> ChatCommerceAssetRecord:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.chat_commerce_registrations (
                        chat_registration_id,
                        asset_id,
                        registration_id,
                        fulfillment_id,
                        creator_profile_id,
                        commerce_destination,
                        availability_state,
                        chat_ready,
                        fulfillment_ready,
                        recommendation_eligible,
                        delivery_eligible,
                        active,
                        temporarily_unavailable,
                        retired,
                        product_ids,
                        experience_ids,
                        source_workflow,
                        media_link,
                        provider_media_id,
                        provider,
                        registered_at,
                        chat_ready_at,
                        temporarily_unavailable_at,
                        retired_at,
                        last_refreshed_at,
                        registration_provenance,
                        block_reasons,
                        warnings,
                        error_code,
                        error_message,
                        retry_count,
                        schema_version,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), now()
                    )
                    ON CONFLICT (asset_id)
                    DO UPDATE SET
                        registration_id = EXCLUDED.registration_id,
                        fulfillment_id = EXCLUDED.fulfillment_id,
                        creator_profile_id = EXCLUDED.creator_profile_id,
                        commerce_destination = EXCLUDED.commerce_destination,
                        availability_state = EXCLUDED.availability_state,
                        chat_ready = EXCLUDED.chat_ready,
                        fulfillment_ready = EXCLUDED.fulfillment_ready,
                        recommendation_eligible = EXCLUDED.recommendation_eligible,
                        delivery_eligible = EXCLUDED.delivery_eligible,
                        active = EXCLUDED.active,
                        temporarily_unavailable = EXCLUDED.temporarily_unavailable,
                        retired = EXCLUDED.retired,
                        product_ids = EXCLUDED.product_ids,
                        experience_ids = EXCLUDED.experience_ids,
                        source_workflow = EXCLUDED.source_workflow,
                        media_link = EXCLUDED.media_link,
                        provider_media_id = EXCLUDED.provider_media_id,
                        provider = EXCLUDED.provider,
                        registered_at = COALESCE(
                            public.chat_commerce_registrations.registered_at,
                            EXCLUDED.registered_at
                        ),
                        chat_ready_at = COALESCE(
                            EXCLUDED.chat_ready_at,
                            public.chat_commerce_registrations.chat_ready_at
                        ),
                        temporarily_unavailable_at = EXCLUDED.temporarily_unavailable_at,
                        retired_at = EXCLUDED.retired_at,
                        last_refreshed_at = EXCLUDED.last_refreshed_at,
                        registration_provenance = EXCLUDED.registration_provenance,
                        block_reasons = EXCLUDED.block_reasons,
                        warnings = EXCLUDED.warnings,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message,
                        retry_count = EXCLUDED.retry_count,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = now()
                    RETURNING *
                    """,
                    self._params(record),
                )
                row = cursor.fetchone()
        stored = self._record_from_row(row)
        self.append_history(stored)
        return stored

    def append_history(self, record: ChatCommerceAssetRecord) -> None:
        with self._connection_factory() as conn:
            self._ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.chat_commerce_registration_history (
                        chat_registration_id,
                        asset_id,
                        availability_state,
                        chat_ready,
                        block_reasons,
                        snapshot,
                        created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, now())
                    """,
                    (
                        record.chat_registration_id,
                        int(record.asset_id),
                        record.availability_state.value,
                        bool(record.chat_ready),
                        json.dumps(list(record.block_reasons), default=str),
                        json.dumps(record.to_context(), default=str),
                    ),
                )

    def list_chat_ready(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        where = [
            "availability_state = %s",
            "chat_ready = TRUE",
            "active = TRUE",
            "temporarily_unavailable = FALSE",
            "retired = FALSE",
            """EXISTS (
                SELECT 1
                FROM public.business_asset_registrations business_asset
                WHERE business_asset.asset_id = public.chat_commerce_registrations.asset_id
                  AND business_asset.is_archived = FALSE
            )""",
            """NOT EXISTS (
                SELECT 1 FROM public.photoshoot_asset_memberships photoshoot_member
                WHERE photoshoot_member.asset_id = public.chat_commerce_registrations.asset_id
                  AND photoshoot_member.approved = TRUE
            )""",
        ]
        params: list[Any] = [ChatAvailabilityState.CHAT_READY.value]
        if creator_profile_id is not None:
            where.append("creator_profile_id = %s")
            params.append(int(creator_profile_id))
        return self._list_by_filter(" AND ".join(where), tuple(params), limit=limit)

    def list_by_state(
        self,
        state: ChatAvailabilityState | str,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        value = state.value if isinstance(state, ChatAvailabilityState) else str(state)
        return self._list_by_filter(
            "availability_state = %s AND " + self._active_business_asset_clause(),
            (value,),
            limit=limit,
        )

    def list_by_product(
        self,
        product_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self._list_by_filter(
            "product_ids ? %s AND " + self._active_business_asset_clause(),
            (str(product_id),),
            limit=limit,
        )

    def list_by_experience(
        self,
        experience_id: str,
        *,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        return self._list_by_filter(
            "experience_ids ? %s AND " + self._active_business_asset_clause(),
            (str(experience_id),),
            limit=limit,
        )

    @staticmethod
    def _active_business_asset_clause() -> str:
        return """EXISTS (
            SELECT 1
            FROM public.business_asset_registrations business_asset
            WHERE business_asset.asset_id = public.chat_commerce_registrations.asset_id
              AND business_asset.is_archived = FALSE
        ) AND NOT EXISTS (
            SELECT 1 FROM public.photoshoot_asset_memberships photoshoot_member
            WHERE photoshoot_member.asset_id = public.chat_commerce_registrations.asset_id
              AND photoshoot_member.approved = TRUE
        )"""

    def list_recommendation_eligible(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        records = self.list_chat_ready(
            creator_profile_id=creator_profile_id,
            limit=limit,
        )
        return tuple(record for record in records if record.recommendation_eligible)

    def list_delivery_eligible(
        self,
        *,
        creator_profile_id: int | None = None,
        limit: int = 100,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        records = self.list_chat_ready(
            creator_profile_id=creator_profile_id,
            limit=limit,
        )
        return tuple(record for record in records if record.delivery_eligible)

    def _list_by_filter(
        self,
        where: str,
        params: tuple[Any, ...],
        *,
        limit: int,
    ) -> tuple[ChatCommerceAssetRecord, ...]:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM public.chat_commerce_registrations
                    WHERE {where}
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (*params, int(limit)),
                )
                rows = cursor.fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.chat_commerce_registrations') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.chat_commerce_registrations. Run forward migrations before using ChatCommerceRegistrationRepository."
            )

    @staticmethod
    def _ensure_history_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.chat_commerce_registration_history') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.chat_commerce_registration_history. Run forward migrations before using ChatCommerceRegistrationRepository."
            )

    @staticmethod
    def _params(record: ChatCommerceAssetRecord) -> tuple[Any, ...]:
        return (
            record.chat_registration_id,
            int(record.asset_id),
            record.registration_id,
            record.fulfillment_id,
            record.creator_profile_id,
            record.commerce_destination,
            record.availability_state.value,
            bool(record.chat_ready),
            bool(record.fulfillment_ready),
            bool(record.recommendation_eligible),
            bool(record.delivery_eligible),
            bool(record.active),
            bool(record.temporarily_unavailable),
            bool(record.retired),
            json.dumps(list(record.product_ids), default=str),
            json.dumps(list(record.experience_ids), default=str),
            record.source_workflow,
            record.media_link,
            record.provider_media_id,
            record.provider,
            record.registered_at,
            record.chat_ready_at,
            record.temporarily_unavailable_at,
            record.retired_at,
            record.last_refreshed_at,
            json.dumps(dict(record.registration_provenance or {}), default=str),
            json.dumps(list(record.block_reasons), default=str),
            json.dumps(list(record.warnings), default=str),
            record.error_code,
            record.error_message,
            int(record.retry_count or 0),
            record.schema_version,
            record.created_at,
        )

    @classmethod
    def _record_from_row(cls, row: Mapping[str, Any]) -> ChatCommerceAssetRecord:
        return ChatCommerceAssetRecord(
            chat_registration_id=UUID(str(row["chat_registration_id"])),
            asset_id=int(row["asset_id"]),
            registration_id=UUID(str(row["registration_id"])),
            fulfillment_id=UUID(str(row["fulfillment_id"])),
            creator_profile_id=row.get("creator_profile_id"),
            commerce_destination=row.get("commerce_destination"),
            availability_state=cls._availability_state(row.get("availability_state")),
            chat_ready=bool(row.get("chat_ready")),
            fulfillment_ready=bool(row.get("fulfillment_ready")),
            recommendation_eligible=bool(row.get("recommendation_eligible")),
            delivery_eligible=bool(row.get("delivery_eligible")),
            active=bool(row.get("active")),
            temporarily_unavailable=bool(row.get("temporarily_unavailable")),
            retired=bool(row.get("retired")),
            product_ids=cls._tuple(row.get("product_ids")),
            experience_ids=cls._tuple(row.get("experience_ids")),
            source_workflow=row.get("source_workflow"),
            media_link=row.get("media_link"),
            provider_media_id=row.get("provider_media_id"),
            provider=row.get("provider"),
            registered_at=cls._datetime(row.get("registered_at")),
            chat_ready_at=cls._datetime(row.get("chat_ready_at")),
            temporarily_unavailable_at=cls._datetime(
                row.get("temporarily_unavailable_at")
            ),
            retired_at=cls._datetime(row.get("retired_at")),
            last_refreshed_at=cls._datetime(row.get("last_refreshed_at")),
            registration_provenance=cls._mapping(row.get("registration_provenance")),
            block_reasons=cls._tuple(row.get("block_reasons")),
            warnings=cls._tuple(row.get("warnings")),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            retry_count=int(row.get("retry_count") or 0),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            schema_version=str(
                row.get("schema_version")
                or CHAT_COMMERCE_REGISTRATION_SCHEMA_VERSION
            ),
        )

    @staticmethod
    def _availability_state(value: Any) -> ChatAvailabilityState:
        try:
            return ChatAvailabilityState(str(value))
        except Exception:
            return ChatAvailabilityState.PENDING

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
