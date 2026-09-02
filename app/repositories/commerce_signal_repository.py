"""Durable retry state and read-only Commerce Signal projection."""
from __future__ import annotations

import json
import hashlib
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
        transaction_family_key: str | None = None,
        reconciliation_mode: str = "LIVE", webhook_event_id: int | None = None,
        payload_sha256: str | None = None,
    ) -> tuple[dict, bool]:
        family_key = transaction_family_key or self.transaction_family_key(
            fanvue_account_id, observed_transaction_id
        )
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commerce_signal_reconciliations (
                           reconciliation_id,fanvue_account_id,creator_profile_id,
                           provider_event_id,source_event_type,
                           observed_transaction_id,external_fanvue_user_uuid,
                           purchase_type,expected_amount_minor,next_attempt_at,
                           transaction_family_key,reconciliation_mode
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),%s,%s)
                       ON CONFLICT (fanvue_account_id,transaction_family_key)
                         WHERE transaction_family_key IS NOT NULL
                       DO NOTHING RETURNING *""",
                    (
                        uuid4(), fanvue_account_id, creator_profile_id,
                        provider_event_id, source_event_type,
                        observed_transaction_id, external_fanvue_user_uuid,
                        purchase_type, expected_amount_minor, family_key,
                        reconciliation_mode,
                    ),
                )
                row = cursor.fetchone()
                created = row is not None
                if row is None:
                    cursor.execute(
                        """SELECT * FROM public.commerce_signal_reconciliations
                           WHERE fanvue_account_id=%s AND transaction_family_key=%s""",
                        (fanvue_account_id, family_key),
                    )
                    row = cursor.fetchone()
                cursor.execute("""INSERT INTO commerce_signal_reconciliation_evidence(
                    evidence_id,reconciliation_id,webhook_event_id,provider_event_id,
                    source_event_type,payload_sha256) VALUES (%s,%s,%s,%s,%s,%s)
                    ON CONFLICT(provider_event_id) DO NOTHING""",
                (uuid4(), row["reconciliation_id"], webhook_event_id,
                     provider_event_id, source_event_type,
                     payload_sha256 or hashlib.sha256(provider_event_id.encode()).hexdigest()))
                evidence_added = cursor.rowcount == 1
                if evidence_added and not created:
                    cursor.execute("""UPDATE public.commerce_signal_reconciliations
                        SET state='PENDING',next_attempt_at=NOW(),last_error=NULL,
                            quarantined_at=NULL,claim_owner=NULL,claimed_at=NULL,
                            lease_expires_at=NULL,updated_at=NOW()
                        WHERE reconciliation_id=%s
                          AND attribution_reason='MISSING_AUTHORITATIVE_CURRENCY'
                        RETURNING *""", (row["reconciliation_id"],))
                    reactivated = cursor.fetchone()
                    if reactivated is not None:
                        row = reactivated
        return dict(row), created

    def get_reconciliation(self, reconciliation_id: UUID) -> dict | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.commerce_signal_reconciliations WHERE reconciliation_id=%s",
                    (reconciliation_id,),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def list_transaction_family_evidence(self, reconciliation_id: UUID) -> list[dict]:
        """Return only durable webhook evidence attached to one transaction family."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT evidence.*,event.event_type,event.payload,
                    event.headers,event.status AS webhook_state,
                    event.fanvue_account_id AS webhook_account_id,
                    event.fanvue_user_id AS webhook_user_id,event.received_at
                    FROM public.commerce_signal_reconciliation_evidence evidence
                    JOIN public.webhook_events event ON event.id=evidence.webhook_event_id
                    WHERE evidence.reconciliation_id=%s
                    ORDER BY evidence.observed_at,evidence.evidence_id""",
                    (reconciliation_id,),
                )
                return [dict(row) for row in cursor.fetchall()]

    def mark_evidence_pending(
        self, reconciliation_id: UUID, *, transaction_order_id: str,
        external_fanvue_user_uuid: UUID, earnings_record: dict, reason: str,
    ) -> dict:
        """Preserve verified provider evidence while keeping settlement retryable."""
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state=CASE WHEN attempt_count+1>=max_attempts THEN 'FAILED' ELSE 'PENDING' END,
                   attempt_count=attempt_count+1,
                   canonical_transaction_order_id=%s,
                   external_fanvue_user_uuid=%s,earnings_record=%s::jsonb,
                   verified_at=COALESCE(verified_at,NOW()),
                   attribution_state='UNKNOWN',attribution_reason=%s,
                   attributed_purchase_intent_id=NULL,last_error=%s,
                   next_attempt_at=CASE WHEN attempt_count+1>=max_attempts
                     THEN NULL ELSE NOW()+INTERVAL '5 minutes' END,
                   quarantined_at=CASE WHEN attempt_count+1>=max_attempts THEN NOW() ELSE NULL END,
                   claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (transaction_order_id, external_fanvue_user_uuid,
             json.dumps(earnings_record), reason, reason, reconciliation_id),
        )

    def mark_evidence_conflict(
        self, reconciliation_id: UUID, *, transaction_order_id: str,
        external_fanvue_user_uuid: UUID, earnings_record: dict, reason: str,
    ) -> dict:
        """Quarantine contradictory provider evidence for manual review."""
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state='FAILED',attempt_count=attempt_count+1,
                   canonical_transaction_order_id=%s,
                   external_fanvue_user_uuid=%s,earnings_record=%s::jsonb,
                   verified_at=COALESCE(verified_at,NOW()),
                   attribution_state='UNKNOWN',attribution_reason=%s,
                   attributed_purchase_intent_id=NULL,last_error=%s,
                   next_attempt_at=NULL,quarantined_at=NOW(),
                   claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (transaction_order_id, external_fanvue_user_uuid,
             json.dumps(earnings_record), reason, reason, reconciliation_id),
        )

    def mark_pending(self, reconciliation_id: UUID, *, error: str) -> dict:
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state=CASE WHEN attempt_count+1>=max_attempts THEN 'FAILED' ELSE 'PENDING' END,
                   attempt_count=attempt_count+1,
                   last_error=%s,next_attempt_at=NOW()+INTERVAL '5 minutes',
                   quarantined_at=CASE WHEN attempt_count+1>=max_attempts THEN NOW() ELSE NULL END,
                   claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                   updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (error[:1000], reconciliation_id),
        )

    def mark_verified(
        self, reconciliation_id: UUID, *, transaction_order_id: str,
        external_fanvue_user_uuid: UUID, earnings_record: dict,
        attribution_state: str | None = None,
        attribution_reason: str | None = None,
        attributed_purchase_intent_id: UUID | None = None,
    ) -> dict:
        return self._update(
            """UPDATE public.commerce_signal_reconciliations SET
                   state='VERIFIED',attempt_count=attempt_count+1,
                   canonical_transaction_order_id=%s,
                   external_fanvue_user_uuid=%s,earnings_record=%s::jsonb,
                   verified_at=NOW(),next_attempt_at=NULL,last_error=NULL,
                   claim_owner=NULL,claimed_at=NULL,lease_expires_at=NULL,
                   attribution_state=%s,attribution_reason=%s,
                   attributed_purchase_intent_id=%s,
                   updated_at=NOW()
               WHERE reconciliation_id=%s RETURNING *""",
            (
                transaction_order_id, external_fanvue_user_uuid,
                json.dumps(earnings_record), attribution_state,
                attribution_reason, attributed_purchase_intent_id,
                reconciliation_id,
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

    def claim_due(self, *, worker_instance_id: str, limit: int = 25,
                  lease_seconds: int = 300) -> list[dict]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""WITH due AS (
                    SELECT reconciliation_id FROM commerce_signal_reconciliations
                    WHERE ((state='PENDING' AND COALESCE(next_attempt_at,NOW())<=NOW())
                       OR (state='FAILED' AND next_attempt_at IS NOT NULL AND next_attempt_at<=NOW())
                       OR (lease_expires_at<NOW() AND claim_owner IS NOT NULL))
                      AND (claim_owner IS NULL OR lease_expires_at<NOW())
                      AND quarantined_at IS NULL
                    ORDER BY next_attempt_at,created_at
                    FOR UPDATE SKIP LOCKED LIMIT %s)
                    UPDATE commerce_signal_reconciliations item SET
                      claim_owner=%s,claimed_at=NOW(),
                      lease_expires_at=NOW()+(%s*INTERVAL '1 second')
                    FROM due WHERE item.reconciliation_id=due.reconciliation_id
                    RETURNING item.*""", (max(1, int(limit)), worker_instance_id,
                                           max(1, int(lease_seconds))))
                return [dict(row) for row in cursor.fetchall()]

    @staticmethod
    def transaction_family_key(fanvue_account_id: int, transaction_id: str) -> str:
        return hashlib.sha256(
            f"{int(fanvue_account_id)}:{str(transaction_id).strip()}".encode()
        ).hexdigest()

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
