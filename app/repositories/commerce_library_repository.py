"""Narrow, paginated read model for the React Commerce Library."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from app.database import get_db_connection
from app.services.content_destination_service import ContentDestinationService
from app.services.reference_asset_protection import commercial_asset_eligibility_sql


@dataclass(frozen=True)
class CommerceLibraryListItem:
    item_id: str
    item_kind: str
    asset_id: int
    creator_profile_id: int
    asset_name: str | None
    analysis_status: str
    current_lifecycle: str
    commerce_status: str
    deliverable_id: str | None = None
    shot_count: int | None = None


@dataclass(frozen=True)
class CommerceLibraryPage:
    items: tuple[CommerceLibraryListItem, ...]
    total: int
    page: int


class CommerceLibraryRepository:
    """Set-based list projection; deliberately excludes detail enrichment."""

    _STATUS_SQL = """
        CASE
            WHEN b.content_intelligence_status LIKE '%%\\_FAILED' ESCAPE '\\'
                 OR b.content_intelligence_status = 'FAILED' THEN 'Analysis Failed'
            WHEN COALESCE(chat.chat_ready, FALSE) THEN 'Chat Ready'
            WHEN fulfillment.lifecycle_state = 'WAITING_FOR_MEDIA_LINK' THEN 'Needs Media Link'
            WHEN b.business_lifecycle_state IN ('AWAITING_UPLOAD', 'PUBLISHING_READY') THEN 'Needs Upload'
            WHEN NOT b.content_intelligence_ready THEN 'Analyzing'
            ELSE 'Ready'
        END
    """

    def __init__(
        self,
        *,
        connection_factory: Callable = get_db_connection,
        content_destination_service: ContentDestinationService | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self.content_destinations = (
            content_destination_service or ContentDestinationService()
        )

    def list_page(
        self,
        *,
        creator_profile_id: int,
        search: str | None,
        commerce_status: str | None,
        page_size: int,
        page: int,
        status: str | None = None,
        destination: str | None = None,
        source_workflow: str | None = None,
        chat_ready: bool | None = None,
        fulfillment_ready: bool | None = None,
        recommendation_ready: bool | None = None,
        awaiting_destination: bool | None = None,
        waiting_for_media_link: bool | None = None,
        blocked: bool | None = None,
    ) -> CommerceLibraryPage:
        union_sql, params = self._union_sql(
            creator_profile_id=creator_profile_id,
            search=search,
            status=status,
            destination=destination,
            source_workflow=source_workflow,
            chat_ready=chat_ready,
            fulfillment_ready=fulfillment_ready,
            recommendation_ready=recommendation_ready,
            awaiting_destination=awaiting_destination,
            waiting_for_media_link=waiting_for_media_link,
            blocked=blocked,
        )
        status_filter = "WHERE LOWER(commerce_status) = LOWER(%s)" if commerce_status else ""
        status_params: tuple[Any, ...] = (commerce_status,) if commerce_status else ()

        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"SELECT COUNT(*) AS total FROM ({union_sql}) commerce_items {status_filter}",
                    (*params, *status_params),
                )
                total = int(cursor.fetchone()["total"])
                total_pages = max(1, (total + page_size - 1) // page_size)
                current_page = min(int(page), total_pages)
                offset = (current_page - 1) * page_size
                cursor.execute(
                    f"""
                    SELECT * FROM ({union_sql}) commerce_items
                    {status_filter}
                    ORDER BY sort_at DESC NULLS LAST, item_id DESC
                    LIMIT %s OFFSET %s
                    """,
                    (*params, *status_params, int(page_size), int(offset)),
                )
                rows = cursor.fetchall()

        return CommerceLibraryPage(
            items=tuple(self._item(row) for row in rows),
            total=total,
            page=current_page,
        )

    def _union_sql(
        self,
        *,
        creator_profile_id: int,
        search: str | None,
        status: str | None,
        destination: str | None,
        source_workflow: str | None,
        chat_ready: bool | None,
        fulfillment_ready: bool | None,
        recommendation_ready: bool | None,
        awaiting_destination: bool | None,
        waiting_for_media_link: bool | None,
        blocked: bool | None,
    ) -> tuple[str, tuple[Any, ...]]:
        needle = str(search or "").strip()
        asset_search = ""
        photoshoot_search = ""
        asset_params: list[Any] = [int(creator_profile_id)]
        photoshoot_params: list[Any] = [int(creator_profile_id)]
        if needle:
            term = f"%{needle}%"
            asset_search = "AND (COALESCE(content.file_name, '') ILIKE %s OR b.asset_id::text ILIKE %s)"
            photoshoot_search = """AND (
                COALESCE(NULLIF(BTRIM(d.user_title), ''), d.ai_title, d.display_name) ILIKE %s
                OR COALESCE(NULLIF(BTRIM(d.user_description), ''), d.ai_description, '') ILIKE %s
                OR d.deliverable_id::text ILIKE %s
            )"""
            asset_params.extend((term, term))
            photoshoot_params.extend((term, term, term))

        asset_filters: list[str] = []
        if destination:
            asset_filters.append("COALESCE(b.selected_commerce_destination, chat.commerce_destination) = %s")
            asset_params.append(str(destination))
        if source_workflow:
            asset_filters.append("COALESCE(b.destination_source_workflow, chat.source_workflow, fulfillment.provenance->>'source_workflow') = %s")
            asset_params.append(str(source_workflow))
        for expected, expression in (
            (chat_ready, "COALESCE(chat.chat_ready, FALSE)"),
            (recommendation_ready, "COALESCE(chat.recommendation_eligible, FALSE)"),
            (awaiting_destination, "b.commerce_destination_status = 'AWAITING_DESTINATION'"),
            (waiting_for_media_link, "fulfillment.lifecycle_state = 'WAITING_FOR_MEDIA_LINK'"),
            (blocked, "chat.availability_state IN ('BLOCKED', 'FAILED')"),
        ):
            if expected is not None:
                asset_filters.append(f"({expression}) = %s")
                asset_params.append(bool(expected))
        if fulfillment_ready is not None:
            asset_filters.append("(fulfillment.lifecycle_state = 'FULFILLMENT_READY' OR COALESCE(chat.fulfillment_ready, FALSE)) = %s")
            asset_params.append(bool(fulfillment_ready))
        if status:
            availability = """CASE
                WHEN chat.availability_state = 'CHAT_READY' THEN 'Chat Ready'
                WHEN chat.availability_state = 'TEMPORARILY_UNAVAILABLE' THEN 'Temporarily Unavailable'
                WHEN chat.availability_state = 'RETIRED' THEN 'Retired'
                WHEN chat.availability_state IN ('BLOCKED', 'FAILED') THEN 'Blocked'
                WHEN b.commerce_destination_status = 'AWAITING_DESTINATION' THEN 'Awaiting Destination'
                WHEN fulfillment.lifecycle_state = 'WAITING_FOR_MEDIA_LINK' THEN 'Waiting For Media Link'
                ELSE 'Pending' END"""
            asset_filters.append(f"({availability}) = %s")
            asset_params.append(str(status))
        extra_asset_filters = "".join(f" AND {condition}" for condition in asset_filters)
        available_inventory = self.content_destinations.available_inventory_predicate(
            "b.asset_id"
        )

        sql = f"""
            SELECT
                'asset:' || b.asset_id::text AS item_id,
                'asset'::text AS item_kind,
                b.asset_id,
                b.creator_profile_id,
                content.file_name AS asset_name,
                b.content_intelligence_status AS analysis_status,
                b.business_lifecycle_state AS current_lifecycle,
                {self._STATUS_SQL} AS commerce_status,
                NULL::text AS deliverable_id,
                NULL::integer AS shot_count,
                b.updated_at AS sort_at
            FROM public.business_asset_registrations b
            JOIN public.content_items content ON content.id = b.asset_id
            LEFT JOIN public.chat_commerce_registrations chat
              ON chat.asset_id = b.asset_id AND chat.active = TRUE AND chat.retired = FALSE
            LEFT JOIN public.business_asset_fulfillment_registrations fulfillment
              ON fulfillment.asset_id = b.asset_id AND fulfillment.route = 'CUSTOMER_CONVERSATIONS'
            WHERE b.creator_profile_id = %s
              AND b.is_archived = FALSE
              AND {commercial_asset_eligibility_sql("content")}
              AND {available_inventory}
              {asset_search}
              {extra_asset_filters}
            UNION ALL
            SELECT
                'photoshoot:' || d.deliverable_id::text AS item_id,
                'photoshoot'::text AS item_kind,
                COALESCE(d.hero_asset_id, 0) AS asset_id,
                d.creator_profile_id::integer,
                COALESCE(NULLIF(BTRIM(d.user_title), ''), d.ai_title, d.display_name) AS asset_name,
                CASE WHEN workflow.current_stage = 'READY' THEN 'COMPLETE'
                     WHEN workflow.current_stage LIKE '%%\\_FAILED' ESCAPE '\\' THEN 'FAILED'
                     ELSE 'ANALYZING' END AS analysis_status,
                CASE WHEN workflow.current_stage = 'READY' THEN 'PHOTOSHOOT_READY'
                     WHEN workflow.current_stage LIKE '%%\\_FAILED' ESCAPE '\\' THEN 'ANALYSIS_FAILED'
                     ELSE 'INTELLIGENCE_PENDING' END AS current_lifecycle,
                CASE WHEN workflow.current_stage = 'READY' THEN 'Ready'
                     WHEN workflow.current_stage LIKE '%%\\_FAILED' ESCAPE '\\' THEN 'Analysis Failed'
                     ELSE 'Analyzing' END AS commerce_status,
                d.deliverable_id::text,
                d.shot_count,
                COALESCE(d.updated_at, d.completed_at, d.created_at) AS sort_at
            FROM public.photoshoot_commerce_deliverables d
            LEFT JOIN public.photoshoot_analysis_workflows workflow USING (deliverable_id)
            WHERE d.creator_profile_id = %s
              AND d.registration_state = 'REGISTERED'
              AND d.is_active = TRUE
              AND d.is_archived = FALSE
              {photoshoot_search}
        """
        return sql, tuple((*asset_params, *photoshoot_params))

    @staticmethod
    def _item(row: dict[str, Any]) -> CommerceLibraryListItem:
        return CommerceLibraryListItem(
            item_id=str(row["item_id"]),
            item_kind=str(row["item_kind"]),
            asset_id=int(row["asset_id"]),
            creator_profile_id=int(row["creator_profile_id"]),
            asset_name=row.get("asset_name"),
            analysis_status=str(row.get("analysis_status") or "ANALYZING"),
            current_lifecycle=str(row.get("current_lifecycle") or "ANALYZING"),
            commerce_status=str(row.get("commerce_status") or "Analyzing"),
            deliverable_id=str(row["deliverable_id"]) if row.get("deliverable_id") else None,
            shot_count=int(row["shot_count"]) if row.get("shot_count") is not None else None,
        )
