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
from app.repositories.advisory_lock_key import deterministic_bigint_advisory_lock_key


_PURCHASE_INTENT_LOCK_DOMAIN = "creator-os:purchase-intent:replace-active:v1"


def purchase_intent_advisory_lock_key(
    *, fanvue_account_id: int, telegram_user_id: int,
) -> int:
    """Return a stable signed BIGINT key for one active-intent buyer scope.

    PostgreSQL's two-key advisory-lock overload accepts two signed 32-bit
    integers, which cannot represent Telegram's 64-bit numeric identities.
    Interpret the first eight SHA-256 bytes as a signed two's-complement value
    so every process derives a value accepted by the one-key BIGINT overload.
    """
    return deterministic_bigint_advisory_lock_key(
        domain=_PURCHASE_INTENT_LOCK_DOMAIN,
        components=(
            ("fanvue_account_id", fanvue_account_id),
            ("telegram_user_id", telegram_user_id),
        ),
    )


class PurchaseIntentRepository:
    _UPDATE_FIELDS = frozenset({
        "status", "telegram_message_id", "presented_at", "clicked_at",
        "abandoned_at", "purchased_at", "provider_transaction_order_id",
        "provider_payment_id", "provider_event_id", "attribution_result",
        "attribution_reason",
        "purchase_acknowledged_at",
        "telegram_identity_mapping_id", "external_fanvue_user_uuid",
        "actual_charged_price_minor", "identity_bootstrap_mode",
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
                lock_key = purchase_intent_advisory_lock_key(
                    fanvue_account_id=int(values["fanvue_account_id"]),
                    telegram_user_id=int(values["telegram_user_id"]),
                )
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s::bigint)",
                    (lock_key,),
                )
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

    def get_by_correlation(self, correlation_id: UUID) -> PurchaseIntent | None:
        return self._one(
            "SELECT * FROM public.purchase_intents WHERE correlation_id=%s",
            (correlation_id,),
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
        result = self._one(
            """UPDATE public.purchase_intents SET
                   status=CASE WHEN status='PRESENTED' THEN 'CLICKED' ELSE status END,
                   clicked_at=CASE
                       WHEN status='PRESENTED' THEN COALESCE(clicked_at,%s)
                       ELSE clicked_at
                   END,
                   updated_at=CASE WHEN status='PRESENTED' THEN NOW() ELSE updated_at END
               WHERE purchase_intent_id=%s
                 AND status IN ('PRESENTED','CLICKED','PURCHASED')
               RETURNING *""",
            (at, intent_id),
        )
        if result is None:
            raise ValueError("Purchase Intent is not eligible for click recording.")
        return result

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

    def clear_unsettled_actual_charged_price(
        self, intent_id: UUID, *, expected_telegram_user_id: int,
    ) -> PurchaseIntent:
        """Clear a legacy pre-purchase target-price write, fail closed.

        This is intentionally narrower than ``update``: it succeeds only for a
        clicked, wholly unsettled fingerprint-bootstrap intent whose active
        reservation and provisional Session still contain no purchase evidence.
        Provider-confirmed settlement remains the only normal writer of the
        actual charged amount.
        """
        result = self._one(
            """UPDATE public.purchase_intents intent
               SET actual_charged_price_minor=NULL,updated_at=NOW()
               WHERE intent.purchase_intent_id=%s
                 AND intent.telegram_user_id=%s
                 AND intent.status='CLICKED'
                 AND intent.actual_charged_price_minor IS NOT NULL
                 AND intent.purchased_at IS NULL
                 AND intent.provider_transaction_order_id IS NULL
                 AND intent.provider_payment_id IS NULL
                 AND intent.provider_event_id IS NULL
                 AND intent.purchase_acknowledged_at IS NULL
                 AND intent.attribution_result='PENDING'
                 AND intent.external_fanvue_user_uuid IS NULL
                 AND EXISTS (
                     SELECT 1
                     FROM public.fanvue_fingerprint_reservations reservation
                     WHERE reservation.purchase_intent_id=intent.purchase_intent_id
                       AND reservation.state='ACTIVE'
                       AND reservation.purchased_at IS NULL
                       AND reservation.provider_transaction_reference IS NULL
                 )
                 AND EXISTS (
                     SELECT 1
                     FROM public.fanvue_runtime_media_links runtime
                     WHERE runtime.purchase_intent_id=intent.purchase_intent_id
                       AND runtime.state='ACTIVE'
                       AND runtime.provider_media_link_uuid IS NOT NULL
                 )
                 AND EXISTS (
                     SELECT 1
                     FROM public.telegram_provisional_sales_sessions session
                     WHERE session.first_purchase_intent_id=intent.purchase_intent_id
                       AND session.state='AWAITING_PAYMENT'
                       AND session.actual_fingerprint_price_minor IS NULL
                       AND session.first_purchase_recorded_at IS NULL
                       AND session.mapped_sales_session_id IS NULL
                 )
                 AND NOT EXISTS (
                     SELECT 1
                     FROM public.commerce_signal_reconciliations reconciliation
                     WHERE reconciliation.attributed_purchase_intent_id=
                           intent.purchase_intent_id
                 )
               RETURNING intent.*""",
            (intent_id, expected_telegram_user_id),
        )
        if result is None:
            current = self.get(intent_id)
            if current is not None and current.actual_charged_price_minor is None:
                return current
            raise ValueError(
                "Purchase Intent is not eligible for pre-purchase price reconciliation."
            )
        return result

    def mark_unknown(self, intent_id: UUID, *, reason: str) -> PurchaseIntent:
        return self.update(
            intent_id, status=PurchaseIntentStatus.UNKNOWN,
            attribution_result=AttributionResult.UNKNOWN,
            attribution_reason=reason,
        )

    def mark_superseded(self, intent_id: UUID) -> PurchaseIntent:
        return self.update(intent_id, status=PurchaseIntentStatus.SUPERSEDED)

    def close_administratively(
        self, intent_id: UUID, *, reason_code: str,
        expected_telegram_user_id: int, expected_telegram_chat_id: int,
        at: datetime,
    ) -> PurchaseIntent:
        """Atomically retire one controlled offer and revoke its Unlock grant."""
        reason = str(reason_code or "").strip()
        if not reason:
            raise ValueError("An administrative close reason is required.")
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.purchase_intents "
                    "WHERE purchase_intent_id=%s FOR UPDATE", (intent_id,),
                )
                row = cursor.fetchone()
                if row is None:
                    raise LookupError("Purchase Intent was not found.")
                if (
                    int(row["telegram_user_id"]) != int(expected_telegram_user_id)
                    or int(row["telegram_chat_id"]) != int(expected_telegram_chat_id)
                ):
                    raise PermissionError("Administrative close identity mismatch.")
                status = str(row["status"])
                cursor.execute(
                    "SELECT * FROM public.telegram_unlock_grants "
                    "WHERE purchase_intent_id=%s FOR UPDATE", (intent_id,),
                )
                grant = cursor.fetchone()
                if status == PurchaseIntentStatus.ADMIN_CLOSED.value:
                    if row.get("administrative_close_reason") != reason:
                        raise ValueError("Purchase Intent has another administrative disposition.")
                    if grant is not None and grant["state"] != "REVOKED":
                        raise RuntimeError("Administrative close is incomplete.")
                    return self._intent(row)
                if status not in {
                    PurchaseIntentStatus.CREATED.value,
                    PurchaseIntentStatus.PRESENTED.value,
                }:
                    raise ValueError(
                        f"Invalid Purchase Intent transition: {status} -> ADMIN_CLOSED."
                    )
                settlement_fields = (
                    "purchased_at", "purchase_acknowledged_at",
                    "provider_transaction_order_id", "provider_payment_id",
                    "provider_event_id",
                )
                if any(row.get(field) is not None for field in settlement_fields):
                    raise ValueError("Purchase or settlement evidence blocks administrative close.")
                if str(row.get("attribution_result") or "") != "PENDING":
                    raise ValueError("Attribution state blocks administrative close.")
                cursor.execute(
                    """SELECT count(*) AS n FROM public.fanvue_fingerprint_reservations
                       WHERE purchase_intent_id=%s AND (
                         state IN ('PURCHASED','UNCERTAIN') OR purchased_at IS NOT NULL
                         OR provider_transaction_reference IS NOT NULL)""", (intent_id,),
                )
                if int(cursor.fetchone()["n"]):
                    raise ValueError("Fingerprint purchase or uncertainty blocks administrative close.")
                cursor.execute(
                    """SELECT count(*) AS n FROM public.commerce_signal_reconciliations
                       WHERE attributed_purchase_intent_id=%s""", (intent_id,),
                )
                if int(cursor.fetchone()["n"]):
                    raise ValueError("Commerce reconciliation blocks administrative close.")
                if grant is not None and grant["state"] not in {"ACTIVE", "REVOKED"}:
                    raise ValueError("Unlock grant state blocks administrative close.")
                cursor.execute(
                    """UPDATE public.purchase_intents
                       SET status='ADMIN_CLOSED',admin_closed_at=%s,
                           administrative_close_reason=%s,updated_at=NOW()
                       WHERE purchase_intent_id=%s RETURNING *""",
                    (at, reason, intent_id),
                )
                closed = cursor.fetchone()
                cursor.execute(
                    """UPDATE public.telegram_provisional_sales_sessions
                       SET state='ADMIN_CLOSED',administratively_closed_at=%s,
                           administrative_close_reason=%s,updated_at=NOW()
                       WHERE first_purchase_intent_id=%s
                         AND state IN ('ACTIVE','OFFERING','AWAITING_PAYMENT')""",
                    (at, reason, intent_id),
                )
                if grant is not None and grant["state"] == "ACTIVE":
                    cursor.execute(
                        """UPDATE public.telegram_unlock_grants
                           SET state='REVOKED',revoked_at=%s,
                               audit_metadata=audit_metadata || jsonb_build_object(
                                 'administrativeCloseReason',%s::text,
                                 'administrativelyClosedAt',%s::text)
                           WHERE unlock_grant_id=%s AND state='ACTIVE'
                           RETURNING unlock_grant_id""",
                        (at, reason, at, grant["unlock_grant_id"]),
                    )
                    if cursor.fetchone() is None:
                        raise RuntimeError("Unlock grant revocation failed.")
                return self._intent(closed)

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

    def get_customer_opportunity_evidence(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        telegram_user_id: int,
    ) -> dict[str, Any]:
        """Project customer-visible paid opportunities from durable lifecycle truth.

        ``presented_at`` is written only after confirmed commercial delivery, so
        CREATED-only intents and internal offer considerations are excluded.
        """
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT
                    COUNT(*) FILTER (WHERE presented_at IS NOT NULL)::INTEGER
                        AS presented_opportunity_count,
                    COUNT(*) FILTER (WHERE presented_at IS NOT NULL AND status IN
                        ('EXPIRED','ABANDONED','SUPERSEDED','ADMIN_CLOSED'))::INTEGER
                        AS failed_nonconverted_opportunity_count,
                    COUNT(*) FILTER (WHERE presented_at IS NOT NULL
                        AND status='PURCHASED')::INTEGER
                        AS converted_opportunity_count,
                    BOOL_OR(presented_at IS NOT NULL AND status IN
                        ('PRESENTED','CLICKED','UNKNOWN'))
                        AS active_unresolved_opportunity
                   FROM public.purchase_intents
                   WHERE creator_profile_id=%s AND fanvue_account_id=%s
                     AND telegram_user_id=%s""",
                (creator_profile_id, fanvue_account_id, telegram_user_id),
            )
            row = dict(cursor.fetchone() or {})
        return {
            "commercial_opportunity_evidence_source": (
                "PURCHASE_INTENT_PRESENTATION_LIFECYCLE"
            ),
            "presented_opportunity_count": int(
                row.get("presented_opportunity_count") or 0
            ),
            "failed_nonconverted_opportunity_count": int(
                row.get("failed_nonconverted_opportunity_count") or 0
            ),
            "converted_opportunity_count": int(
                row.get("converted_opportunity_count") or 0
            ),
            "active_unresolved_opportunity": bool(
                row.get("active_unresolved_opportunity")
            ),
        }

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

    def get_attribution_contexts(
        self, intent_ids: list[UUID] | tuple[UUID, ...],
    ) -> dict[UUID, dict[str, Any]]:
        """Return authoritative product identity used by attribution policy."""
        if not intent_ids:
            return {}
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT intent.purchase_intent_id,
                              offering.offering_type,
                              offering.source_photoshoot_deliverable_id,
                              deliverable.selling_mode,
                              deliverable.bundle_sales_channel,
                              publication.external_product_id
                       FROM public.purchase_intents intent
                       JOIN public.commercial_offerings offering
                         ON offering.offering_id=intent.commercial_offering_id
                       JOIN public.commercial_publications publication
                         ON publication.publication_id=
                            intent.commercial_publication_id
                        AND publication.commercial_offering_id=
                            offering.offering_id
                       LEFT JOIN public.photoshoot_commerce_deliverables
                            deliverable
                         ON deliverable.deliverable_id=
                            offering.source_photoshoot_deliverable_id
                       WHERE intent.purchase_intent_id=ANY(%s)""",
                    (list(intent_ids),),
                )
                rows = cursor.fetchall()
        return {
            UUID(str(row["purchase_intent_id"])): dict(row) for row in rows
        }

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
        if values.get("telegram_identity_mapping_id") is None:
            cursor.execute(
                """INSERT INTO public.purchase_intents (
                       purchase_intent_id,creator_profile_id,fanvue_account_id,
                       telegram_identity_mapping_id,telegram_user_id,telegram_chat_id,
                       external_fanvue_user_uuid,commercial_offering_id,
                       commercial_publication_id,provider,provider_resource_id,
                       delivery_url,conversation_id,correlation_id,
                       expected_price_minor,expected_currency,expires_at,created_metadata,
                       configured_base_price_minor,identity_bootstrap_mode
                   ) SELECT %s,%s,%s,NULL,%s,%s,NULL,
                       offering.offering_id,publication.publication_id,%s,%s,%s,
                       %s,%s,%s,%s,%s,%s::jsonb,%s,'PRIVATE_CHAT_FINGERPRINT'
                   FROM public.commercial_offerings offering
                   JOIN public.commercial_publications publication
                     ON publication.publication_id=%s
                    AND publication.commercial_offering_id=offering.offering_id
                    AND publication.provider=%s
                   WHERE offering.offering_id=%s
                     AND offering.creator_profile_id=%s
                   RETURNING *""",
                (
                    intent_id, values["creator_profile_id"], values["fanvue_account_id"],
                    values["telegram_user_id"], values["telegram_chat_id"],
                    values["provider"], values["provider_resource_id"],
                    values["delivery_url"], values.get("conversation_id"),
                    values["correlation_id"], values["expected_price_minor"],
                    values["expected_currency"], values["expires_at"],
                    json.dumps(values.get("created_metadata", {})),
                    values["expected_price_minor"],
                    values["commercial_publication_id"], values["provider"],
                    values["commercial_offering_id"], values["creator_profile_id"],
                ),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(
                    "Purchase Intent offering or publication is inconsistent."
                )
            return self._intent(row)
        cursor.execute(
            """INSERT INTO public.purchase_intents (
                   purchase_intent_id,creator_profile_id,fanvue_account_id,
                   telegram_identity_mapping_id,telegram_user_id,telegram_chat_id,
                   external_fanvue_user_uuid,commercial_offering_id,
                   commercial_publication_id,provider,provider_resource_id,
                   delivery_url,conversation_id,correlation_id,
                   expected_price_minor,expected_currency,expires_at,created_metadata,
                   configured_base_price_minor,identity_bootstrap_mode
               ) SELECT %s,%s,%s,tim.id,tim.telegram_user_id,tim.telegram_chat_id,
                   %s,offering.offering_id,publication.publication_id,%s,%s,%s,
                   %s,%s,%s,%s,%s,%s::jsonb,%s,'NONE'
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
                values["expected_price_minor"],
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
