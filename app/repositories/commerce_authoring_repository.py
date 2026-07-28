"""Set-based creator-facing Commerce catalog projection."""
from app.database import get_db_connection


class CommerceAuthoringRepository:
    def __init__(self, connection_factory=get_db_connection) -> None:
        self.connection_factory = connection_factory

    def summary(self, *, creator_profile_id: int):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """SELECT COUNT(*) AS total,
                       COUNT(*) FILTER (WHERE offering.status='DRAFT') AS draft,
                       COUNT(*) FILTER (WHERE offering.status='READY') AS ready,
                       COUNT(*) FILTER (WHERE offering.status='ARCHIVED') AS archived,
                       COUNT(*) FILTER (WHERE publication.status='LIVE'
                         AND offering.status<>'ARCHIVED') AS live
                       FROM public.commercial_offerings offering
                       LEFT JOIN public.commercial_publications publication
                         ON publication.commercial_offering_id=offering.offering_id
                        AND publication.provider='FANVUE'
                       WHERE offering.creator_profile_id=%s""",
                    (creator_profile_id,),
                )
                return cursor.fetchone()

    def list_page(
        self, *, creator_profile_id: int, search=None, status=None,
        offering_type=None, channel=None, publication_status=None,
        page=1, page_size=20,
    ):
        filters = ["offering.creator_profile_id=%s"]
        params = [creator_profile_id]
        for clause, value in (
            ("offering.status=%s", status),
            ("offering.offering_type=%s", offering_type),
            ("offering.primary_sales_channel=%s", channel),
            ("publication.status=%s", publication_status),
        ):
            if value:
                filters.append(clause)
                params.append(str(value).upper())
        if search:
            filters.append("(offering.title ILIKE %s OR COALESCE(offering.description,'') ILIKE %s)")
            term = f"%{str(search).strip()}%"
            params.extend((term, term))
        where = " AND ".join(filters)
        source = """FROM public.commercial_offerings offering
            LEFT JOIN public.commercial_publications publication
              ON publication.commercial_offering_id=offering.offering_id
             AND publication.provider='FANVUE'"""
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total {source} WHERE {where}",
                    tuple(params),
                )
                total = int(cursor.fetchone()["total"] or 0)
                total_pages = max(1, (total + page_size - 1) // page_size)
                current = min(max(1, page), total_pages)
                cursor.execute(
                    f"""SELECT offering.*,
                        COUNT(member.asset_id) AS asset_count,
                        publication.publication_id,
                        publication.status AS publication_status,
                        publication.provider,
                        COALESCE(publication.provider_resource_status,'UNVERIFIED')
                          AS provider_resource_status,
                        publication.last_reconciled_at,
                        publication.reconciliation_result,
                        publication.last_error,
                        publication.published_at,
                        CASE WHEN publication.status='LIVE'
                              AND publication.provider_resource_status='PRESENT'
                              AND offering.status<>'ARCHIVED'
                             THEN publication.publication_metadata#>>'{{media_link,url}}'
                             ELSE NULL END AS delivery_url
                        {source}
                        LEFT JOIN public.commercial_offering_assets member
                          ON member.offering_id=offering.offering_id
                        WHERE {where}
                        GROUP BY offering.offering_id,publication.publication_id
                        ORDER BY offering.updated_at DESC,offering.offering_id ASC
                        LIMIT %s OFFSET %s""",
                    (*params, page_size, (current - 1) * page_size),
                )
                rows = cursor.fetchall()
        return rows, total, current
