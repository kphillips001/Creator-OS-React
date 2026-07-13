"""Persistence for Business Asset fulfillment registrations."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

from app.database import get_db_connection
from app.models.commerce_destination import DestinationRoutingOwner
from app.models.fulfillment_registration import (
    FULFILLMENT_REGISTRATION_SCHEMA_VERSION,
    BusinessAssetFulfillmentRecord,
    FulfillmentLifecycleState,
    FulfillmentRoute,
    MediaLinkVerificationState,
)


class FulfillmentRegistrationRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_by_asset_and_route(
        self,
        asset_id: int,
        route: FulfillmentRoute | str,
    ) -> BusinessAssetFulfillmentRecord | None:
        route_value = route.value if isinstance(route, FulfillmentRoute) else str(route)
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_fulfillment_registrations
                    WHERE asset_id = %s
                      AND route = %s
                    """,
                    (int(asset_id), route_value),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def get_by_route_intent_id(
        self,
        routing_intent_id: UUID | str,
    ) -> BusinessAssetFulfillmentRecord | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_fulfillment_registrations
                    WHERE routing_intent_id = %s
                    """,
                    (routing_intent_id,),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def get_by_publishing_job_id(
        self,
        publishing_job_id: UUID | str,
    ) -> BusinessAssetFulfillmentRecord | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_fulfillment_registrations
                    WHERE publishing_job_id = %s
                    """,
                    (publishing_job_id,),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def get_by_media_link(
        self,
        media_link: str,
    ) -> BusinessAssetFulfillmentRecord | None:
        normalized = str(media_link or "").strip()
        if not normalized:
            return None
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_fulfillment_registrations
                    WHERE media_link = %s
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (normalized,),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def upsert_record(
        self,
        record: BusinessAssetFulfillmentRecord,
    ) -> BusinessAssetFulfillmentRecord:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.business_asset_fulfillment_registrations (
                        fulfillment_id,
                        asset_id,
                        registration_id,
                        routing_intent_id,
                        route,
                        route_owner,
                        provider,
                        provider_account_id,
                        publishing_job_id,
                        upload_attempt_id,
                        provider_media_id,
                        provider_preview_media_id,
                        provider_full_media_id,
                        provider_processing_status,
                        lifecycle_state,
                        media_link,
                        media_link_verification_state,
                        media_link_submitted_at,
                        media_link_verified_at,
                        fulfillment_ready_at,
                        failure_code,
                        failure_message,
                        retry_count,
                        retry_required,
                        provider_metadata,
                        provenance,
                        schema_version,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s,
                        COALESCE(%s::timestamptz, now()), now()
                    )
                    ON CONFLICT (asset_id, route)
                    DO UPDATE SET
                        registration_id = EXCLUDED.registration_id,
                        routing_intent_id = EXCLUDED.routing_intent_id,
                        route_owner = EXCLUDED.route_owner,
                        provider = EXCLUDED.provider,
                        provider_account_id = EXCLUDED.provider_account_id,
                        publishing_job_id = COALESCE(
                            EXCLUDED.publishing_job_id,
                            public.business_asset_fulfillment_registrations.publishing_job_id
                        ),
                        upload_attempt_id = EXCLUDED.upload_attempt_id,
                        provider_media_id = COALESCE(
                            EXCLUDED.provider_media_id,
                            public.business_asset_fulfillment_registrations.provider_media_id
                        ),
                        provider_preview_media_id = COALESCE(
                            EXCLUDED.provider_preview_media_id,
                            public.business_asset_fulfillment_registrations.provider_preview_media_id
                        ),
                        provider_full_media_id = COALESCE(
                            EXCLUDED.provider_full_media_id,
                            public.business_asset_fulfillment_registrations.provider_full_media_id
                        ),
                        provider_processing_status = EXCLUDED.provider_processing_status,
                        lifecycle_state = EXCLUDED.lifecycle_state,
                        media_link = COALESCE(
                            EXCLUDED.media_link,
                            public.business_asset_fulfillment_registrations.media_link
                        ),
                        media_link_verification_state = EXCLUDED.media_link_verification_state,
                        media_link_submitted_at = COALESCE(
                            EXCLUDED.media_link_submitted_at,
                            public.business_asset_fulfillment_registrations.media_link_submitted_at
                        ),
                        media_link_verified_at = COALESCE(
                            EXCLUDED.media_link_verified_at,
                            public.business_asset_fulfillment_registrations.media_link_verified_at
                        ),
                        fulfillment_ready_at = COALESCE(
                            EXCLUDED.fulfillment_ready_at,
                            public.business_asset_fulfillment_registrations.fulfillment_ready_at
                        ),
                        failure_code = EXCLUDED.failure_code,
                        failure_message = EXCLUDED.failure_message,
                        retry_count = EXCLUDED.retry_count,
                        retry_required = EXCLUDED.retry_required,
                        provider_metadata = EXCLUDED.provider_metadata,
                        provenance = EXCLUDED.provenance,
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

    def append_history(self, record: BusinessAssetFulfillmentRecord) -> None:
        with self._connection_factory() as conn:
            self._ensure_history_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.business_asset_fulfillment_history (
                        fulfillment_id,
                        asset_id,
                        route,
                        lifecycle_state,
                        media_link_verification_state,
                        publishing_job_id,
                        provider_media_id,
                        failure_code,
                        failure_message,
                        snapshot,
                        created_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, now()
                    )
                    """,
                    (
                        record.fulfillment_id,
                        int(record.asset_id),
                        record.route.value,
                        record.lifecycle_state.value,
                        record.media_link_verification_state.value,
                        record.publishing_job_id,
                        record.provider_media_id,
                        record.failure_code,
                        record.failure_message,
                        json.dumps(record.to_context(), default=str),
                    ),
                )

    def list_by_state(
        self,
        state: FulfillmentLifecycleState | str,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetFulfillmentRecord, ...]:
        value = state.value if isinstance(state, FulfillmentLifecycleState) else str(state)
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_fulfillment_registrations
                    WHERE lifecycle_state = %s
                    ORDER BY updated_at DESC
                    LIMIT %s
                    """,
                    (value, int(limit)),
                )
                rows = cursor.fetchall()
        return tuple(self._record_from_row(row) for row in rows)

    @staticmethod
    def _ensure_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.business_asset_fulfillment_registrations') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.business_asset_fulfillment_registrations. Run forward migrations before using FulfillmentRegistrationRepository."
            )

    @staticmethod
    def _ensure_history_table(connection) -> None:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT to_regclass('public.business_asset_fulfillment_history') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.business_asset_fulfillment_history. Run forward migrations before using FulfillmentRegistrationRepository."
            )

    @staticmethod
    def _params(record: BusinessAssetFulfillmentRecord) -> tuple[Any, ...]:
        return (
            record.fulfillment_id,
            int(record.asset_id),
            record.registration_id,
            record.routing_intent_id,
            record.route.value,
            record.route_owner.value,
            record.provider,
            record.provider_account_id,
            record.publishing_job_id,
            str(record.upload_attempt_id) if record.upload_attempt_id else None,
            record.provider_media_id,
            record.provider_preview_media_id,
            record.provider_full_media_id,
            record.provider_processing_status,
            record.lifecycle_state.value,
            record.media_link,
            record.media_link_verification_state.value,
            record.media_link_submitted_at,
            record.media_link_verified_at,
            record.fulfillment_ready_at,
            record.failure_code,
            record.failure_message,
            int(record.retry_count or 0),
            bool(record.retry_required),
            json.dumps(dict(record.provider_metadata or {}), default=str),
            json.dumps(dict(record.provenance or {}), default=str),
            record.schema_version,
            record.created_at,
        )

    @classmethod
    def _record_from_row(
        cls,
        row: Mapping[str, Any],
    ) -> BusinessAssetFulfillmentRecord:
        return BusinessAssetFulfillmentRecord(
            fulfillment_id=UUID(str(row["fulfillment_id"])),
            asset_id=int(row["asset_id"]),
            registration_id=UUID(str(row["registration_id"])),
            routing_intent_id=UUID(str(row["routing_intent_id"])),
            route=FulfillmentRoute(str(row["route"])),
            route_owner=DestinationRoutingOwner(str(row["route_owner"])),
            provider=str(row["provider"]),
            provider_account_id=row.get("provider_account_id"),
            publishing_job_id=(
                UUID(str(row["publishing_job_id"]))
                if row.get("publishing_job_id")
                else None
            ),
            upload_attempt_id=row.get("upload_attempt_id"),
            provider_media_id=row.get("provider_media_id"),
            provider_preview_media_id=row.get("provider_preview_media_id"),
            provider_full_media_id=row.get("provider_full_media_id"),
            provider_processing_status=row.get("provider_processing_status"),
            lifecycle_state=FulfillmentLifecycleState(str(row["lifecycle_state"])),
            media_link=row.get("media_link"),
            media_link_verification_state=MediaLinkVerificationState(
                str(row.get("media_link_verification_state") or "MISSING")
            ),
            media_link_submitted_at=row.get("media_link_submitted_at"),
            media_link_verified_at=row.get("media_link_verified_at"),
            fulfillment_ready_at=row.get("fulfillment_ready_at"),
            failure_code=row.get("failure_code"),
            failure_message=row.get("failure_message"),
            retry_count=int(row.get("retry_count") or 0),
            retry_required=bool(row.get("retry_required")),
            provider_metadata=cls._mapping(row.get("provider_metadata")),
            provenance=cls._mapping(row.get("provenance")),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            schema_version=str(
                row.get("schema_version") or FULFILLMENT_REGISTRATION_SCHEMA_VERSION
            ),
        )

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
