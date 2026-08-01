"""Thin, creator-scoped read projections required by Commercial Administration."""

from fastapi import APIRouter, Query

from app.api.asset_library import _creator_profile
from app.api.purchase_intents import _payload as purchase_intent_payload
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.legacy_commerce_migration_service import (
    LegacyCommerceMigrationService,
    MigrationMode,
)


router = APIRouter(
    prefix="/api/v1/commercial-administration",
    tags=["commercial-administration"],
)


@router.get("/legacy-commerce-migration")
def legacy_commerce_migration_status():
    """Expose the governed read-only legacy classification report."""
    creator_profile_id = int(_creator_profile()["id"])
    report = LegacyCommerceMigrationService().run(MigrationMode.REVALIDATE)
    payload = report.as_dict()
    payload["decisions"] = [
        item for item in payload["decisions"]
        if item["creator_profile_id"] == creator_profile_id
    ]
    payload["records_seen"] = len(payload["decisions"])
    return payload


@router.get("/purchase-intents")
def list_purchase_intents(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=100),
):
    """Expose canonical Purchase Intents without developer-only authorization."""
    items, total, current_page = PurchaseIntentRepository().list_page(
        creator_profile_id=int(_creator_profile()["id"]),
        search=search,
        status=None,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [purchase_intent_payload(item) for item in items],
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }
