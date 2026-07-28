"""PostgreSQL persistence for customer commerce profiles and transactions."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.customer_commerce import (
    CustomerCommerceProfile,
    CustomerCommerceProfileState,
    CustomerCommerceStatistics,
)


class CustomerCommerceRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def get_by_buyer_uuid(
        self, *, creator_profile_id: int, external_fanvue_user_uuid: UUID,
    ) -> CustomerCommerceProfile | None:
        return self._one(
            """SELECT * FROM public.customer_commerce_profiles
               WHERE creator_profile_id=%s AND external_fanvue_user_uuid=%s""",
            (creator_profile_id, external_fanvue_user_uuid),
        )

    def get_by_id(
        self, profile_id: UUID, *, creator_profile_id: int,
    ) -> CustomerCommerceProfile | None:
        return self._one(
            """SELECT * FROM public.customer_commerce_profiles
               WHERE customer_commerce_profile_id=%s AND creator_profile_id=%s""",
            (profile_id, creator_profile_id),
        )

    def get_or_create(
        self, *, creator_profile_id: int, fanvue_account_id: int,
        external_fanvue_user_uuid: UUID, seen_at: datetime,
        display_name: str | None = None, handle: str | None = None,
    ) -> CustomerCommerceProfile:
        profile_id = uuid4()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.customer_commerce_profiles (
                           customer_commerce_profile_id,creator_profile_id,
                           fanvue_account_id,external_fanvue_user_uuid,
                           display_name,handle,first_seen_at,last_seen_at
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (
                           creator_profile_id,external_fanvue_user_uuid
                       ) DO UPDATE SET
                           last_seen_at=GREATEST(
                               customer_commerce_profiles.last_seen_at,
                               EXCLUDED.last_seen_at
                           ),
                           display_name=COALESCE(
                               EXCLUDED.display_name,
                               customer_commerce_profiles.display_name
                           ),
                           handle=COALESCE(
                               EXCLUDED.handle,
                               customer_commerce_profiles.handle
                           ),
                           updated_at=NOW()
                       RETURNING *""",
                    (
                        profile_id, creator_profile_id, fanvue_account_id,
                        external_fanvue_user_uuid, display_name, handle,
                        seen_at, seen_at,
                    ),
                )
                row = cursor.fetchone()
        return self._profile(row)

    def record_purchase(
        self, *, profile_id: UUID, fanvue_account_id: int,
        transaction_order_id: str, gross_minor: int, net_minor: int,
        payment_status: str, purchase_source: str,
        payment_timestamp: datetime,
    ) -> tuple[CustomerCommerceProfile, bool]:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.customer_commerce_transactions (
                           customer_commerce_transaction_id,
                           customer_commerce_profile_id,fanvue_account_id,
                           transaction_order_id,gross_minor,net_minor,
                           payment_status,purchase_source,payment_timestamp
                       ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (
                           fanvue_account_id,transaction_order_id
                       ) DO NOTHING
                       RETURNING customer_commerce_transaction_id""",
                    (
                        uuid4(), profile_id, fanvue_account_id,
                        transaction_order_id, gross_minor, net_minor,
                        payment_status, purchase_source, payment_timestamp,
                    ),
                )
                inserted = cursor.fetchone() is not None
                if inserted:
                    cursor.execute(
                        """UPDATE public.customer_commerce_profiles SET
                               first_purchase_at=COALESCE(
                                   LEAST(first_purchase_at,%s),%s
                               ),
                               last_purchase_at=COALESCE(
                                   GREATEST(last_purchase_at,%s),%s
                               ),
                               last_seen_at=GREATEST(last_seen_at,%s),
                               lifetime_gross_minor=lifetime_gross_minor+%s,
                               lifetime_net_minor=lifetime_net_minor+%s,
                               purchase_count=purchase_count+1,
                               average_order_value_minor=(
                                   lifetime_gross_minor+%s
                               )/(purchase_count+1),
                               largest_purchase_minor=GREATEST(
                                   largest_purchase_minor,%s
                               ),
                               last_transaction_order_id=CASE
                                   WHEN last_purchase_at IS NULL
                                     OR %s>=last_purchase_at THEN %s
                                   ELSE last_transaction_order_id END,
                               last_payment_status=CASE
                                   WHEN last_purchase_at IS NULL
                                     OR %s>=last_purchase_at THEN %s
                                   ELSE last_payment_status END,
                               last_purchase_source=CASE
                                   WHEN last_purchase_at IS NULL
                                     OR %s>=last_purchase_at THEN %s
                                   ELSE last_purchase_source END,
                               last_synced_at=NOW(),updated_at=NOW()
                           WHERE customer_commerce_profile_id=%s""",
                        (
                            payment_timestamp, payment_timestamp,
                            payment_timestamp, payment_timestamp,
                            payment_timestamp, gross_minor, net_minor,
                            gross_minor, gross_minor,
                            payment_timestamp, transaction_order_id,
                            payment_timestamp, payment_status,
                            payment_timestamp, purchase_source, profile_id,
                        ),
                    )
                else:
                    cursor.execute(
                        """SELECT customer_commerce_profile_id
                           FROM public.customer_commerce_transactions
                           WHERE fanvue_account_id=%s
                             AND transaction_order_id=%s""",
                        (fanvue_account_id, transaction_order_id),
                    )
                    owner = cursor.fetchone()
                    if (
                        owner
                        and UUID(str(owner["customer_commerce_profile_id"]))
                        != profile_id
                    ):
                        raise ValueError(
                            "The transaction belongs to another customer "
                            "commerce profile."
                        )
                cursor.execute(
                    """SELECT * FROM public.customer_commerce_profiles
                       WHERE customer_commerce_profile_id=%s""",
                    (profile_id,),
                )
                row = cursor.fetchone()
        return self._profile(row), inserted

    def update_last_seen(
        self, profile_id: UUID, *, seen_at: datetime,
    ) -> CustomerCommerceProfile:
        return self._update(
            """UPDATE public.customer_commerce_profiles
               SET last_seen_at=GREATEST(last_seen_at,%s),updated_at=NOW()
               WHERE customer_commerce_profile_id=%s RETURNING *""",
            (seen_at, profile_id),
        )

    def update_profile(
        self, profile_id: UUID, *, display_name: str | None,
        handle: str | None, profile_state: CustomerCommerceProfileState,
        telegram_identity_mapping_id: int | None = None,
        telegram_user_id: int | None = None,
    ) -> CustomerCommerceProfile:
        return self._update(
            """UPDATE public.customer_commerce_profiles SET
                   display_name=%s,handle=%s,profile_state=%s,
                   telegram_identity_mapping_id=%s,telegram_user_id=%s,
                   updated_at=NOW()
               WHERE customer_commerce_profile_id=%s RETURNING *""",
            (
                display_name, handle, profile_state.value,
                telegram_identity_mapping_id, telegram_user_id, profile_id,
            ),
        )

    def refresh_statistics(
        self, profile_id: UUID,
    ) -> CustomerCommerceProfile:
        return self._update(
            """UPDATE public.customer_commerce_profiles profile SET
                   first_purchase_at=aggregate.first_purchase_at,
                   last_purchase_at=aggregate.last_purchase_at,
                   lifetime_gross_minor=aggregate.gross,
                   lifetime_net_minor=aggregate.net,
                   purchase_count=aggregate.purchase_count,
                   average_order_value_minor=aggregate.average_order,
                   largest_purchase_minor=aggregate.largest,
                   last_synced_at=NOW(),updated_at=NOW()
               FROM (
                   SELECT
                       MIN(payment_timestamp) AS first_purchase_at,
                       MAX(payment_timestamp) AS last_purchase_at,
                       COALESCE(SUM(gross_minor),0)::BIGINT AS gross,
                       COALESCE(SUM(net_minor),0)::BIGINT AS net,
                       COUNT(*)::INTEGER AS purchase_count,
                       COALESCE(AVG(gross_minor),0)::BIGINT AS average_order,
                       COALESCE(MAX(gross_minor),0)::BIGINT AS largest
                   FROM public.customer_commerce_transactions
                   WHERE customer_commerce_profile_id=%s
               ) aggregate
               WHERE profile.customer_commerce_profile_id=%s RETURNING profile.*""",
            (profile_id, profile_id),
        )

    def list_profiles(
        self, *, creator_profile_id: int, search: str | None,
        page: int, page_size: int,
    ) -> tuple[tuple[CustomerCommerceProfile, ...], int, int]:
        filters = ["creator_profile_id=%s"]
        params: list = [creator_profile_id]
        if search:
            filters.append(
                """(COALESCE(display_name,'') ILIKE %s
                    OR COALESCE(handle,'') ILIKE %s
                    OR external_fanvue_user_uuid::TEXT ILIKE %s)"""
            )
            term = f"%{search.strip()}%"
            params.extend((term, term, term))
        where = " AND ".join(filters)
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT COUNT(*) AS total
                        FROM public.customer_commerce_profiles WHERE {where}""",
                    tuple(params),
                )
                total = int(cursor.fetchone()["total"] or 0)
                total_pages = max(1, (total + page_size - 1) // page_size)
                current_page = min(max(1, page), total_pages)
                cursor.execute(
                    f"""SELECT * FROM public.customer_commerce_profiles
                        WHERE {where}
                        ORDER BY last_purchase_at DESC NULLS LAST,
                                 last_seen_at DESC,
                                 customer_commerce_profile_id
                        LIMIT %s OFFSET %s""",
                    (*params, page_size, (current_page - 1) * page_size),
                )
                rows = cursor.fetchall()
        return tuple(self._profile(row) for row in rows), total, current_page

    def get_statistics(
        self, *, creator_profile_id: int,
    ) -> CustomerCommerceStatistics:
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT COUNT(*)::INTEGER AS profile_count,
                              COUNT(*) FILTER (
                                  WHERE purchase_count>0
                              )::INTEGER AS buyer_count,
                              COALESCE(SUM(lifetime_gross_minor),0)::BIGINT
                                  AS lifetime_gross_minor,
                              COALESCE(SUM(lifetime_net_minor),0)::BIGINT
                                  AS lifetime_net_minor,
                              COALESCE(SUM(purchase_count),0)::INTEGER
                                  AS purchase_count,
                              CASE WHEN SUM(purchase_count)>0
                                   THEN (
                                       SUM(lifetime_gross_minor)
                                       / SUM(purchase_count)
                                   )::BIGINT ELSE 0 END
                                  AS average_order_value_minor,
                              COALESCE(MAX(largest_purchase_minor),0)::BIGINT
                                  AS largest_purchase_minor
                       FROM public.customer_commerce_profiles
                       WHERE creator_profile_id=%s""",
                    (creator_profile_id,),
                )
                row = cursor.fetchone()
        return CustomerCommerceStatistics(**{
            key: int(row[key] or 0) for key in (
                "profile_count", "buyer_count", "lifetime_gross_minor",
                "lifetime_net_minor", "purchase_count",
                "average_order_value_minor", "largest_purchase_minor",
            )
        })

    def _one(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        return self._profile(row) if row else None

    def _update(self, query, params):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(query, params)
                row = cursor.fetchone()
        if not row:
            raise LookupError("Customer commerce profile was not found.")
        return self._profile(row)

    @staticmethod
    def _profile(row) -> CustomerCommerceProfile:
        return CustomerCommerceProfile(
            customer_commerce_profile_id=UUID(
                str(row["customer_commerce_profile_id"])
            ),
            creator_profile_id=int(row["creator_profile_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            external_fanvue_user_uuid=UUID(
                str(row["external_fanvue_user_uuid"])
            ),
            telegram_identity_mapping_id=(
                int(row["telegram_identity_mapping_id"])
                if row.get("telegram_identity_mapping_id") is not None
                else None
            ),
            telegram_user_id=(
                int(row["telegram_user_id"])
                if row.get("telegram_user_id") is not None else None
            ),
            display_name=row.get("display_name"), handle=row.get("handle"),
            first_seen_at=row["first_seen_at"], last_seen_at=row["last_seen_at"],
            first_purchase_at=row.get("first_purchase_at"),
            last_purchase_at=row.get("last_purchase_at"),
            lifetime_gross_minor=int(row["lifetime_gross_minor"]),
            lifetime_net_minor=int(row["lifetime_net_minor"]),
            purchase_count=int(row["purchase_count"]),
            average_order_value_minor=int(row["average_order_value_minor"]),
            largest_purchase_minor=int(row["largest_purchase_minor"]),
            last_transaction_order_id=row.get("last_transaction_order_id"),
            last_payment_status=row.get("last_payment_status"),
            last_purchase_source=row.get("last_purchase_source"),
            last_synced_at=row.get("last_synced_at"),
            profile_state=CustomerCommerceProfileState(row["profile_state"]),
            created_at=row["created_at"], updated_at=row["updated_at"],
        )
