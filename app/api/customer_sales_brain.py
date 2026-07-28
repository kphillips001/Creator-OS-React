"""Developer-only, read-only Customer Sales Brain API."""
from fastapi import APIRouter, Depends, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.asset_library import _creator_profile
from app.models.customer_sales_decision import CustomerSalesDecision
from app.services.customer_sales_brain_service import CustomerSalesBrainService


router = APIRouter(
    prefix="/api/v1/developer/customer-sales-brain",
    tags=["developer-customer-sales-brain"],
    dependencies=[Depends(require_developer_authorization)],
)


def _payload(item: CustomerSalesDecision):
    return {
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "externalFanvueBuyerUuid": (
            str(item.external_fanvue_buyer_uuid)
            if item.external_fanvue_buyer_uuid else None
        ),
        "telegramUserId": item.telegram_user_id,
        "identityResolved": item.identity_resolved,
        "decision": item.decision.value,
        "reasonCode": item.reason_code.value,
        "reasonSummary": item.reason_summary,
        "buyerStage": item.buyer_stage.value,
        "commerceSignal": dict(item.commerce_signal),
        "activePurchaseIntentId": (
            str(item.active_purchase_intent_id)
            if item.active_purchase_intent_id else None
        ),
        "activeOfferingId": (
            str(item.active_offering_id) if item.active_offering_id else None
        ),
        "activeOfferStatus": item.active_offer_status,
        "activeOfferConversionState": item.active_offer_conversion_state,
        "recommendedOfferingId": (
            str(item.recommended_offering_id)
            if item.recommended_offering_id else None
        ),
        "recommendedPublicationId": (
            str(item.recommended_publication_id)
            if item.recommended_publication_id else None
        ),
        "recommendedDeliveryUrl": item.recommended_delivery_url,
        "sellAllowed": item.sell_allowed,
        "nudgeAllowed": item.nudge_allowed,
        "upsellAllowed": item.upsell_allowed,
        "crossSellAllowed": item.cross_sell_allowed,
        "congratulateAllowed": item.congratulate_allowed,
        "cooldownUntil": (
            item.cooldown_until.isoformat() if item.cooldown_until else None
        ),
        "evaluatedAt": item.evaluated_at.isoformat(),
        "decisionMetadata": dict(item.decision_metadata),
    }


@router.get("")
def list_customer_sales_decisions(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    items, total, current_page = CustomerSalesBrainService().list_decisions(
        creator_profile_id=int(_creator_profile()["id"]),
        search=search, page=page, page_size=page_size,
    )
    return {
        "items": [_payload(item) for item in items],
        "total": total, "page": current_page, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/statistics")
def get_customer_sales_statistics():
    return CustomerSalesBrainService().statistics(
        creator_profile_id=int(_creator_profile()["id"])
    )


@router.get("/{telegram_user_id}")
def get_customer_sales_decision(
    telegram_user_id: int,
):
    return _payload(
        CustomerSalesBrainService().evaluate_for_telegram_user(
            creator_profile_id=int(_creator_profile()["id"]),
            telegram_user_id=telegram_user_id,
        )
    )
