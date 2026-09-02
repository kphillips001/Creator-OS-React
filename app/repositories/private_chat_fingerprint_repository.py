"""Transactional persistence for private-chat Unlock bootstrap resources."""
from __future__ import annotations

import hashlib
import json
from contextlib import contextmanager
from datetime import datetime
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.private_chat_fingerprint import (
    FingerprintReservation,
    FingerprintReservationState,
    RuntimeMediaLink,
    RuntimeMediaLinkState,
    UnlockGrant,
)
from app.services.fingerprint_price_allocator import FingerprintPoolExhaustedError


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class PrivateChatFingerprintRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    @contextmanager
    def serialize_intent(self, purchase_intent_id: UUID):
        """Hold a PostgreSQL session lock for one complete Unlock lifecycle."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_lock(hashtextextended(%s,0))",
                    (f"private-chat-unlock:{purchase_intent_id}",),
                )
                try:
                    yield
                finally:
                    cursor.execute(
                        "SELECT pg_advisory_unlock(hashtextextended(%s,0))",
                        (f"private-chat-unlock:{purchase_intent_id}",),
                    )

    def get_grant_for_intent(self, purchase_intent_id: UUID) -> UnlockGrant | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.telegram_unlock_grants WHERE purchase_intent_id=%s",
                    (purchase_intent_id,),
                )
                row = cursor.fetchone()
        return self._grant(row) if row else None

    def create_grant(
        self, *, grant_id: UUID, token: str, intent, audit_metadata=None,
    ) -> UnlockGrant:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.telegram_unlock_grants (
                           unlock_grant_id,token_hash,purchase_intent_id,
                           telegram_user_id,telegram_chat_id,commercial_offering_id,
                           commercial_publication_id,fanvue_account_id,currency,audit_metadata)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
                       ON CONFLICT (purchase_intent_id) DO UPDATE SET
                           audit_metadata=telegram_unlock_grants.audit_metadata
                       RETURNING *""",
                    (grant_id, token_digest(token), intent.purchase_intent_id,
                     intent.telegram_user_id, intent.telegram_chat_id,
                     intent.commercial_offering_id, intent.commercial_publication_id,
                     intent.fanvue_account_id, intent.expected_currency,
                     json.dumps(audit_metadata or {})),
                )
                return self._grant(cursor.fetchone())

    def resolve_grant(self, token: str) -> UnlockGrant | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.telegram_unlock_grants
                       SET last_used_at=NOW(),use_count=use_count+1
                       WHERE token_hash=%s AND state='ACTIVE'
                       RETURNING *""",
                    (token_digest(token),),
                )
                row = cursor.fetchone()
        return self._grant(row) if row else None

    def assign_public_alias(
        self, *, grant_id: UUID, alias_hash: str, generation: int,
    ) -> UnlockGrant | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.telegram_unlock_grants
                       SET public_alias_hash=%s,public_alias_generation=%s
                       WHERE unlock_grant_id=%s AND public_alias_hash IS NULL
                       RETURNING *""",
                    (alias_hash, generation, grant_id),
                )
                row = cursor.fetchone()
        return self._grant(row) if row else None

    def resolve_grant_by_alias(self, alias: str) -> UnlockGrant | None:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.telegram_unlock_grants
                       SET last_used_at=NOW(),use_count=use_count+1
                       WHERE public_alias_hash=%s AND state='ACTIVE'
                       RETURNING *""",
                    (token_digest(alias),),
                )
                row = cursor.fetchone()
        return self._grant(row) if row else None

    def reserve_price(
        self, *, intent, canonical_prices, candidate_prices,
    ) -> FingerprintReservation:
        """Serialize an account/currency pool and permanently claim one price."""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT pg_advisory_xact_lock(%s,hashtext(%s))",
                    (int(intent.fanvue_account_id), intent.expected_currency),
                )
                cursor.execute(
                    """SELECT * FROM public.fanvue_fingerprint_reservations
                       WHERE purchase_intent_id=%s
                       ORDER BY created_at DESC LIMIT 1""",
                    (intent.purchase_intent_id,),
                )
                existing = cursor.fetchone()
                if existing and existing["state"] in {"RESERVED", "ACTIVE", "UNCERTAIN"}:
                    return self._reservation(existing)
                cursor.execute(
                    """SELECT exact_price_minor
                       FROM public.fanvue_fingerprint_reservations
                       WHERE fanvue_account_id=%s AND currency=%s""",
                    (intent.fanvue_account_id, intent.expected_currency),
                )
                excluded = {int(row["exact_price_minor"]) for row in cursor.fetchall()}
                excluded.update(int(value) for value in canonical_prices)
                selected = next((price for price in candidate_prices if price not in excluded), None)
                if selected is None:
                    raise FingerprintPoolExhaustedError(
                        "Fingerprint capacity exhausted for this account/currency/price band."
                    )
                cursor.execute(
                    """INSERT INTO public.fanvue_fingerprint_reservations (
                           fingerprint_reservation_id,fanvue_account_id,currency,
                           exact_price_minor,configured_base_price_minor,
                           purchase_intent_id,telegram_user_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (uuid4(), intent.fanvue_account_id, intent.expected_currency,
                     selected, intent.expected_price_minor,
                     intent.purchase_intent_id, intent.telegram_user_id),
                )
                return self._reservation(cursor.fetchone())

    def get_live_link(self, purchase_intent_id: UUID, *, now: datetime):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.fanvue_runtime_media_links
                       WHERE purchase_intent_id=%s AND state='ACTIVE' AND expires_at>%s
                       ORDER BY created_at DESC LIMIT 1""",
                    (purchase_intent_id, now),
                )
                row = cursor.fetchone()
        return self._runtime_link(row) if row else None

    def get_reservation_for_intent(self, purchase_intent_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.fanvue_fingerprint_reservations
                       WHERE purchase_intent_id=%s ORDER BY created_at DESC LIMIT 1""",
                    (purchase_intent_id,),
                )
                row = cursor.fetchone()
        return self._reservation(row) if row else None

    def get_runtime_link_for_intent(self, purchase_intent_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.fanvue_runtime_media_links
                       WHERE purchase_intent_id=%s ORDER BY created_at DESC LIMIT 1""",
                    (purchase_intent_id,),
                )
                row = cursor.fetchone()
        return self._runtime_link(row) if row else None

    def retire_expired_for_intent(self, purchase_intent_id: UUID, *, now: datetime):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.fanvue_runtime_media_links
                    SET state='EXPIRED',last_attempt_at=NOW()
                    WHERE purchase_intent_id=%s AND state='ACTIVE' AND expires_at<=%s
                    RETURNING fingerprint_reservation_id""", (purchase_intent_id, now))
                rows = cursor.fetchall()
                for row in rows:
                    cursor.execute("""UPDATE public.fanvue_fingerprint_reservations
                        SET state='RETIRED',retired_at=COALESCE(retired_at,NOW())
                        WHERE fingerprint_reservation_id=%s AND state='ACTIVE'""",
                        (row["fingerprint_reservation_id"],))
        return len(rows)

    def prepare_runtime_link(self, *, intent, reservation, expires_at):
        operation_key = uuid4()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.fanvue_runtime_media_links (
                           runtime_media_link_id,purchase_intent_id,
                           fingerprint_reservation_id,creation_operation_key,expires_at)
                       VALUES (%s,%s,%s,%s,%s)
                       ON CONFLICT (fingerprint_reservation_id) DO UPDATE SET
                           fingerprint_reservation_id=EXCLUDED.fingerprint_reservation_id
                       RETURNING *""",
                    (uuid4(), intent.purchase_intent_id,
                     reservation.fingerprint_reservation_id, operation_key, expires_at),
                )
                link = cursor.fetchone()
                cursor.execute(
                    """INSERT INTO public.fanvue_runtime_media_link_operations (
                           operation_id,runtime_media_link_id,operation_type,idempotency_key)
                       VALUES (%s,%s,'CREATE',%s)
                       ON CONFLICT (idempotency_key) DO NOTHING""",
                    (uuid4(), link["runtime_media_link_id"],
                     link["creation_operation_key"]),
                )
                return self._runtime_link(link)

    def mark_creating(self, runtime_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_links SET
                           state='CREATING',attempt_count=attempt_count+1,last_attempt_at=NOW()
                       WHERE runtime_media_link_id=%s
                         AND state IN ('PENDING_CREATE','CREATE_FAILED','UNCERTAIN') RETURNING *""",
                    (runtime_id,),
                )
                row = cursor.fetchone()
        return self._runtime_link(row) if row else None

    def activate(self, runtime_id: UUID, *, provider_uuid: str, provider_url: str):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_links SET
                           state='ACTIVE',provider_media_link_uuid=%s,provider_url=%s,
                           last_error=NULL
                       WHERE runtime_media_link_id=%s RETURNING *""",
                    (provider_uuid, provider_url, runtime_id),
                )
                row = cursor.fetchone()
                cursor.execute(
                    """UPDATE public.fanvue_fingerprint_reservations SET
                           state='ACTIVE',activated_at=COALESCE(activated_at,NOW())
                       WHERE fingerprint_reservation_id=%s""",
                    (row["fingerprint_reservation_id"],),
                )
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_link_operations SET
                           state='SUCCEEDED',completed_at=NOW()
                       WHERE runtime_media_link_id=%s AND operation_type='CREATE'""",
                    (runtime_id,),
                )
                return self._runtime_link(row)

    def mark_creation_uncertain(self, runtime_id: UUID, error: Exception):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_links SET
                           state='UNCERTAIN',last_error=%s WHERE runtime_media_link_id=%s""",
                    (type(error).__name__, runtime_id),
                )
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_link_operations SET
                           state='UNCERTAIN',attempt_count=attempt_count+1,
                           next_attempt_at=NOW()+INTERVAL '1 minute',last_error=%s
                       WHERE runtime_media_link_id=%s AND operation_type='CREATE'""",
                    (type(error).__name__, runtime_id),
                )

    def request_delete(self, runtime_id: UUID):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.fanvue_runtime_media_links SET
                    state='DELETE_REQUESTED' WHERE runtime_media_link_id=%s
                    AND state IN ('ACTIVE','EXPIRED','DELETE_FAILED','ORPHANED') RETURNING *""",
                    (runtime_id,))
                row = cursor.fetchone()
                if row:
                    cursor.execute("""INSERT INTO public.fanvue_runtime_media_link_operations
                        (operation_id,runtime_media_link_id,operation_type,idempotency_key)
                        VALUES (%s,%s,'DELETE',%s) ON CONFLICT (idempotency_key) DO NOTHING""",
                        (uuid4(), runtime_id, uuid4()))
        return self._runtime_link(row) if row else None

    def claim_due_operations(self, *, limit=25):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""WITH due AS (
                    SELECT operation_id FROM public.fanvue_runtime_media_link_operations
                    WHERE state IN ('PENDING','FAILED','UNCERTAIN') AND next_attempt_at<=NOW()
                    ORDER BY next_attempt_at,created_at FOR UPDATE SKIP LOCKED LIMIT %s)
                    UPDATE public.fanvue_runtime_media_link_operations operation SET
                    state='CLAIMED',claimed_at=NOW(),attempt_count=attempt_count+1
                    FROM due WHERE operation.operation_id=due.operation_id
                    RETURNING operation.*""", (limit,))
                return [dict(row) for row in cursor.fetchall()]

    def operation_runtime(self, runtime_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""SELECT runtime.*,intent.fanvue_account_id,
                    intent.expected_price_minor,intent.expected_currency,
                    reservation.exact_price_minor,
                    publication.publication_metadata
                    FROM public.fanvue_runtime_media_links runtime
                    JOIN public.purchase_intents intent ON intent.purchase_intent_id=runtime.purchase_intent_id
                    JOIN public.fanvue_fingerprint_reservations reservation
                      ON reservation.fingerprint_reservation_id=runtime.fingerprint_reservation_id
                    JOIN public.commercial_publications publication ON publication.publication_id=intent.commercial_publication_id
                    WHERE runtime.runtime_media_link_id=%s""", (runtime_id,))
                row = cursor.fetchone()
        return dict(row) if row else None

    def finish_operation(self, operation_id, *, succeeded, error=None):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.fanvue_runtime_media_link_operations SET
                    state=%s,completed_at=CASE WHEN %s THEN NOW() ELSE NULL END,
                    next_attempt_at=CASE WHEN %s THEN next_attempt_at ELSE NOW()+INTERVAL '5 minutes' END,
                    last_error=%s WHERE operation_id=%s""",
                    ('SUCCEEDED' if succeeded else 'FAILED', succeeded, succeeded,
                     type(error).__name__ if error else None, operation_id))

    def mark_deleted(self, runtime_id):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute("""UPDATE public.fanvue_runtime_media_links SET
                    state='DELETED',deleted_at=COALESCE(deleted_at,NOW()),last_error=NULL
                    WHERE runtime_media_link_id=%s RETURNING *""", (runtime_id,))
                row = cursor.fetchone()
        return self._runtime_link(row) if row else None

    def match_purchase(
        self, *, fanvue_account_id: int, currency: str, gross_minor: int,
    ):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT reservation.*,runtime.runtime_media_link_id,
                              runtime.provider_media_link_uuid,runtime.state AS runtime_state,
                              intent.creator_profile_id,intent.telegram_chat_id,
                              intent.commercial_offering_id,
                              intent.commercial_publication_id,intent.status AS intent_status
                       FROM public.fanvue_fingerprint_reservations reservation
                       JOIN public.fanvue_runtime_media_links runtime
                         ON runtime.fingerprint_reservation_id=
                            reservation.fingerprint_reservation_id
                       JOIN public.purchase_intents intent
                         ON intent.purchase_intent_id=reservation.purchase_intent_id
                       WHERE reservation.fanvue_account_id=%s
                         AND reservation.currency=%s
                         AND reservation.exact_price_minor=%s
                         AND runtime.state IN ('ACTIVE','PURCHASED')""",
                    (fanvue_account_id, currency, gross_minor),
                )
                return [dict(row) for row in cursor.fetchall()]

    def mark_purchased(
        self, *, reservation_id: UUID, transaction_reference: str,
        purchased_at: datetime,
    ):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.fanvue_fingerprint_reservations SET
                           state='PURCHASED',purchased_at=COALESCE(purchased_at,%s),
                           provider_transaction_reference=COALESCE(
                               provider_transaction_reference,%s)
                       WHERE fingerprint_reservation_id=%s
                         AND (provider_transaction_reference IS NULL
                              OR provider_transaction_reference=%s)
                       RETURNING purchase_intent_id""",
                    (purchased_at, transaction_reference, reservation_id,
                     transaction_reference),
                )
                row = cursor.fetchone()
                if row is None:
                    raise ValueError("Fingerprint reservation was consumed differently.")
                cursor.execute(
                    """UPDATE public.fanvue_runtime_media_links SET state='PURCHASED'
                       WHERE fingerprint_reservation_id=%s
                         AND state IN ('ACTIVE','PURCHASED')""",
                    (reservation_id,),
                )
                return UUID(str(row["purchase_intent_id"]))

    @staticmethod
    def _grant(row):
        values = dict(row); values.pop("token_hash", None)
        for key in ("unlock_grant_id", "purchase_intent_id", "commercial_offering_id", "commercial_publication_id"):
            values[key] = UUID(str(values[key]))
        values["audit_metadata"] = values.get("audit_metadata") or {}
        return UnlockGrant(**values)

    @staticmethod
    def _reservation(row):
        values = dict(row)
        for key in ("fingerprint_reservation_id", "purchase_intent_id"):
            values[key] = UUID(str(values[key]))
        values["state"] = FingerprintReservationState(values["state"])
        values["recovery_metadata"] = values.get("recovery_metadata") or {}
        return FingerprintReservation(**values)

    @staticmethod
    def _runtime_link(row):
        values = dict(row)
        for key in ("runtime_media_link_id", "purchase_intent_id", "fingerprint_reservation_id", "creation_operation_key"):
            values[key] = UUID(str(values[key]))
        values["state"] = RuntimeMediaLinkState(values["state"])
        values["reconciliation_metadata"] = values.get("reconciliation_metadata") or {}
        return RuntimeMediaLink(**values)
