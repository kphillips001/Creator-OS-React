"""Developer-only read API for bot-facing Commerce Signals."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.asset_library import _creator_profile
from app.services.commerce_signal_service import CommerceSignalService


router = APIRouter(
    prefix="/api/v1/developer/commerce-signals",
    tags=["developer-commerce-signals"],
    dependencies=[Depends(require_developer_authorization)],
)


@router.get("")
def get_commerce_signal(
    buyer_uuid: UUID | None = Query(None),
    telegram_user_id: int | None = Query(None, gt=0),
):
    if buyer_uuid is None and telegram_user_id is None:
        raise HTTPException(
            status_code=422,
            detail="buyer_uuid or telegram_user_id is required.",
        )
    signal = CommerceSignalService().get_signal(
        creator_profile_id=int(_creator_profile()["id"]),
        external_fanvue_user_uuid=buyer_uuid,
        telegram_user_id=telegram_user_id,
    )
    if signal is None:
        raise HTTPException(status_code=404, detail="Commerce Signal was not found.")
    return {
        "buyerUuid": signal.buyer_uuid,
        "telegramUserId": signal.telegram_user_id,
        "identityResolved": signal.identity_resolved,
        "lifetimeSpendMinor": signal.lifetime_spend_minor,
        "purchaseCount": signal.purchase_count,
        "lastPurchaseAt": (
            signal.last_purchase_at.isoformat()
            if signal.last_purchase_at else None
        ),
        "currentActiveOfferId": signal.current_active_offer_id,
        "currentOfferStatus": signal.current_offer_status,
        "conversionState": signal.conversion_state,
        "latestTransaction": signal.latest_transaction,
        "attributionState": signal.attribution_state,
        "reconciliationState": signal.reconciliation_state,
    }
