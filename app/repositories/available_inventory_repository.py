"""Narrow, server-paginated projection for Available Inventory."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from app.database import get_db_connection
from app.services.content_destination_service import ContentDestinationService
from app.services.reference_asset_protection import commercial_asset_eligibility_sql


@dataclass(frozen=True)
class AvailableInventoryItem:
    asset_id: int
    display_name: str
    media_type: str
    created_at: datetime | None
    registration_state: str
    readiness: str
    destination: str
    source_workflow: str
    source_name: str
    source_session_id: str | None
    short_description: str | None


@dataclass(frozen=True)
class AvailableInventoryPage:
    items: tuple[AvailableInventoryItem, ...]
    total: int
    ready: int
    pending: int
    page: int


class AvailableInventoryRepository:
    """Two-query read model with destination filtering before pagination."""

    _MEDIA_SQL = """CASE
        WHEN LOWER(COALESCE(asset.media_metadata->>'media_type', '')) IN ('image','video','story')
            THEN LOWER(asset.media_metadata->>'media_type')
        WHEN LOWER(COALESCE(asset.file_path, '')) ~ '\\.(m4v|mov|mp4|webm)$' THEN 'video'
        WHEN LOWER(COALESCE(asset.file_path, '')) ~ '\\.(gif|jpe?g|png|webp)$' THEN 'image'
        ELSE 'unknown' END"""
    _SOURCE_WORKFLOW_SQL = """COALESCE(
        NULLIF(asset.media_metadata->'photoshoot_session'->>'source_workflow', ''),
        NULLIF(asset.media_metadata->'creator_approval'->>'source_workflow', ''),
        NULLIF(destination.source_workflow, ''),
        'canonical_asset'
    )"""
    _SESSION_SQL = """COALESCE(
        NULLIF(asset.media_metadata->'photoshoot_session'->>'session_id', ''),
        NULLIF(asset.media_metadata->'creator_approval'->>'source_session_id', '')
    )"""

    def __init__(
        self,
        *,
        connection_factory: Callable = get_db_connection,
        content_destination_service: ContentDestinationService | None = None,
    ) -> None:
        self._connection_factory = connection_factory
        self.content_destinations = content_destination_service or ContentDestinationService()

    def list_page(
        self,
        *,
        creator_profile_id: int,
        page: int,
        page_size: int,
        search: str | None,
        readiness: str | None,
        source: str | None,
        media_type: str | None,
        sort: str,
    ) -> AvailableInventoryPage:
        where, params = self._filters(
            creator_profile_id=creator_profile_id,
            search=search,
            readiness=readiness,
            source=source,
            media_type=media_type,
        )
        order = {
            "oldest": "asset.created_at ASC NULLS LAST, asset.id ASC",
            "name": "LOWER(COALESCE(NULLIF(asset.file_name, ''), 'Asset ' || asset.id::text)), asset.id",
            "readiness": "COALESCE(intelligence.analysis_status, 'PENDING') ASC, asset.created_at DESC NULLS LAST, asset.id DESC",
        }.get(sort, "asset.created_at DESC NULLS LAST, asset.id DESC")
        joins = f"""
            FROM public.content_items asset
            JOIN public.asset_content_destinations destination ON destination.asset_id=asset.id
            LEFT JOIN public.asset_intelligence_profiles intelligence ON intelligence.asset_id=asset.id
            LEFT JOIN public.photoshoot_commerce_deliverables photoshoot
              ON photoshoot.photoshoot_session_id={self._SESSION_SQL}
        """
        with self._connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    f"""SELECT COUNT(*) AS total,
                        COUNT(*) FILTER (WHERE intelligence.analysis_status='READY') AS ready
                        {joins} WHERE {where}""",
                    tuple(params),
                )
                summary = cursor.fetchone()
                total = int(summary["total"] or 0)
                total_pages = max(1, (total + page_size - 1) // page_size)
                current_page = min(max(1, int(page)), total_pages)
                cursor.execute(
                    f"""SELECT asset.id AS asset_id,
                        COALESCE(NULLIF(asset.file_name, ''), 'Asset ' || asset.id::text) AS display_name,
                        {self._MEDIA_SQL} AS media_type,
                        asset.created_at,
                        COALESCE(asset.status, 'approved') AS registration_state,
                        COALESCE(intelligence.analysis_status, 'PENDING') AS readiness,
                        destination.destination,
                        {self._SOURCE_WORKFLOW_SQL} AS source_workflow,
                        COALESCE(
                            NULLIF(photoshoot.user_title, ''),
                            photoshoot.ai_title,
                            photoshoot.display_name,
                            CASE WHEN {self._SESSION_SQL} IS NOT NULL THEN 'Photoshoot Studio' END,
                            'Canonical Asset'
                        ) AS source_name,
                        {self._SESSION_SQL} AS source_session_id,
                        COALESCE(
                            NULLIF(intelligence.profile_data->>'short_description', ''),
                            NULLIF(asset.short_safe_summary, '')
                        ) AS short_description
                        {joins}
                        WHERE {where}
                        ORDER BY {order}
                        LIMIT %s OFFSET %s""",
                    (*params, int(page_size), (current_page - 1) * int(page_size)),
                )
                rows = cursor.fetchall()
        ready = int(summary["ready"] or 0)
        return AvailableInventoryPage(
            items=tuple(self._item(row) for row in rows),
            total=total,
            ready=ready,
            pending=max(0, total - ready),
            page=current_page,
        )

    def _filters(
        self,
        *,
        creator_profile_id: int,
        search: str | None,
        readiness: str | None,
        source: str | None,
        media_type: str | None,
    ) -> tuple[str, list[Any]]:
        filters = [
            "asset.creator_profile_id=%s",
            "COALESCE(asset.is_active, TRUE)=TRUE",
            "COALESCE(asset.is_test, FALSE)=FALSE",
            "COALESCE(asset.status, '')<>'archived'",
            "intelligence.analysis_status='READY'",
            commercial_asset_eligibility_sql("asset"),
            self.content_destinations.available_inventory_predicate("asset.id"),
        ]
        params: list[Any] = [int(creator_profile_id)]
        if search:
            filters.append("""(
                COALESCE(asset.file_name, '') ILIKE %s
                OR COALESCE(asset.short_safe_summary, '') ILIKE %s
                OR COALESCE(intelligence.profile_data->>'short_description', '') ILIKE %s
                OR COALESCE(photoshoot.user_title, photoshoot.ai_title, photoshoot.display_name, '') ILIKE %s
            )""")
            params.extend([f"%{search.strip()}%"] * 4)
        if readiness:
            filters.append("COALESCE(intelligence.analysis_status, 'PENDING')=%s")
            params.append(readiness.upper())
        if source == "photoshoot":
            filters.append(f"{self._SESSION_SQL} IS NOT NULL")
        elif source == "standalone":
            filters.append(f"{self._SESSION_SQL} IS NULL")
        if media_type:
            filters.append(f"({self._MEDIA_SQL})=%s")
            params.append(media_type.lower())
        return " AND ".join(filters), params

    @staticmethod
    def _item(row: dict[str, Any]) -> AvailableInventoryItem:
        return AvailableInventoryItem(
            asset_id=int(row["asset_id"]),
            display_name=str(row["display_name"]),
            media_type=str(row["media_type"]),
            created_at=row.get("created_at"),
            registration_state=str(row["registration_state"]),
            readiness=str(row["readiness"]),
            destination=str(row["destination"]),
            source_workflow=str(row["source_workflow"]),
            source_name=str(row["source_name"]),
            source_session_id=str(row["source_session_id"]) if row.get("source_session_id") else None,
            short_description=row.get("short_description"),
        )
