"""Set-based SQL projection for Commercial Fulfillment consumers."""
from __future__ import annotations
from collections.abc import Callable
from uuid import UUID

from app.database import get_db_connection
from app.services.reference_asset_protection import commercial_asset_eligibility_sql


class CommercialFulfillmentRepository:
    def __init__(self, connection_factory: Callable = get_db_connection) -> None:
        self.connection_factory = connection_factory

    def get(self, offering_id: UUID, *, creator_profile_id: int):
        rows = self._query(
            creator_profile_id=creator_profile_id,
            filters=["offering.offering_id=%s"],
            params=[offering_id],
            fulfillable_only=False,
            limit=1,
            offset=0,
        )
        return rows[0] if rows else None

    def list_fulfillable(
        self, *, creator_profile_id: int, primary_sales_channel: str,
        offering_type: str | None, provider: str | None,
        page: int, page_size: int,
    ):
        filters = ["offering.primary_sales_channel=%s"]
        params: list = [primary_sales_channel]
        if offering_type:
            filters.append("offering.offering_type=%s")
            params.append(offering_type)
        if provider:
            filters.append("publication.provider=%s")
            params.append(provider)
        where = self._where(creator_profile_id, filters)
        having = self._fulfillable_having()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT COUNT(*) AS total FROM (
                        {self._select(where, having)}
                    ) eligible""",
                    (creator_profile_id, *params),
                )
                total = int(cursor.fetchone()["total"] or 0)
        total_pages = max(1, (total + page_size - 1) // page_size)
        current_page = min(max(1, page), total_pages)
        rows = self._query(
            creator_profile_id=creator_profile_id,
            filters=filters, params=params, fulfillable_only=True,
            limit=page_size, offset=(current_page - 1) * page_size,
        )
        return rows, total, current_page

    def list_candidates(
        self, *, creator_profile_id: int, primary_sales_channel: str,
    ):
        return self._query(
            creator_profile_id=creator_profile_id,
            filters=["offering.primary_sales_channel=%s"],
            params=[primary_sales_channel],
            fulfillable_only=False,
            limit=1000,
            offset=0,
        )

    def _query(
        self, *, creator_profile_id, filters, params,
        fulfillable_only, limit, offset,
    ):
        where = self._where(creator_profile_id, filters)
        having = self._fulfillable_having() if fulfillable_only else ""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    self._select(where, having)
                    + " ORDER BY offering.created_at DESC, offering.offering_id ASC "
                    "LIMIT %s OFFSET %s",
                    (creator_profile_id, *params, limit, offset),
                )
                return cursor.fetchall()

    @staticmethod
    def _where(creator_profile_id, filters):
        del creator_profile_id
        return " AND ".join(
            ["offering.creator_profile_id=%s", *filters]
        )

    @staticmethod
    def _select(where, having):
        return f"""SELECT
            offering.offering_id,offering.creator_profile_id,
            offering.title,offering.description,
            offering.offering_type,offering.primary_sales_channel,
            offering.price_minor,offering.currency,offering.hero_asset_id,
            offering.status AS offering_status,offering.created_at,
            array_agg(member.asset_id ORDER BY member.position) AS asset_ids,
            array_agg(destination.destination ORDER BY member.position) AS destinations,
            (
                SELECT COALESCE(jsonb_agg(
                    jsonb_build_object(
                        'asset_id', intelligence.asset_id,
                        'profile_data', intelligence.profile_data
                    ) ORDER BY intelligence.asset_id
                ), '[]'::jsonb)
                FROM public.commercial_offering_assets intelligence_member
                JOIN public.asset_intelligence_profiles intelligence
                  ON intelligence.asset_id=intelligence_member.asset_id
                 AND intelligence.creator_profile_id=offering.creator_profile_id
                 AND intelligence.analysis_status IN ('READY','PARTIAL',
                     'CONTENT_INTELLIGENCE_COMPLETE')
                WHERE intelligence_member.offering_id=offering.offering_id
            ) AS asset_intelligence,
            (
                SELECT membership.photoshoot_session_id
                FROM public.photoshoot_asset_memberships membership
                WHERE membership.asset_id=offering.hero_asset_id
                  AND membership.approved=TRUE
                ORDER BY membership.updated_at DESC
                LIMIT 1
            ) AS photoshoot_identifier,
            (
                SELECT profile.profile_data
                FROM public.photoshoot_asset_memberships membership
                JOIN public.photoshoot_intelligence_profiles profile
                  ON profile.photoshoot_session_id=membership.photoshoot_session_id
                WHERE membership.asset_id=offering.hero_asset_id
                  AND membership.approved=TRUE
                ORDER BY membership.updated_at DESC
                LIMIT 1
            ) AS photoshoot_intelligence,
            publication.publication_id,publication.provider,
            publication.external_product_id,
            publication.publication_metadata#>>'{{media_link,url}}' AS delivery_url,
            publication.status AS publication_status,
            COALESCE(publication.provider_resource_status,'UNVERIFIED')
                AS provider_resource_status,
            publication.last_reconciled_at,publication.published_at
            ,TRUE AS commercially_eligible
        FROM public.commercial_offerings offering
        JOIN public.commercial_offering_assets member
          ON member.offering_id=offering.offering_id
        JOIN public.content_items member_asset
          ON member_asset.id=member.asset_id
        JOIN public.asset_content_destinations destination
          ON destination.asset_id=member.asset_id
        LEFT JOIN public.commercial_publications publication
          ON publication.commercial_offering_id=offering.offering_id
        WHERE {where}
          AND {commercial_asset_eligibility_sql("member_asset")}
        GROUP BY offering.offering_id,publication.publication_id
        {having}"""

    @staticmethod
    def _fulfillable_having():
        return """HAVING offering.status<>'ARCHIVED'
            AND offering.price_minor BETWEEN 300 AND 50000
            AND publication.status='LIVE'
            AND publication.provider_resource_status='PRESENT'
            AND publication.external_product_id IS NOT NULL
            AND COALESCE(publication.publication_metadata#>>'{media_link,url}','')<>''
            AND (
                (offering.offering_type IN ('SINGLE_IMAGE','VIDEO')
                 AND COUNT(*)=1
                 AND bool_and(destination.destination='SINGLE_PPV'))
                OR
                (offering.offering_type='PHOTOSET'
                 AND bool_and(destination.destination='PHOTOSET'))
            )"""
