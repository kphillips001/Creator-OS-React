"""Durable retry state and read-only Commerce Signal projection."""
from __future__ import annotations

import json
from datetime import datetime
from uuid import UUID, uuid4

from app.database import get_db_connection


class CommerceSignalRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def get_or_create_reconciliation(
        self, *, fanvue_account_id: int, creator_profile_id: int,
        provider_event_id: str, source_event_type: str,
        observed_transaction_id: str,
        external_fanvue_user_uuid: UUID | None,
        purchase_type: str | None, expected_amount_minor: int | None,
    ) -> tuple[dict, bool]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commerce_signal_reconciliations (
                           reconciliation_id,fanvue_account_id,creator_profile_id,
                           provider_event_id,source_event_type,
                           observed_transaction_id,external_fanvue_user_uuid,
                           purchase_type,expected_amount_minor,next_attempt_at
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                       ON CONFLICT (fanvue_account_id,provider_event_id)
                       DO NOTHING RETURNING *""",
                    (
                        uuid4(), fanvue_account_id, creator_profile_id,
                        provider_event_id, source_event_type,
                        observed_transaction_id, external_fanvue_user_uuid,
                        purchase_type, expected_amount_minor,
                    ),
                )
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        """SELECT * FROM public.commerce_signal_reconciliations
                           WHERE fanvue_account_id=%s AND provider_event_id=%s""",
                        (fanvue_account_id, provider_event_id),
                    )
                    row = cursor.fetchone()
        return dict(row), created

    def mark_pending(self, reconciliation_id: UUID, *, error: str) -> dict:
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state='PENDING',attempt_count=attempt_count+1,
                   last_error=%s,next_attempt_at=NOW()+INTERVAL '5 minutes',
                   updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (error[:1000], reconciliation_id),
        )

    def mark_verified(
        self, reconciliation_id: UUID, *, transaction_order_id: str,
        external_fanvue_user_uuid: UUID, earnings_record: dict,
    ) -> dict:
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state='VERIFIED',attempt_count=attempt_count+1,
                   canonical_transaction_order_id=%s,
                   external_fanvue_user_uuid=%s,earnings_record=%s::jsonb,
                   verified_at=NOW(),next_attempt_at=NULL,last_error=NULL,
                   updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (
                transaction_order_id, external_fanvue_user_uuid,
                json.dumps(earnings_record), reconciliation_id,
            ),
        )

    def list_due(self, *, limit: int = 25) -> list[dict]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commerce_signal_reconciliations
                       WHERE state='PENDING'
                         AND COALESCE(next_attempt_at,NOW())<=NOW()
                       ORDER BY created_at LIMIT %s""",
                    (limit,),
                )
                return [dict(row) for row in cursor.fetchall()]

    def get_signal(
        self, *, creator_profile_id: int,
        external_fanvue_user_uuid: UUID | None = None,
        telegram_user_id: int | None = None,
    ) -> dict | None:
        if external_fanvue_user_uuid is None and telegram_user_id is None:
            raise ValueError("A buyer UUID or Telegram user is required.")
        filters = ["profile.creator_profile_id=%s"]
        params: list = [creator_profile_id]
        if external_fanvue_user_uuid is not None:
            filters.append("profile.external_fanvue_user_uuid=%s")
            params.append(external_fanvue_user_uuid)
        else:
            filters.append("identity.telegram_user_id=%s")
            params.append(telegram_user_id)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT
                        profile.external_fanvue_user_uuid,
                        identity.telegram_user_id,
                        (identity.id IS NOT NULL) AS identity_resolved,
                        profile.lifetime_gross_minor,profile.purchase_count,
                        profile.last_purchase_at,
                        profile.last_transaction_order_id,
                        intent.purchase_intent_id,intent.commercial_offering_id,
                        intent.status AS current_offer_status,
                        intent.attribution_result,intent.expires_at,
                        reconciliation.state AS reconciliation_state
                    FROM public.customer_commerce_profiles profile
                    LEFT JOIN public.telegram_identity_map identity
                      ON identity.fanvue_account_id=profile.fanvue_account_id
                     AND identity.external_fanvue_user_uuid=
                         profile.external_fanvue_user_uuid
                     AND identity.is_active=TRUE
                    LEFT JOIN LATERAL (
                        SELECT * FROM public.purchase_intents candidate
                        WHERE candidate.creator_profile_id=profile.creator_profile_id
                          AND candidate.fanvue_account_id=profile.fanvue_account_id
                          AND (
                            candidate.external_fanvue_user_uuid=
                              profile.external_fanvue_user_uuid
                            OR candidate.telegram_user_id=identity.telegram_user_id
                          )
                        ORDER BY candidate.created_at DESC LIMIT 1
                    ) intent ON TRUE
                    LEFT JOIN LATERAL (
                        SELECT state FROM public.commerce_signal_reconciliations item
                        WHERE item.creator_profile_id=profile.creator_profile_id
                          AND item.external_fanvue_user_uuid=
                              profile.external_fanvue_user_uuid
                        ORDER BY item.created_at DESC LIMIT 1
                    ) reconciliation ON TRUE
                    WHERE {' AND '.join(filters)}
                    LIMIT 1""",
                    tuple(params),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def _update(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        if row is None:
            raise LookupError("Commerce signal reconciliation was not found.")
        return dict(row)
