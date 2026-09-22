"""PostgreSQL lineage only; transactions remain owned by canonical commerce."""
from contextlib import contextmanager
from uuid import uuid4

from app.database import get_db_connection
from app.repositories.advisory_lock_key import deterministic_bigint_advisory_lock_key


class EvergreenCheckoutRepository:
    def __init__(self, *, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    @contextmanager
    def serialize(self, namespace, original_id):
        key = deterministic_bigint_advisory_lock_key(
            domain=f"creator-os:evergreen-checkout:v1:{namespace}",
            components=(("original_id", original_id.int),),
        )
        # One checked-out connection also owns all local transactions, without
        # acquiring a second pooled connection for local work under this lock.
        with self.connection_factory() as connection:
            connection.execute("SELECT pg_advisory_lock(%s::bigint)", (key,))
            connection.commit()
            try:
                yield connection
            finally:
                connection.rollback()
                connection.execute("SELECT pg_advisory_unlock(%s::bigint)", (key,))
                connection.commit()

    @staticmethod
    def latest(connection, namespace, original_id):
        return connection.execute(
            """SELECT * FROM public.evergreen_checkout_lineage
               WHERE namespace=%s AND original_transaction_id=%s
               ORDER BY generation DESC LIMIT 1""", (namespace, original_id),
        ).fetchone()

    @staticmethod
    def append(connection, *, namespace, grant, predecessor, successor, generation, now):
        connection.execute(
            """INSERT INTO public.evergreen_checkout_lineage (
                namespace,alias_id,original_transaction_id,generation,
                predecessor_id,successor_id,refresh_reason,refreshed_at,
                predecessor_price_minor,successor_price_minor,currency,eligibility_result)
               VALUES (%s,%s,%s,%s,%s,%s,'TRANSACTION_EXPIRED',%s,%s,%s,%s,'ELIGIBLE')""",
            (namespace, grant.alias_id, grant.original_transaction_id, generation,
             predecessor.transaction_id, successor.transaction_id, now,
             predecessor.price.minor, successor.price.minor, successor.price.currency),
        )

    @staticmethod
    def runtime_result(connection, namespace, effective_id, *, state, reason):
        connection.execute(
            """UPDATE public.evergreen_checkout_lineage
               SET runtime_state=%s,runtime_reason=%s
               WHERE namespace=%s AND successor_id=%s""",
            (state, reason, namespace, effective_id),
        )

    @staticmethod
    def record(connection, *, namespace, grant, effective_id, generation, result, reason, now):
        connection.execute(
            """INSERT INTO public.evergreen_checkout_resolution_events (
                event_id,namespace,alias_id,original_transaction_id,
                effective_transaction_id,generation,result,reason_code,occurred_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (uuid4(), namespace, grant.alias_id, grant.original_transaction_id,
             effective_id, generation, result, reason, now),
        )
