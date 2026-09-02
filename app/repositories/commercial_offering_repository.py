"""PostgreSQL persistence for Commercial Offerings and ordered membership."""

from __future__ import annotations

from collections.abc import Callable
from contextlib import nullcontext
from uuid import UUID, uuid4

from app.database import get_db_connection
from app.models.commercial_offering import (
    CommercialOffering,
    CommercialOfferingAsset,
    CommercialOfferingStatus,
    CommercialOfferingType,
    PrimarySalesChannel,
)


class CommercialOfferingRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self._connection_factory = connection_factory

    def transaction(self):
        """Expose the repository transaction used by offering-domain orchestration."""
        return self._connection_factory()

    def create(
        self, *, creator_profile_id: int, offering_type: CommercialOfferingType,
        title: str, description: str | None, hero_asset_id: int,
        primary_sales_channel: PrimarySalesChannel, asset_ids: tuple[int, ...],
        price_minor: int | None = None, currency: str = "USD",
        status: CommercialOfferingStatus = CommercialOfferingStatus.DRAFT,
        source_photoshoot_deliverable_id: UUID | None = None,
        source_bundle_studio_bundle_id: UUID | None = None,
        idempotency_key: str | None = None,
        connection=None,
    ) -> CommercialOffering:
        offering_id = uuid4()
        with (
            nullcontext(connection)
            if connection is not None
            else self._connection_factory()
        ) as active_connection:
            with active_connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.commercial_offerings
                       (offering_id,creator_profile_id,offering_type,title,description,
                        hero_asset_id,primary_sales_channel,status,price_minor,currency,
                        source_photoshoot_deliverable_id,source_bundle_studio_bundle_id,idempotency_key)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (offering_id, creator_profile_id, offering_type.value, title,
                     description, hero_asset_id, primary_sales_channel.value,
                     status.value, price_minor, currency,
                     source_photoshoot_deliverable_id, source_bundle_studio_bundle_id, idempotency_key),
                )
                row = cursor.fetchone()
                for position, asset_id in enumerate(asset_ids, 1):
                    cursor.execute(
                        """INSERT INTO public.commercial_offering_assets
                           (offering_id,asset_id,position,is_hero)
                           VALUES (%s,%s,%s,%s)""",
                        (offering_id, asset_id, position, asset_id == hero_asset_id),
                    )
        members = tuple(
            CommercialOfferingAsset(
                asset_id=asset_id,
                position=position,
                is_hero=asset_id == hero_asset_id,
            )
            for position, asset_id in enumerate(asset_ids, 1)
        )
        return self._from_row(row, members)

    def get_by_idempotency_key(
        self, *, creator_profile_id: int, idempotency_key: str, connection=None,
    ) -> CommercialOffering | None:
        with (nullcontext(connection) if connection is not None else self._connection_factory()) as active_connection:
            with active_connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commercial_offerings
                       WHERE creator_profile_id=%s AND idempotency_key=%s""",
                    (creator_profile_id, idempotency_key),
                )
                row = cursor.fetchone()
        return self._from_row(row, self._members(UUID(str(row["offering_id"])))) if row else None

    def get(
        self, offering_id: UUID, *, creator_profile_id: int,
    ) -> CommercialOffering | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT * FROM public.commercial_offerings
                       WHERE offering_id=%s AND creator_profile_id=%s""",
                    (offering_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return self._from_row(row, self._members(offering_id)) if row else None

    def list_page(
        self, *, creator_profile_id: int, search: str | None,
        page: int, page_size: int,
    ) -> tuple[tuple[CommercialOffering, ...], int, int]:
        filters = ["creator_profile_id=%s", "status<>'ARCHIVED'"]
        params: list = [creator_profile_id]
        if search:
            filters.append("(title ILIKE %s OR COALESCE(description,'') ILIKE %s)")
            term = f"%{search.strip()}%"
            params.extend((term, term))
        where = " AND ".join(filters)
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM public.commercial_offerings WHERE {where}",
                    tuple(params),
                )
                total = int(cursor.fetchone()["total"] or 0)
                total_pages = max(1, (total + page_size - 1) // page_size)
                current_page = min(max(1, page), total_pages)
                cursor.execute(
                    f"""SELECT offering.*, COUNT(member.asset_id) AS asset_count
                        FROM public.commercial_offerings offering
                        LEFT JOIN public.commercial_offering_assets member USING (offering_id)
                        WHERE {' AND '.join('offering.' + part if part in ('creator_profile_id=%s', "status<>'ARCHIVED'") else part for part in filters)}
                        GROUP BY offering.offering_id
                        ORDER BY offering.created_at DESC, offering.offering_id DESC
                        LIMIT %s OFFSET %s""",
                    (*params, page_size, (current_page - 1) * page_size),
                )
                rows = cursor.fetchall()
        offerings = tuple(
            self._from_row(row, tuple(
                CommercialOfferingAsset(0, position, position == 1)
                for position in range(1, int(row.get("asset_count") or 0) + 1)
            ))
            for row in rows
        )
        return offerings, total, current_page

    def update_metadata(
        self, offering_id: UUID, *, creator_profile_id: int,
        title: str, description: str | None, hero_asset_id: int,
    ) -> CommercialOffering | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_offerings
                       SET title=%s,description=%s,hero_asset_id=%s,updated_at=now()
                       WHERE offering_id=%s AND creator_profile_id=%s RETURNING *""",
                    (title, description, hero_asset_id, offering_id, creator_profile_id),
                )
                row = cursor.fetchone()
                if row:
                    cursor.execute(
                        """UPDATE public.commercial_offering_assets
                           SET is_hero=(asset_id=%s) WHERE offering_id=%s""",
                        (hero_asset_id, offering_id),
                    )
        return self._from_row(row, self._members(offering_id)) if row else None

    def update_pricing(
        self, offering_id: UUID, *, creator_profile_id: int,
        price_minor: int, currency: str,
    ) -> CommercialOffering | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_offerings
                       SET price_minor=%s,currency=%s,updated_at=now()
                       WHERE offering_id=%s AND creator_profile_id=%s RETURNING *""",
                    (price_minor, currency, offering_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return self._from_row(row, self._members(offering_id)) if row else None

    def update_status(self, offering_id: UUID, *, creator_profile_id: int,
                      status: CommercialOfferingStatus, connection=None):
        with (nullcontext(connection) if connection is not None else self._connection_factory()) as active_connection:
            with active_connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_offerings SET status=%s,updated_at=now()
                       WHERE offering_id=%s AND creator_profile_id=%s RETURNING *""",
                    (status.value, offering_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return self._from_row(row, self._members(offering_id)) if row else None

    def archive(
        self, offering_id: UUID, *, creator_profile_id: int,
    ) -> CommercialOffering | None:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.commercial_offerings
                       SET status='ARCHIVED',updated_at=now()
                       WHERE offering_id=%s AND creator_profile_id=%s
                         AND status<>'ARCHIVED' RETURNING *""",
                    (offering_id, creator_profile_id),
                )
                row = cursor.fetchone()
        return self._from_row(row, self._members(offering_id)) if row else None

    def _members(self, offering_id: UUID) -> tuple[CommercialOfferingAsset, ...]:
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT asset_id,position,is_hero
                       FROM public.commercial_offering_assets
                       WHERE offering_id=%s ORDER BY position""",
                    (offering_id,),
                )
                rows = cursor.fetchall()
        return tuple(CommercialOfferingAsset(
            asset_id=int(row["asset_id"]), position=int(row["position"]),
            is_hero=bool(row["is_hero"]),
        ) for row in rows)

    @staticmethod
    def _from_row(row, assets) -> CommercialOffering:
        return CommercialOffering(
            offering_id=UUID(str(row["offering_id"])),
            creator_profile_id=int(row["creator_profile_id"]),
            offering_type=CommercialOfferingType(row["offering_type"]),
            title=str(row["title"]), description=row.get("description"),
            hero_asset_id=int(row["hero_asset_id"]),
            primary_sales_channel=PrimarySalesChannel(row["primary_sales_channel"]),
            price_minor=(int(row["price_minor"]) if row.get("price_minor") is not None else None),
            currency=str(row.get("currency") or "USD"),
            status=CommercialOfferingStatus(row["status"]), assets=tuple(assets),
            created_at=row["created_at"], updated_at=row["updated_at"],
            source_photoshoot_deliverable_id=(
                UUID(str(row["source_photoshoot_deliverable_id"]))
                if row.get("source_photoshoot_deliverable_id") else None
            ),
            source_bundle_studio_bundle_id=(UUID(str(row["source_bundle_studio_bundle_id"])) if row.get("source_bundle_studio_bundle_id") else None),
        )
