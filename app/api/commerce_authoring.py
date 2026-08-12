"""Authenticated creator-facing Commerce authoring and publish orchestration."""
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel, Field

from app.api.asset_library import _creator_profile
from app.api.commercial_offerings import _payload as offering_payload
from app.api.commercial_publications import (
    ExecutePublicationRequest,
    execute_publication,
)
from app.services.commerce_authoring_service import (
    CommerceAuthoringError,
    CommerceAuthoringService,
)
from app.services.commerce_telegram_vault_service import (
    CommerceTelegramVaultError,
    CommerceTelegramVaultService,
)

router = APIRouter(prefix="/api/v1/commerce-authoring", tags=["commerce-authoring"])


class CreateAuthoringOfferingRequest(BaseModel):
    offeringType: str
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    heroAssetId: int | None = None
    primarySalesChannel: str = "AI_CHAT"
    assetIds: list[int] = Field(min_length=1)
    priceMinor: int
    currency: str = "USD"


class UpdateAuthoringOfferingRequest(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = Field(None, max_length=2000)
    priceMinor: int
    currency: str = "USD"


class PublishTelegramContentVaultRequest(BaseModel):
    marketingText: str | None = Field(None, max_length=500)


def _service():
    return CommerceAuthoringService()


def _telegram_service():
    return CommerceTelegramVaultService()


def _error(error):
    raise HTTPException(
        status_code=409 if error.code.endswith("CONFLICT") or error.code == "LIVE_PRICE_LOCKED" else 400,
        detail={"code": error.code, "message": str(error)},
    ) from error


def _row(row, telegram=None):
    payload = {
        "offeringId": str(row["offering_id"]), "title": row["title"],
        "description": row.get("description"),
        "offeringType": row["offering_type"],
        "heroAssetId": int(row["hero_asset_id"]),
        "heroUrl": f"/api/v1/assets/{row['hero_asset_id']}/thumbnail",
        "assetCount": int(row.get("asset_count") or 0),
        "priceMinor": row.get("price_minor"), "currency": row.get("currency") or "USD",
        "primarySalesChannel": row["primary_sales_channel"],
        "status": row["status"],
        "publicationId": str(row["publication_id"]) if row.get("publication_id") else None,
        "publicationStatus": row.get("publication_status"),
        "provider": row.get("provider"),
        "providerResourceStatus": row.get("provider_resource_status"),
        "publishedAt": row["published_at"].isoformat() if row.get("published_at") else None,
        "updatedAt": row["updated_at"].isoformat(),
        "lastReconciledAt": row["last_reconciled_at"].isoformat() if row.get("last_reconciled_at") else None,
        "reconciliationResult": row.get("reconciliation_result"),
        "lastError": row.get("last_error"),
        "deliveryUrl": row.get("delivery_url"),
    }
    telegram = telegram or {}
    payload.update({
        "telegramVaultStatus": telegram.get("status"),
        "telegramVaultPublishedAt": telegram.get("publishedAt"),
        "telegramVaultLastError": telegram.get("lastError"),
    })
    return payload


@router.get("/summary")
def commerce_summary():
    row = _service().summary(creator_profile_id=int(_creator_profile()["id"]))
    return {key: int(row.get(key) or 0) for key in ("total", "draft", "ready", "live", "archived")}


@router.get("")
def list_commerce(
    search: str | None = Query(None, max_length=200),
    status: str | None = Query(None), offering_type: str | None = Query(None),
    channel: str | None = Query(None), publication_status: str | None = Query(None),
    page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    items, total, current = _service().list_page(
        creator_profile_id=int(_creator_profile()["id"]), search=search,
        status=status, offering_type=offering_type, channel=channel,
        publication_status=publication_status, page=page, page_size=page_size,
    )
    creator_profile_id = int(_creator_profile()["id"])
    telegram = _telegram_service()
    return {"items": [
                _row(item, telegram.status(
                    item["offering_id"], creator_profile_id=creator_profile_id
                ))
                for item in items
            ], "total": total, "page": current,
            "pageSize": page_size, "totalPages": max(1, (total + page_size - 1) // page_size)}


@router.post("", status_code=201)
def create_commerce(request: CreateAuthoringOfferingRequest):
    try:
        offering = _service().create(
            creator_profile_id=int(_creator_profile()["id"]),
            offering_type=request.offeringType, title=request.title,
            description=request.description, hero_asset_id=request.heroAssetId,
            primary_sales_channel=request.primarySalesChannel,
            asset_ids=request.assetIds, price_minor=request.priceMinor,
            currency=request.currency,
        )
    except CommerceAuthoringError as error:
        _error(error)
    return offering_payload(offering)


@router.patch("/{offering_id}")
def edit_commerce(offering_id: UUID, request: UpdateAuthoringOfferingRequest):
    try:
        offering = _service().update(
            offering_id, creator_profile_id=int(_creator_profile()["id"]),
            title=request.title, description=request.description,
            price_minor=request.priceMinor, currency=request.currency,
        )
    except CommerceAuthoringError as error:
        _error(error)
    return offering_payload(offering)


@router.post("/{offering_id}/archive")
def archive_commerce(offering_id: UUID):
    try:
        offering = _service().archive(
            offering_id, creator_profile_id=int(_creator_profile()["id"])
        )
    except CommerceAuthoringError as error:
        _error(error)
    return offering_payload(offering)


@router.post("/{offering_id}/publish", status_code=202)
def publish_commerce(offering_id: UUID, background_tasks: BackgroundTasks):
    try:
        publication = _service().resolve_publication(
            offering_id, creator_profile_id=int(_creator_profile()["id"])
        )
    except CommerceAuthoringError as error:
        _error(error)
    return execute_publication(
        publication.publication_id, ExecutePublicationRequest(),
        background_tasks,
    )


@router.get("/{offering_id}/telegram-content-vault")
def telegram_content_vault_status(offering_id: UUID):
    return _telegram_service().status(
        offering_id, creator_profile_id=int(_creator_profile()["id"])
    )


@router.post("/{offering_id}/telegram-content-vault")
def publish_telegram_content_vault(
    offering_id: UUID, request: PublishTelegramContentVaultRequest,
):
    try:
        result = _telegram_service().publish(
            offering_id,
            creator_profile_id=int(_creator_profile()["id"]),
            marketing_text=request.marketingText,
        )
    except CommerceTelegramVaultError as error:
        raise HTTPException(
              status_code=409 if error.code in {"ALREADY_PUBLISHED", "PUBLISH_IN_PROGRESS"} else 400,
            detail={"code": error.code, "message": str(error)},
        ) from error
    return {
        "status": "PUBLISHED",
        "queueItemId": result.queue_item_id,
        "publishedAt": result.updated_at,
    }
