"""Developer-only, read-only Commercial Offering Selector API."""
from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.asset_library import _creator_profile
from app.repositories.customer_commerce_repository import (
    CustomerCommerceRepository,
)
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.repositories.telegram_identity_repository import TelegramIdentityRepository
from app.services.commerce_signal_service import CommerceSignalService
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)


router = APIRouter(
    prefix="/api/v1/developer/offering-selector",
    tags=["developer-commercial-offering-selector"],
    dependencies=[Depends(require_developer_authorization)],
)


def _payload(result, *, profile=None):
    selected_evaluation = next((
        item for item in result.evaluations
        if item.offering_id == result.offering_id
    ), None)
    return {
        "buyer": {
            "externalFanvueBuyerUuid": (
                str(profile.external_fanvue_user_uuid) if profile else None
            ),
            "telegramUserId": (
                profile.telegram_user_id if profile else None
            ),
            "displayName": profile.display_name if profile else None,
            "handle": profile.handle if profile else None,
        },
        "selectedOffering": (
            {
                "offeringId": str(result.offering_id),
                "title": (
                    selected_evaluation.title
                    if selected_evaluation else None
                ),
                "publicationId": str(result.publication_id),
                "publicationProvider": result.publication_provider,
                "deliveryUrl": result.delivery_url,
                "offeringType": result.offering_type,
                "primarySalesChannel": result.primary_sales_channel,
            }
            if result.offering_id else None
        ),
        "selectionReason": result.selection_reason.value,
        "exclusionReasons": list(result.exclusion_reasons),
        "evaluations": [{
            "offeringId": str(item.offering_id),
            "title": item.title,
            "eligible": item.eligible,
            "exclusionReasons": list(item.exclusion_reasons),
            "publicationId": (
                str(item.publication_id) if item.publication_id else None
            ),
            "publicationProvider": item.publication_provider,
            "publicationStatus": item.publication_status,
            "deliveryUrlAvailable": item.delivery_url_available,
            "offeringStatus": item.offering_status,
            "offeringType": item.offering_type,
            "primarySalesChannel": item.primary_sales_channel,
            "publishedAt": item.published_at,
        } for item in result.evaluations],
        "selectorMetadata": dict(result.selector_metadata),
    }


def _select(profile, *, creator_profile_id: int):
    intents = PurchaseIntentRepository()
    active = (
        intents.get_active_for_buyer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=profile.fanvue_account_id,
            telegram_user_id=profile.telegram_user_id,
        )
        if profile.telegram_user_id is not None else None
    )
    signal = CommerceSignalService().get_signal(
        creator_profile_id=creator_profile_id,
        external_fanvue_user_uuid=profile.external_fanvue_user_uuid,
    )
    return CommercialOfferingSelectorService().select(
        creator_profile_id=creator_profile_id,
        telegram_user_id=profile.telegram_user_id,
        customer_profile=profile,
        commerce_signal=signal,
        active_purchase_intent=active,
        conversation_context={"primary_sales_channel": "AI_CHAT"},
    )


@router.get("")
def list_offering_selections(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    creator_profile_id = int(_creator_profile()["id"])
    profiles, total, current_page = CustomerCommerceRepository().list_profiles(
        creator_profile_id=creator_profile_id, search=search,
        page=page, page_size=page_size,
    )
    return {
        "items": [
            _payload(
                _select(profile, creator_profile_id=creator_profile_id),
                profile=profile,
            )
            for profile in profiles
        ],
        "total": total, "page": current_page, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{telegram_user_id}")
def get_offering_selection(telegram_user_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    identity = TelegramIdentityRepository().get_by_telegram_user_id(
        telegram_user_id
    )
    if identity is None:
        raise HTTPException(status_code=404, detail="Telegram identity not found.")
    profile = CustomerCommerceRepository().get_by_buyer_uuid(
        creator_profile_id=creator_profile_id,
        external_fanvue_user_uuid=identity.external_fanvue_user_uuid,
    )
    if profile is None:
        raise HTTPException(
            status_code=404, detail="Customer Commerce profile not found."
        )
    return _payload(
        _select(profile, creator_profile_id=creator_profile_id),
        profile=profile,
    )
