"""Developer-only, read-only Purchase Intent inspection API."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.asset_library import _creator_profile
from app.models.purchase_intent import PurchaseIntent, PurchaseIntentStatus
from app.repositories.purchase_intent_repository import PurchaseIntentRepository


router = APIRouter(
    prefix="/api/v1/developer/purchase-intents",
    tags=["developer-purchase-intents"],
    dependencies=[Depends(require_developer_authorization)],
)


def _payload(item: PurchaseIntent) -> dict:
    timestamp_fields = (
        "created_at", "presented_at", "clicked_at", "expires_at",
        "abandoned_at", "purchased_at", "updated_at",
    )
    result = {
        "purchaseIntentId": str(item.purchase_intent_id),
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "telegramIdentityMappingId": item.telegram_identity_mapping_id,
        "telegramUserId": item.telegram_user_id,
        "telegramChatId": item.telegram_chat_id,
        "externalFanvueUserUuid": (
            str(item.external_fanvue_user_uuid)
            if item.external_fanvue_user_uuid else None
        ),
        "commercialOfferingId": str(item.commercial_offering_id),
        "commercialPublicationId": str(item.commercial_publication_id),
        "provider": item.provider,
        "providerResourceId": item.provider_resource_id,
        "deliveryUrl": item.delivery_url,
        "telegramMessageId": item.telegram_message_id,
        "conversationId": item.conversation_id,
        "correlationId": str(item.correlation_id),
        "expectedPriceMinor": item.expected_price_minor,
        "expectedCurrency": item.expected_currency,
        "status": item.status.value,
        "providerTransactionOrderId": item.provider_transaction_order_id,
        "providerPaymentId": item.provider_payment_id,
        "providerEventId": item.provider_event_id,
        "attributionResult": item.attribution_result.value,
        "attributionReason": item.attribution_reason,
        "purchaseAcknowledgedAt": (
            item.purchase_acknowledged_at.isoformat()
            if item.purchase_acknowledged_at else None
        ),
        "createdMetadata": item.created_metadata,
    }
    for field in timestamp_fields:
        value = getattr(item, field)
        result["".join(
            [field.split("_")[0]]
            + [part.title() for part in field.split("_")[1:]]
        )] = value.isoformat() if value else None
    return result


@router.get("")
def list_purchase_intents(
    search: str | None = Query(None),
    status: PurchaseIntentStatus | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total, current_page = PurchaseIntentRepository().list_page(
        creator_profile_id=int(_creator_profile()["id"]),
        search=search, status=status, page=page, page_size=page_size,
    )
    return {
        "items": [_payload(item) for item in items],
        "total": total, "page": current_page, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/statistics")
def get_purchase_intent_statistics():
    item = PurchaseIntentRepository().get_statistics(
        creator_profile_id=int(_creator_profile()["id"])
    )
    return {
        "total": item.total, "active": item.active,
        "purchased": item.purchased, "expired": item.expired,
        "abandoned": item.abandoned, "unknown": item.unknown,
        "superseded": item.superseded,
    }


@router.get("/{intent_id}")
def get_purchase_intent(intent_id: UUID):
    item = PurchaseIntentRepository().get(
        intent_id, creator_profile_id=int(_creator_profile()["id"]),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Purchase Intent was not found.")
    return _payload(item)
