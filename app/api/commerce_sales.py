"""Developer-only API for inspecting AI Commerce Sales eligibility."""
from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.asset_library import _creator_profile
from app.api.developer_authorization import require_developer_authorization
from app.services.commerce_sales_service import (
    CommerceSalesDecisionError,
    CommerceSalesService,
)

router = APIRouter(
    prefix="/api/v1/commerce/sales",
    tags=["commerce-sales"],
    dependencies=[Depends(require_developer_authorization)],
)


def _payload(item):
    return {
        "offeringId": str(item.offering_id),
        "title": item.title,
        "description": item.description,
        "offeringType": item.offering_type,
        "priceMinor": item.price_minor,
        "currency": item.currency,
        "primarySalesChannel": item.primary_sales_channel,
        "heroAssetId": item.hero_asset_id,
        "heroUrl": f"/api/v1/assets/{item.hero_asset_id}/thumbnail",
        "deliveryUrl": item.delivery_url,
        "provider": item.provider,
        "providerResourceId": item.provider_resource_id,
        "publishedAt": item.published_at.isoformat(),
        "status": "FULFILLABLE",
    }


@router.get("")
def list_commerce_sales(
    channel: str = Query("AI_CHAT"),
    offering_type: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    try:
        items, total, current_page = CommerceSalesService().list_eligible_offerings(
            creator_profile_id=int(_creator_profile()["id"]),
            primary_sales_channel=channel,
            requested_media_type=offering_type,
            page=page,
            page_size=page_size,
        )
    except CommerceSalesDecisionError as error:
        raise HTTPException(
            status_code=400,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return {
        "items": [_payload(item) for item in items],
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }
