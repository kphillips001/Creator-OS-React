"""Persistence boundary for provider-neutral customer entitlements."""

import json
from collections.abc import Callable
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.customer_entitlement import (
    CustomerEntitlement,
    EntitlementSourceType,
)


class CustomerEntitlementRepository:
    def __init__(self, connection_factory: Callable = get_db_connection):
        self._connection_factory = connection_factory

    def create(
        self,
        *,
        product_id: UUID,
        source_type: EntitlementSourceType,
        core_user_id: UUID | None = None,
        legacy_fanvue_account_id: int | None = None,
        legacy_fanvue_user_id: str | None = None,
        commerce_provider: str | None = None,
        provider_transaction_id: str | None = None,
        provider_event_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> CustomerEntitlement:
        query = """
            INSERT INTO public.customer_entitlements (
                id, core_user_id, legacy_fanvue_account_id,
                legacy_fanvue_user_id, product_id, source_type,
                commerce_provider, provider_transaction_id,
                provider_event_id, metadata
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb)
            RETURNING *;
        """
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        uuid4(), core_user_id, legacy_fanvue_account_id,
                        legacy_fanvue_user_id, product_id, source_type.value,
                        commerce_provider, provider_transaction_id,
                        provider_event_id, json.dumps(metadata or {}),
                    ),
                )
                row = cursor.fetchone()
        return CustomerEntitlement.from_row(row)

    def get_by_id(self, entitlement_id: UUID) -> CustomerEntitlement | None:
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.customer_entitlements WHERE id = %s",
                    (entitlement_id,),
                )
                row = cursor.fetchone()
        return CustomerEntitlement.from_row(row) if row else None

    def count_for_product(self, product_id: UUID) -> int:
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT COUNT(*) AS count
                    FROM public.customer_entitlements
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                return cursor.fetchone()["count"]

    def has_any_entitlement(self, product_id: UUID) -> bool:
        return self.count_for_product(product_id) > 0

    def has_active_entitlement_for_legacy_user(
        self,
        *,
        product_id: UUID,
        legacy_fanvue_account_id: int,
        legacy_fanvue_user_id,
    ) -> bool:
        if not legacy_fanvue_account_id or not legacy_fanvue_user_id:
            return False

        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1
                    FROM public.customer_entitlements
                    WHERE product_id = %s
                      AND legacy_fanvue_account_id = %s
                      AND legacy_fanvue_user_id = %s
                      AND status IN ('pending', 'active', 'fulfilled')
                    LIMIT 1
                    """,
                    (
                        product_id,
                        legacy_fanvue_account_id,
                        str(legacy_fanvue_user_id),
                    ),
                )
                return cursor.fetchone() is not None
