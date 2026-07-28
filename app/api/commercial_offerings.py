"""Narrow Commercial Offering CRUD foundation; no selling or publishing."""

from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.asset_library import _creator_profile
from app.services.commercial_offering_service import (
    CommercialOfferingBusinessError,
    CommercialOfferingService,
)


router = APIRouter(prefix="/api/v1/commercial-offerings", tags=["commercial-offerings"])


class CreateOfferingRequest(BaseModel):
    offeringType: str
    title: str
    description: str | None = None
    heroAssetId: int | None = None
    primarySalesChannel: str
    assetIds: list[int] = Field(min_length=1)


class UpdateOfferingMetadataRequest(BaseModel):
    title: str
    description: str | None = None
    heroAssetId: int

class UpdateOfferingPricingRequest(BaseModel):
    priceMinor: int
    currency: str = "USD"


def _service() -> CommercialOfferingService:
    return CommercialOfferingService()


def _payload(offering, *, include_assets=True):
    return {
        "offeringId": str(offering.offering_id),
        "offeringType": offering.offering_type.value,
        "title": offering.title,
        "description": offering.description,
        "heroAssetId": offering.hero_asset_id,
        "heroUrl": f"/api/v1/assets/{offering.hero_asset_id}/thumbnail",
        "primarySalesChannel": offering.primary_sales_channel.value,
        "priceMinor": offering.price_minor,
        "currency": offering.currency,
        "status": offering.status.value,
        "assetCount": len(offering.assets),
        "assets": [
            {"assetId": member.asset_id, "position": member.position, "isHero": member.is_hero}
            for member in offering.assets
        ] if include_assets else [],
        "createdAt": offering.created_at.isoformat(),
        "updatedAt": offering.updated_at.isoformat(),
    }


@router.get("")
def list_offerings(
    search: str | None = Query(None, max_length=200),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    offerings, total, current_page = _service().list(
        creator_profile_id=int(_creator_profile()["id"]), search=search,
        page=page, page_size=page_size,
    )
    return {
        "items": [_payload(item, include_assets=False) for item in offerings],
        "total": total, "page": current_page, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{offering_id}")
def get_offering(offering_id: UUID):
    offering = _service().get(offering_id, creator_profile_id=int(_creator_profile()["id"]))
    if offering is None:
        raise HTTPException(status_code=404, detail="Commercial Offering not found.")
    return _payload(offering)


@router.post("", status_code=201)
def create_offering(request: CreateOfferingRequest):
    try:
        offering = _service().create(
            creator_profile_id=int(_creator_profile()["id"]),
            offering_type=request.offeringType, title=request.title,
            description=request.description, hero_asset_id=request.heroAssetId,
            primary_sales_channel=request.primarySalesChannel, asset_ids=request.assetIds,
        )
    except CommercialOfferingBusinessError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": error.code,
                "message": str(error),
                "requiredAction": error.required_action,
            },
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _payload(offering)


@router.patch("/{offering_id}")
def update_offering(offering_id: UUID, request: UpdateOfferingMetadataRequest):
    try:
        offering = _service().update_metadata(
            offering_id, creator_profile_id=int(_creator_profile()["id"]),
            title=request.title, description=request.description,
            hero_asset_id=request.heroAssetId,
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if offering is None:
        raise HTTPException(status_code=404, detail="Commercial Offering not found.")
    return _payload(offering)

@router.patch("/{offering_id}/pricing")
def update_offering_pricing(offering_id: UUID, request: UpdateOfferingPricingRequest):
    try:
        offering = _service().update_pricing(
            offering_id, creator_profile_id=int(_creator_profile()["id"]),
            price_minor=request.priceMinor, currency=request.currency,
        )
    except CommercialOfferingBusinessError as error:
        raise HTTPException(
            status_code=409,
            detail={
                "code": error.code,
                "message": str(error),
                "requiredAction": error.required_action,
            },
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    if offering is None:
        raise HTTPException(status_code=404, detail="Commercial Offering not found.")
    return _payload(offering)
