"""Internal, read-only Commercial Fulfillment projection API."""
from uuid import UUID
from fastapi import APIRouter, HTTPException, Query

from app.api.asset_library import _creator_profile
from app.services.commercial_fulfillment_service import CommercialFulfillmentService

router = APIRouter(
    prefix="/api/v1/commercial-fulfillments", tags=["commercial-fulfillments"]
)


def _payload(item):
    return {
        "offeringId": str(item.offering_id), "title": item.title,
        "description": item.description, "offeringType": item.offering_type,
        "primarySalesChannel": item.primary_sales_channel,
        "priceMinor": item.price_minor, "currency": item.currency,
        "heroAssetId": item.hero_asset_id,
        "orderedAssetIds": list(item.ordered_asset_ids),
        "publicationId": str(item.publication_id) if item.publication_id else None,
        "provider": item.provider,
        "providerResourceId": item.provider_resource_id,
        "deliveryUrl": item.delivery_url,
        "publicationStatus": item.publication_status,
        "providerResourceStatus": item.provider_resource_status,
        "lastReconciledAt": (
            item.last_reconciled_at.isoformat() if item.last_reconciled_at else None
        ),
        "publishedAt": item.published_at.isoformat() if item.published_at else None,
        "fulfillable": item.fulfillable,
        "ineligibilityReason": item.ineligibility_reason,
        "eligibleForAiChat": item.eligible_for_ai_chat,
        "eligibleForTelegramWall": item.eligible_for_telegram_wall,
    }


@router.get("")
def list_fulfillments(
    primary_sales_channel: str = Query(...),
    offering_type: str | None = Query(None),
    provider: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        items, total, current = CommercialFulfillmentService().list_fulfillable(
            creator_profile_id=int(_creator_profile()["id"]),
            primary_sales_channel=primary_sales_channel,
            offering_type=offering_type, provider=provider,
            page=page, page_size=page_size,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {
        "items": [_payload(item) for item in items], "total": total,
        "page": current, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{offering_id}")
def get_fulfillment(offering_id: UUID):
    item = CommercialFulfillmentService().get_fulfillment(
        offering_id, creator_profile_id=int(_creator_profile()["id"])
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Commercial Offering not found.")
    return _payload(item)
