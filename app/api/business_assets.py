"""Read-only Business Asset Console HTTP adapter for React."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.api.asset_library import _creator_profile
from app.models.chat_commerce_inventory import ChatCommerceInventoryFilter
from app.repositories.commerce_destination_repository import CommerceDestinationRepository
from app.repositories.commerce_registration_repository import CommerceRegistrationRepository
from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository
from app.services.asset_library_service import AssetLibraryService
from app.services.chat_commerce_inventory_service import ChatCommerceInventoryService
from app.services.chat_commerce_registration_service import ChatCommerceRegistrationService
from app.services.fulfillment_registration_service import FulfillmentRegistrationService


router = APIRouter(prefix="/api/v1/business-assets", tags=["business-assets"])


def _inventory_service() -> ChatCommerceInventoryService:
    return ChatCommerceInventoryService()


def _commerce_repository() -> CommerceRegistrationRepository:
    return CommerceRegistrationRepository()


def _content_intelligence_repository() -> ContentIntelligenceProfileRepository:
    return ContentIntelligenceProfileRepository()


def _destination_repository() -> CommerceDestinationRepository:
    return CommerceDestinationRepository()


def _fulfillment_service() -> FulfillmentRegistrationService:
    return FulfillmentRegistrationService()


def _chat_service() -> ChatCommerceRegistrationService:
    return ChatCommerceRegistrationService()


def _asset_library_service() -> AssetLibraryService:
    return AssetLibraryService()


def _context(value: Any) -> Any:
    if value is None:
        return None
    to_context = getattr(value, "to_context", None)
    if callable(to_context):
        return jsonable_encoder(to_context())
    if is_dataclass(value):
        return jsonable_encoder(asdict(value))
    return jsonable_encoder(value)


def _owned_record(asset_id: int, creator_profile_id: int):
    record = _commerce_repository().get_by_asset_id(int(asset_id))
    if record is None or int(record.creator_profile_id or 0) != creator_profile_id:
        raise HTTPException(status_code=404, detail="Business Asset not found.")
    return record


def _item_payload(item: Any) -> dict[str, Any]:
    payload = _context(item)
    payload["imageUrl"] = f"/api/v1/assets/{int(item.asset_id)}/media"
    return payload


@router.get("")
def list_business_assets(
    search: str | None = None,
    status: str | None = None,
    destination: str | None = None,
    source_workflow: str | None = None,
    chat_ready: bool | None = None,
    fulfillment_ready: bool | None = None,
    recommendation_ready: bool | None = None,
    awaiting_destination: bool | None = None,
    waiting_for_media_link: bool | None = None,
    blocked: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    creator_profile_id = int(_creator_profile()["id"])
    service = _inventory_service()
    result = service.build_inventory(
        filters=ChatCommerceInventoryFilter(
            status=str(status or "").strip() or None,
            destination=str(destination or "").strip() or None,
            source_workflow=str(source_workflow or "").strip() or None,
            chat_ready=chat_ready,
            fulfillment_ready=fulfillment_ready,
            recommendation_ready=recommendation_ready,
            awaiting_destination=awaiting_destination,
            waiting_for_media_link=waiting_for_media_link,
            blocked=blocked,
        ),
        limit=5000,
    )
    records = _commerce_repository()
    items = [
        item
        for item in result.items
        if (
            (record := records.get_by_asset_id(int(item.asset_id))) is not None
            and int(record.creator_profile_id or 0) == creator_profile_id
        )
    ]
    needle = str(search or "").strip().lower()
    if needle:
        items = [
            item for item in items
            if needle in str(item.asset_name or "").lower()
            or needle in str(item.asset_id)
        ]
    summary = service.summarize_items(items)
    total = len(items)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    return {
        "items": [_item_payload(item) for item in items[start:start + page_size]],
        "summary": _context(summary),
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "generatedAt": result.generated_at,
    }


@router.get("/{asset_id}")
def business_asset_details(asset_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    business_asset = _owned_record(asset_id, creator_profile_id)
    inventory = _inventory_service().build_inventory(limit=5000)
    item = next((candidate for candidate in inventory.items if candidate.asset_id == asset_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Business Asset not found.")

    asset = _asset_library_service().get_asset_details(asset_id)
    if asset is None or int(asset.creator_profile_id or 0) != creator_profile_id:
        raise HTTPException(status_code=404, detail="Business Asset not found.")

    intelligence = _content_intelligence_repository().get_by_asset_id(asset_id)
    destinations = _destination_repository()
    fulfillment = _fulfillment_service().get_fulfillment_by_asset_id(asset_id)
    chat = _chat_service().get_by_asset_id(asset_id)
    return {
        "item": _item_payload(item),
        "asset": {
            "assetId": asset_id,
            "fileName": asset.item.file_name,
            "mediaType": asset.item.media_type,
            "classification": asset.item.classification,
            "status": asset.item.status,
            "createdAt": asset.item.created_at,
            "tags": list(asset.item.tags),
            "themes": list(asset.item.themes),
            "imageUrl": f"/api/v1/assets/{asset_id}/media",
        },
        "contentIntelligence": _context(intelligence),
        "commerceRegistration": _context(business_asset),
        "destination": {
            "history": [_context(entry) for entry in destinations.list_history(asset_id)],
            "routingIntents": [_context(intent) for intent in destinations.list_routing_intents(asset_id)],
        },
        "fulfillment": _context(fulfillment),
        "chatCommerce": _context(chat),
    }
