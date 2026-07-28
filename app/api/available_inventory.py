"""Read-only Available Inventory API."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

from app.api.asset_library import _creator_profile
from app.services.available_inventory_service import AvailableInventoryService


router = APIRouter(prefix="/api/v1/available-inventory", tags=["available-inventory"])


class AvailableInventoryItemResponse(BaseModel):
    assetId: int
    displayName: str
    thumbnailUrl: str
    previewUrl: str
    mediaType: str
    createdAt: str | None
    registrationState: str
    readiness: str
    contentDestination: str
    sourceWorkflow: str
    sourceName: str
    sourceSessionId: str | None
    shortDescription: str | None


class AvailableInventoryResponse(BaseModel):
    items: list[AvailableInventoryItemResponse]
    total: int
    ready: int
    pending: int
    page: int
    pageSize: int
    totalPages: int


def _service() -> AvailableInventoryService:
    return AvailableInventoryService()


@router.get("", response_model=AvailableInventoryResponse)
def list_available_inventory(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None, max_length=200),
    readiness: str | None = Query(None),
    source: str | None = Query(None),
    media_type: str | None = Query(None),
    sort: str = Query("newest"),
):
    profile = _creator_profile()
    result = _service().list_page(
        creator_profile_id=int(profile["id"]),
        page=page,
        page_size=page_size,
        search=search,
        readiness=readiness,
        source=source,
        media_type=media_type,
        sort=sort,
    )
    return {
        "items": [
            {
                "assetId": item.asset_id,
                "displayName": item.display_name,
                "thumbnailUrl": f"/api/v1/assets/{item.asset_id}/thumbnail",
                "previewUrl": f"/api/v1/assets/{item.asset_id}/media",
                "mediaType": item.media_type,
                "createdAt": item.created_at.isoformat() if item.created_at else None,
                "registrationState": item.registration_state,
                "readiness": item.readiness,
                "contentDestination": item.destination,
                "sourceWorkflow": item.source_workflow,
                "sourceName": item.source_name,
                "sourceSessionId": item.source_session_id,
                "shortDescription": item.short_description,
            }
            for item in result.items
        ],
        "total": result.total,
        "ready": result.ready,
        "pending": result.pending,
        "page": result.page,
        "pageSize": page_size,
        "totalPages": max(1, (result.total + page_size - 1) // page_size),
    }
