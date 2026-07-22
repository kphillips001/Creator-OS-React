"""Persistence for asset-keyed Commerce Registration records."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

from app.database import get_db_connection
from app.models.commerce_registration import (
    COMMERCE_REGISTRATION_SCHEMA_VERSION,
    BusinessAssetLifecycleState,
    BusinessAssetRecord,
    CommerceDestinationStatus,
    CommerceRegistrationStatus,
)


class CommerceRegistrationRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def get_by_asset_id(self, asset_id: int) -> BusinessAssetRecord | None:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT *
                    FROM public.business_asset_registrations
                    WHERE asset_id = %s
                    """,
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def archive(self, asset_id: int) -> BusinessAssetRecord | None:
        """Deactivate commerce participation while preserving its durable record."""
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE public.business_asset_registrations
                    SET is_archived = TRUE,
                        archived_at = COALESCE(archived_at, now()),
                        updated_at = now()
                    WHERE asset_id = %s
                    RETURNING *
                    """,
                    (int(asset_id),),
                )
                row = cursor.fetchone()
        return self._record_from_row(row) if row else None

    def upsert_record(self, record: BusinessAssetRecord) -> BusinessAssetRecord:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO public.business_asset_registrations (
                        registration_id,
                        asset_id,
                        creator_profile_id,
                        approval_status,
                        content_intelligence_status,
                        content_intelligence_ready,
                        commerce_registration_status,
                        business_lifecycle_state,
                        commerce_destination_status,
                        selected_commerce_destination,
                        destination_selected_at,
                        destination_selected_by_profile_id,
                        destination_source_workflow,
                        destination_routing_state,
                        destination_change_note,
                        destination_revision,
                        product_ids,
                        experience_ids,
                        product_draft_ids,
                        delivery_type,
                        delivery_type_source,
                        delivery_type_requires_review,
                        commerce_intelligence_refs,
                        publishing_readiness,
                        fulfillment_readiness,
                        relationship_provenance,
                        registration_provenance,
                        missing_requirements,
                        warnings,
                        error_code,
                        error_message,
                        retry_count,
                        registered_at,
                        last_refreshed_at,
                        schema_version,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb,
                        %s, %s, %s,
                        %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                        %s::jsonb, %s::jsonb,
                        %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), now()
                    )
                    ON CONFLICT (asset_id)
                    DO UPDATE SET
                        creator_profile_id = EXCLUDED.creator_profile_id,
                        approval_status = EXCLUDED.approval_status,
                        content_intelligence_status = EXCLUDED.content_intelligence_status,
                        content_intelligence_ready = EXCLUDED.content_intelligence_ready,
                        commerce_registration_status = EXCLUDED.commerce_registration_status,
                        business_lifecycle_state = EXCLUDED.business_lifecycle_state,
                        commerce_destination_status = EXCLUDED.commerce_destination_status,
                        selected_commerce_destination = EXCLUDED.selected_commerce_destination,
                        destination_selected_at = EXCLUDED.destination_selected_at,
                        destination_selected_by_profile_id = EXCLUDED.destination_selected_by_profile_id,
                        destination_source_workflow = EXCLUDED.destination_source_workflow,
                        destination_routing_state = EXCLUDED.destination_routing_state,
                        destination_change_note = EXCLUDED.destination_change_note,
                        destination_revision = EXCLUDED.destination_revision,
                        product_ids = EXCLUDED.product_ids,
                        experience_ids = EXCLUDED.experience_ids,
                        product_draft_ids = EXCLUDED.product_draft_ids,
                        delivery_type = EXCLUDED.delivery_type,
                        delivery_type_source = EXCLUDED.delivery_type_source,
                        delivery_type_requires_review = EXCLUDED.delivery_type_requires_review,
                        commerce_intelligence_refs = EXCLUDED.commerce_intelligence_refs,
                        publishing_readiness = EXCLUDED.publishing_readiness,
                        fulfillment_readiness = EXCLUDED.fulfillment_readiness,
                        relationship_provenance = EXCLUDED.relationship_provenance,
                        registration_provenance = EXCLUDED.registration_provenance,
                        missing_requirements = EXCLUDED.missing_requirements,
                        warnings = EXCLUDED.warnings,
                        error_code = EXCLUDED.error_code,
                        error_message = EXCLUDED.error_message,
                        retry_count = EXCLUDED.retry_count,
                        registered_at = COALESCE(
                            public.business_asset_registrations.registered_at,
                            EXCLUDED.registered_at
                        ),
                        last_refreshed_at = EXCLUDED.last_refreshed_at,
                        schema_version = EXCLUDED.schema_version,
                        updated_at = now()
                    RETURNING *
                    """,
                    (
                        record.registration_id,
                        int(record.asset_id),
                        record.creator_profile_id,
                        record.approval_status,
                        record.content_intelligence_status,
                        bool(record.content_intelligence_ready),
                        record.commerce_registration_status.value,
                        record.business_lifecycle_state.value,
                        record.commerce_destination_status.value,
                        record.selected_commerce_destination,
                        record.destination_selected_at,
                        record.destination_selected_by_profile_id,
                        record.destination_source_workflow,
                        record.destination_routing_state,
                        record.destination_change_note,
                        int(record.destination_revision or 0),
                        json.dumps(list(record.product_ids), default=str),
                        json.dumps(list(record.experience_ids), default=str),
                        json.dumps(list(record.product_draft_ids), default=str),
                        record.delivery_type,
                        record.delivery_type_source,
                        bool(record.delivery_type_requires_review),
                        json.dumps(dict(record.commerce_intelligence_refs), default=str),
                        json.dumps(dict(record.publishing_readiness), default=str),
                        json.dumps(dict(record.fulfillment_readiness), default=str),
                        json.dumps(dict(record.relationship_provenance), default=str),
                        json.dumps(dict(record.registration_provenance), default=str),
                        json.dumps(list(record.missing_requirements), default=str),
                        json.dumps(list(record.warnings), default=str),
                        record.error_code,
                        record.error_message,
                        int(record.retry_count or 0),
                        record.registered_at,
                        record.last_refreshed_at,
                        record.schema_version,
                        record.created_at,
                    ),
                )
                row = cursor.fetchone()
        return self._record_from_row(row)

    def list_registered(self, *, limit: int = 100) -> tuple[BusinessAssetRecord, ...]:
        return self._list_by_filter(
            "commerce_registration_status = %s AND is_archived = FALSE",
            (CommerceRegistrationStatus.REGISTERED.value,),
            limit=limit,
        )

    def list_active(self, *, limit: int = 100) -> tuple[BusinessAssetRecord, ...]:
        """Return every non-archived Business Asset regardless of workflow stage."""
        return self._list_by_filter("is_archived = FALSE", (), limit=limit)

    def list_archived(self, *, limit: int = 100) -> tuple[BusinessAssetRecord, ...]:
        return self._list_by_filter("is_archived = TRUE", (), limit=limit)

    def list_awaiting_destination(
        self, *, limit: int = 100
    ) -> tuple[BusinessAssetRecord, ...]:
        return self._list_by_filter(
            "commerce_destination_status = %s AND is_archived = FALSE",
            (CommerceDestinationStatus.AWAITING_DESTINATION.value,),
            limit=limit,
        )

    def list_by_selected_destination(
        self,
        destination: str,
        *,
        limit: int = 100,
    ) -> tuple[BusinessAssetRecord, ...]:
        return self._list_by_filter(
            "selected_commerce_destination = %s AND is_archived = FALSE",
            (str(destination),),
            limit=limit,
        )

    def list_blocked_by_incomplete_intelligence(
        self, *, limit: int = 100
    ) -> tuple[BusinessAssetRecord, ...]:
        return self._list_by_filter(
            "business_lifecycle_state = %s AND is_archived = FALSE",
            (BusinessAssetLifecycleState.INTELLIGENCE_PENDING.value,),
            limit=limit,
        )

    def _list_by_filter(
        self,
        where: str,
        params: tuple[Any, ...],
        *,
        limit: int,
    ) -> tuple[BusinessAssetRecord, ...]:
        with self._connection_factory() as conn:
            self._ensure_table(conn)
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT *
                    FROM public.business_asset_registrations
                    WHERE ({where})
                      AND NOT EXISTS (
                          SELECT 1 FROM public.photoshoot_asset_memberships photoshoot_member
                          WHERE photoshoot_member.asset_id = public.business_asset_registrations.asset_id
                            AND photoshoot_member.approved = TRUE
                      )
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
                "SELECT to_regclass('public.business_asset_registrations') AS table_ref;"
            )
            row = cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError(
                "Missing public.business_asset_registrations. Run forward migrations before using CommerceRegistrationRepository."
            )

    @classmethod
    def _record_from_row(cls, row: Mapping[str, Any]) -> BusinessAssetRecord:
        return BusinessAssetRecord(
            registration_id=UUID(str(row["registration_id"])),
            asset_id=int(row["asset_id"]),
            creator_profile_id=row.get("creator_profile_id"),
            approval_status=str(row.get("approval_status") or "unknown"),
            content_intelligence_status=str(
                row.get("content_intelligence_status") or "UNKNOWN"
            ),
            content_intelligence_ready=bool(row.get("content_intelligence_ready")),
            commerce_registration_status=cls._registration_status(
                row.get("commerce_registration_status")
            ),
            business_lifecycle_state=cls._lifecycle_state(
                row.get("business_lifecycle_state")
            ),
            commerce_destination_status=cls._destination_status(
                row.get("commerce_destination_status")
            ),
            selected_commerce_destination=row.get("selected_commerce_destination"),
            destination_selected_at=cls._datetime(row.get("destination_selected_at")),
            destination_selected_by_profile_id=row.get(
                "destination_selected_by_profile_id"
            ),
            destination_source_workflow=row.get("destination_source_workflow"),
            destination_routing_state=row.get("destination_routing_state"),
            destination_change_note=row.get("destination_change_note"),
            destination_revision=int(row.get("destination_revision") or 0),
            product_ids=cls._tuple(row.get("product_ids")),
            experience_ids=cls._tuple(row.get("experience_ids")),
            product_draft_ids=cls._tuple(row.get("product_draft_ids")),
            delivery_type=row.get("delivery_type"),
            delivery_type_source=row.get("delivery_type_source"),
            delivery_type_requires_review=bool(
                row.get("delivery_type_requires_review")
            ),
            commerce_intelligence_refs=cls._mapping(
                row.get("commerce_intelligence_refs")
            ),
            publishing_readiness=cls._mapping(row.get("publishing_readiness")),
            fulfillment_readiness=cls._mapping(row.get("fulfillment_readiness")),
            relationship_provenance=cls._mapping(row.get("relationship_provenance")),
            registration_provenance=cls._mapping(row.get("registration_provenance")),
            missing_requirements=cls._tuple(row.get("missing_requirements")),
            warnings=cls._tuple(row.get("warnings")),
            error_code=row.get("error_code"),
            error_message=row.get("error_message"),
            retry_count=int(row.get("retry_count") or 0),
            registered_at=cls._datetime(row.get("registered_at")),
            last_refreshed_at=cls._datetime(row.get("last_refreshed_at")),
            created_at=cls._datetime(row.get("created_at")),
            updated_at=cls._datetime(row.get("updated_at")),
            is_archived=bool(row.get("is_archived", False)),
            archived_at=cls._datetime(row.get("archived_at")),
            schema_version=str(
                row.get("schema_version") or COMMERCE_REGISTRATION_SCHEMA_VERSION
            ),
        )

    @staticmethod
    def _registration_status(value: Any) -> CommerceRegistrationStatus:
        try:
            return CommerceRegistrationStatus(str(value))
        except Exception:
            return CommerceRegistrationStatus.PENDING

    @staticmethod
    def _lifecycle_state(value: Any) -> BusinessAssetLifecycleState:
        try:
            return BusinessAssetLifecycleState(str(value))
        except Exception:
            return BusinessAssetLifecycleState.APPROVED

    @staticmethod
    def _destination_status(value: Any) -> CommerceDestinationStatus:
        try:
            return CommerceDestinationStatus(str(value))
        except Exception:
            return CommerceDestinationStatus.NOT_READY

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
