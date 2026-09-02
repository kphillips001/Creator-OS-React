"""Atomic cross-process leases for optional proactive customer contact."""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.customer_contact_reservation import CustomerContactReservation


class CustomerContactReservationRepository:
    def __init__(self, connection_factory=get_db_connection, *, clock=None):
        self.connection_factory = connection_factory
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def try_acquire(self, *, fanvue_account_id: int, customer_scope: str,
                    contact_purpose: str, owner_id: str,
                    creator_profile_id: int | None = None,
                    correlation_id: str | None = None,
                    lease_seconds: int = 300, metadata=None):
        now = self.clock()
        expires = now + timedelta(seconds=max(30, int(lease_seconds)))
        reservation_id = uuid4()
        with self.connection_factory() as connection, connection.cursor() as cursor:
            # A transaction-scoped advisory lock serializes expiration+insert for
            # one customer without holding a database connection during send.
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                (f"customer-contact:{int(fanvue_account_id)}:{customer_scope}",),
            )
            cursor.execute(
                """UPDATE public.customer_contact_reservations
                   SET state='EXPIRED',finalized_at=%s,updated_at=%s
                   WHERE fanvue_account_id=%s AND customer_scope=%s
                     AND state IN ('ACTIVE','SEND_UNCERTAIN')
                     AND lease_expires_at<=%s""",
                (now, now, int(fanvue_account_id), str(customer_scope), now),
            )
            cursor.execute(
                """SELECT * FROM public.customer_contact_reservations
                   WHERE fanvue_account_id=%s AND customer_scope=%s
                     AND state IN ('ACTIVE','SEND_UNCERTAIN')
                   LIMIT 1""",
                (int(fanvue_account_id), str(customer_scope)),
            )
            existing = cursor.fetchone()
            if existing is not None:
                return None, self._model(existing)
            cursor.execute(
                """INSERT INTO public.customer_contact_reservations (
                       reservation_id,creator_profile_id,fanvue_account_id,
                       customer_scope,contact_purpose,state,owner_id,
                       correlation_id,reserved_at,lease_expires_at,metadata
                   ) VALUES (%s,%s,%s,%s,%s,'ACTIVE',%s,%s,%s,%s,%s::jsonb)
                   RETURNING *""",
                (reservation_id, creator_profile_id, int(fanvue_account_id),
                 str(customer_scope), str(contact_purpose), str(owner_id),
                 correlation_id, now, expires,
                 json.dumps(dict(metadata or {}), default=str)),
            )
            return self._model(cursor.fetchone()), None

    def finalize(self, reservation_id: UUID, *, owner_id: str, state: str,
                 delivery_reference: str | None = None,
                 last_error: str | None = None):
        if state not in {"CONFIRMED", "FAILED", "SEND_UNCERTAIN", "RELEASED"}:
            raise ValueError("Unsupported contact reservation outcome")
        now = self.clock()
        uncertain_until = now + timedelta(hours=24)
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """UPDATE public.customer_contact_reservations
                   SET state=%s,delivery_reference=%s,last_error=%s,
                       finalized_at=CASE WHEN %s='SEND_UNCERTAIN' THEN NULL ELSE %s END,
                       lease_expires_at=CASE WHEN %s='SEND_UNCERTAIN' THEN %s ELSE lease_expires_at END,
                       updated_at=%s
                   WHERE reservation_id=%s AND owner_id=%s AND state='ACTIVE'
                   RETURNING *""",
                (state, delivery_reference, str(last_error or "")[:500] or None,
                 state, now, state, uncertain_until, now,
                 reservation_id, str(owner_id)),
            )
            row = cursor.fetchone()
            return self._model(row) if row else None

    @staticmethod
    def _model(row):
        return CustomerContactReservation(
            reservation_id=UUID(str(row["reservation_id"])),
            fanvue_account_id=int(row["fanvue_account_id"]),
            customer_scope=str(row["customer_scope"]),
            contact_purpose=str(row["contact_purpose"]), state=str(row["state"]),
            owner_id=str(row["owner_id"]), reserved_at=row["reserved_at"],
            lease_expires_at=row["lease_expires_at"],
            correlation_id=row.get("correlation_id"),
            delivery_reference=row.get("delivery_reference"),
        )
