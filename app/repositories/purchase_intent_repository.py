"""PostgreSQL persistence for Purchase Intent lifecycle state."""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.purchase_intent import (
    AttributionResult,
    PurchaseIntent,
    PurchaseIntentStatistics,
    PurchaseIntentStatus,
)


class PurchaseIntentRepository:
    _UPDATE_FIELDS = frozenset({
        "status", "telegram_message_id", "presented_at", "clicked_at",
        "abandoned_at", "purchased_at", "provider_transaction_order_id",
        "provider_payment_id", "provider_event_id", "attribution_result",
        "attribution_reason",
        "purchase_acknowledged_at",
    })

    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def create(self, **values: Any) -> PurchaseIntent:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                return self._insert(cursor, values)

    def replace_active(self, **values: Any) -> PurchaseIntent:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT purchase_intent_id
                       FROM public.purchase_intents
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s
                         AND telegram_user_id=%s
                         AND status IN ('CREATED','PRESENTED','CLICKED')
                       FOR UPDATE""",
                    (
                        values["creator_profile_id"],
                        values["fanvue_account_id"],
                        values["telegram_user_id"],
                    ),
                )
                active_ids = [row["purchase_intent_id"] for row in cursor.fetchall()]
                if active_ids:
                    cursor.execute(
                        """UPDATE public.purchase_intents
                           SET status='SUPERSEDED',updated_at=NOW()
                           WHERE purchase_intent_id=ANY(%s)""",
                        (active_ids,),
                    )
                return self._insert(cursor, values)

    def get(
        self, intent_id: UUID, *, creator_profile_id: int | None = None,
    ) -> PurchaseIntent | None:
        params: list[Any] = [intent_id]
        owner_clause = ""
        if creator_profile_id is not None:
            owner_clause = " AND creator_profile_id=%s"
            params.append(creator_profile_id)
        return self._one(
            "SELECT * FROM public.purchase_intents "
            "WHERE purchase_intent_id=%s" + owner_clause,
            tuple(params),
        )

    def update(self, intent_id: UUID, **changes: Any) -> PurchaseIntent:
        invalid = set(changes) - self._UPDATE_FIELDS
        if not changes or invalid:
            raise ValueError(f"Unsupported purchase intent fields: {sorted(invalid)}")
        assignments = []
        params: list[Any] = []
        for field, value in changes.items():
            assignments.append(f"{field}=%s")
            params.append(value.value if isinstance(value, Enum) else value)
        params.append(intent_id)
        return self._update(
            f"""UPDATE public.purchase_intents
                SET {','.join(assignments)},updated_at=NOW()
                WHERE purchase_intent_id=%s RETURNING *""",
            tuple(params),
        )

    def mark_presented(self, intent_id: UUID, *, at: datetime,
                       telegram_message_id: int | None) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.PRESENTED,
                           presented_at=at, telegram_message_id=telegram_message_id)

    def mark_clicked(self, intent_id: UUID, *, at: datetime) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.CLICKED,
                           clicked_at=at)

    def mark_expired(self, intent_id: UUID) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.EXPIRED)

    def mark_abandoned(self, intent_id: UUID, *, at: datetime) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.ABANDONED,
                           abandoned_at=at)

    def mark_purchased(self, intent_id: UUID, *, at: datetime,
                       attribution_reason: str) -> PurchaseIntent:
        return self.update(
            intent_id, status=PurchaseIntentStatus.PURCHASED, purchased_at=at,
            attribution_result=AttributionResult.ATTRIBUTED,
            attribution_reason=attribution_reason,
        )

    def mark_unknown(self, intent_id: UUID, *, reason: str) -> PurchaseIntent:
        return self.update(
            intent_id, status=PurchaseIntentStatus.UNKNOWN,
            attribution_result=AttributionResult.UNKNOWN,
            attribution_reason=reason,
        )

    def mark_superseded(self, intent_id: UUID) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.SUPERSEDED)

    def get_active_for_buyer(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int,
    ) -> PurchaseIntent | None:
        return self._one(
            """SELECT * FROM public.purchase_intents
               WHERE creator_profile_id=%s AND fanvue_account_id=%s
                 AND telegram_user_id=%s
                 AND status IN ('CREATED','PRESENTED','CLICKED')
               ORDER BY created_at DESC LIMIT 1""",
            (creator_profile_id, fanvue_account_id, telegram_user_id),
        )

    def get_latest_for_buyer(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int,
    ) -> PurchaseIntent | None:
        return self._one(
            """SELECT * FROM public.purchase_intents
               WHERE creator_profile_id=%s AND fanvue_account_id=%s
                 AND telegram_user_id=%s
               ORDER BY created_at DESC LIMIT 1""",
            (creator_profile_id, fanvue_account_id, telegram_user_id),
        )

    def get_unacknowledged_purchase(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int,
    ) -> PurchaseIntent | None:
        return self._one(
            """SELECT * FROM public.purchase_intents
               WHERE creator_profile_id=%s AND fanvue_account_id=%s
                 AND telegram_user_id=%s AND status='PURCHASED'
                 AND attribution_result='ATTRIBUTED'
                 AND purchase_acknowledged_at IS NULL
               ORDER BY purchased_at,created_at LIMIT 1""",
            (creator_profile_id, fanvue_account_id, telegram_user_id),
        )

    def mark_purchase_acknowledged(
        self, intent_id: UUID, *, at: datetime,
    ) -> PurchaseIntent:
        return self._update(
            """UPDATE public.purchase_intents
               SET purchase_acknowledged_at=COALESCE(
                       purchase_acknowledged_at,%s
                   ),updated_at=NOW()
               WHERE purchase_intent_id=%s AND status='PURCHASED'
               RETURNING *""",
            (at, intent_id),
        )

    def get_by_transaction(
        self, *, fanvue_account_id: int, provider: str,
        transaction_order_id: str,
    ) -> PurchaseIntent | None:
        return self._one(
            """SELECT * FROM public.purchase_intents
               WHERE fanvue_account_id=%s AND provider=%s
                 AND provider_transaction_order_id=%s""",
            (fanvue_account_id, provider, transaction_order_id),
        )

    def list_attributed_purchased_offering_ids(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID | None,
        telegram_user_id: int | None,
    ) -> frozenset[UUID]:
        identity_filters = []
        identity_params: list[Any] = []
        if external_fanvue_user_uuid is not None:
            identity_filters.append("external_fanvue_user_uuid=%s")
            identity_params.append(external_fanvue_user_uuid)
        elif telegram_user_id is not None:
            identity_filters.append("telegram_user_id=%s")
            identity_params.append(telegram_user_id)
        if not identity_filters:
            return frozenset()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT DISTINCT commercial_offering_id
                        FROM public.purchase_intents
                        WHERE creator_profile_id=%s
                          AND fanvue_account_id=%s
                          AND status='PURCHASED'
                          AND attribution_result='ATTRIBUTED'
                          AND ({' OR '.join(identity_filters)})""",
                    (
                        creator_profile_id, fanvue_account_id,
                        *identity_params,
                    ),
                )
                rows = cursor.fetchall()
        return frozenset(
            UUID(str(row["commercial_offering_id"])) for row in rows
        )

    def list_recommendation_history(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID | None,
        telegram_user_id: int | None, limit: int = 10,
    ) -> tuple[dict[str, Any], ...]:
        """Return one bounded, read-only offer/purchase history projection."""
        identity_clause = None
        identity_value = None
        if external_fanvue_user_uuid is not None:
            identity_clause = "intent.external_fanvue_user_uuid=%s"
            identity_value = external_fanvue_user_uuid
        elif telegram_user_id is not None:
            identity_clause = "intent.telegram_user_id=%s"
            identity_value = int(telegram_user_id)
        if identity_clause is None:
            return ()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT
                        intent.commercial_offering_id,intent.status,
                        intent.presented_at,intent.purchased_at,
                        intent.attribution_result,offering.offering_type,
                        (
                            SELECT membership.photoshoot_session_id
                            FROM public.photoshoot_asset_memberships membership
                            WHERE membership.asset_id=offering.hero_asset_id
                              AND membership.approved=TRUE
                            ORDER BY membership.updated_at DESC LIMIT 1
                        ) AS photoshoot_identifier,
                        (
                            SELECT COALESCE(jsonb_agg(
                                intelligence.profile_data
                                ORDER BY intelligence.asset_id
                            ),'[]'::jsonb)
                            FROM public.commercial_offering_assets member
                            JOIN public.asset_intelligence_profiles intelligence
                              ON intelligence.asset_id=member.asset_id
                             AND intelligence.creator_profile_id=
                                 offering.creator_profile_id
                            WHERE member.offering_id=offering.offering_id
                        ) AS asset_intelligence
                       FROM public.purchase_intents intent
                       JOIN public.commercial_offerings offering
                         ON offering.offering_id=intent.commercial_offering_id
                       WHERE intent.creator_profile_id=%s
                         AND intent.fanvue_account_id=%s
                         AND {identity_clause}
                         AND COALESCE(intent.presented_at,intent.created_at)
                             >= now()-interval '30 days'
                       ORDER BY COALESCE(
                           intent.presented_at,intent.created_at
                       ) DESC,intent.purchase_intent_id
                       LIMIT %s""",
                    (
                        int(creator_profile_id), int(fanvue_account_id),
                        identity_value, max(1, min(10, int(limit))),
                    ),
                )
                return tuple(dict(row) for row in cursor.fetchall())

    def list_candidates(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID | None = None,
    ) -> list[PurchaseIntent]:
        clause = ""
        params: list[Any] = [creator_profile_id, fanvue_account_id]
        if external_fanvue_user_uuid is not None:
            clause = " AND external_fanvue_user_uuid=%s"
            params.append(external_fanvue_user_uuid)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.purchase_intents
                       WHERE creator_profile_id=%s AND fanvue_account_id=%s"""
                    + clause + " ORDER BY created_at DESC",
                    tuple(params),
                )
                return [self._intent(row) for row in cursor.fetchall()]

    def expire_due(self, *, now: datetime) -> list[PurchaseIntent]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.purchase_intents SET
                           status='EXPIRED',updated_at=NOW()
                       WHERE expires_at<=%s
                         AND status IN ('CREATED','PRESENTED','CLICKED')
                       RETURNING *""",
                    (now,),
                )
                return [self._intent(row) for row in cursor.fetchall()]

    def list_page(
        self, *, creator_profile_id: int, search: str | None,
        status: PurchaseIntentStatus | None, page: int, page_size: int,
    ) -> tuple[list[PurchaseIntent], int, int]:
        conditions = ["creator_profile_id=%s"]
        params: list[Any] = [creator_profile_id]
        if status:
            conditions.append("status=%s")
            params.append(status.value)
        if search:
            conditions.append(
                """(telegram_user_id::TEXT ILIKE %s
                    OR commercial_offering_id::TEXT ILIKE %s
                    OR COALESCE(provider_transaction_order_id,'') ILIKE %s
                    OR COALESCE(provider_resource_id,'') ILIKE %s)"""
            )
            term = f"%{search.strip()}%"
            params.extend([term, term, term, term])
        where = " AND ".join(conditions)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS count FROM public.purchase_intents WHERE {where}",
                    tuple(params),
                )
                total = int(cursor.fetchone()["count"])
                total_pages = max(1, (total + page_size - 1) // page_size)
                current_page = min(page, total_pages)
                cursor.execute(
                    f"""SELECT * FROM public.purchase_intents WHERE {where}
                        ORDER BY created_at DESC,purchase_intent_id
                        LIMIT %s OFFSET %s""",
                    (*params, page_size, (current_page - 1) * page_size),
                )
                items = [self._intent(row) for row in cursor.fetchall()]
        return items, total, current_page

    def get_statistics(self, *, creator_profile_id: int) -> PurchaseIntentStatistics:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT COUNT(*)::INTEGER AS total,
                       COUNT(*) FILTER (WHERE status IN
                         ('CREATED','PRESENTED','CLICKED'))::INTEGER AS active,
                       COUNT(*) FILTER (WHERE status='PURCHASED')::INTEGER AS purchased,
                       COUNT(*) FILTER (WHERE status='EXPIRED')::INTEGER AS expired,
                       COUNT(*) FILTER (WHERE status='ABANDONED')::INTEGER AS abandoned,
                       COUNT(*) FILTER (WHERE status='UNKNOWN')::INTEGER AS unknown,
                       COUNT(*) FILTER (WHERE status='SUPERSEDED')::INTEGER AS superseded
                       FROM public.purchase_intents WHERE creator_profile_id=%s""",
                    (creator_profile_id,),
                )
                row = cursor.fetchone()
        return PurchaseIntentStatistics(**{key: int(row[key]) for key in (
            "total", "active", "purchased", "expired", "abandoned",
            "unknown", "superseded",
        )})

    def _insert(self, cursor, values: dict[str, Any]) -> PurchaseIntent:
        intent_id = values.get("purchase_intent_id", uuid4())
        cursor.execute(
            """INSERT INTO public.purchase_intents (
                   purchase_intent_id,creator_profile_id,fanvue_account_id,
                   telegram_identity_mapping_id,telegram_user_id,telegram_chat_id,
                   external_fanvue_user_uuid,commercial_offering_id,
                   commercial_publication_id,provider,provider_resource_id,
                   delivery_url,conversation_id,correlation_id,
                   expected_price_minor,expected_currency,expires_at,created_metadata
               ) SELECT %s,%s,%s,tim.id,tim.telegram_user_id,tim.telegram_chat_id,
                   %s,offering.offering_id,publication.publication_id,%s,%s,%s,
                   %s,%s,%s,%s,%s,%s::jsonb
               FROM public.telegram_identity_map tim
               JOIN public.commercial_offerings offering
                 ON offering.offering_id=%s AND offering.creator_profile_id=%s
               JOIN public.commercial_publications publication
                 ON publication.publication_id=%s
                AND publication.commercial_offering_id=offering.offering_id
                AND publication.provider=%s
               WHERE tim.id=%s AND tim.fanvue_account_id=%s
                 AND tim.telegram_user_id=%s AND tim.telegram_chat_id=%s
                 AND tim.is_active=TRUE
                 AND (%s IS NULL OR tim.external_fanvue_user_uuid=%s)
               RETURNING *""",
            (
                intent_id, values["creator_profile_id"], values["fanvue_account_id"],
                values.get("external_fanvue_user_uuid"), values["provider"],
                values["provider_resource_id"], values["delivery_url"],
                values.get("conversation_id"), values["correlation_id"],
                values["expected_price_minor"], values["expected_currency"],
                values["expires_at"], json.dumps(values.get("created_metadata", {})),
                values["commercial_offering_id"], values["creator_profile_id"],
                values["commercial_publication_id"], values["provider"],
                values["telegram_identity_mapping_id"], values["fanvue_account_id"],
                values["telegram_user_id"], values["telegram_chat_id"],
                values.get("external_fanvue_user_uuid"),
                values.get("external_fanvue_user_uuid"),
            ),
        )
        row = cursor.fetchone()
        if row is None:
            raise ValueError(
                "Purchase Intent identity, offering, or publication is inconsistent."
            )
        return self._intent(row)

    def _one(self, query: str, params: tuple[Any, ...]) -> PurchaseIntent | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return self._intent(row) if row else None

    def _update(self, query: str, params: tuple[Any, ...]) -> PurchaseIntent:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        if row is None:
            raise LookupError("Purchase Intent was not found.")
        return self._intent(row)

    @staticmethod
    def _intent(row: dict[str, Any]) -> PurchaseIntent:
        values = dict(row)
        values["purchase_intent_id"] = UUID(str(values["purchase_intent_id"]))
        for key in ("external_fanvue_user_uuid", "commercial_offering_id",
                    "commercial_publication_id", "correlation_id"):
            if values.get(key) is not None:
                values[key] = UUID(str(values[key]))
        values["status"] = PurchaseIntentStatus(values["status"])
        values["attribution_result"] = AttributionResult(values["attribution_result"])
        values["created_metadata"] = values.get("created_metadata") or {}
        return PurchaseIntent(**values)
