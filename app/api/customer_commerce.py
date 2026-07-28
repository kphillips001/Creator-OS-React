"""Developer-only read API for Customer Commerce Intelligence."""
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from app.api.developer_authorization import require_developer_authorization

from app.api.asset_library import _creator_profile
from app.models.customer_commerce import (
    CustomerCommerceProfile,
    CustomerCommerceStatistics,
)
from app.repositories.customer_commerce_repository import (
    CustomerCommerceRepository,
)


router = APIRouter(
    prefix="/api/v1/developer/customer-commerce",
    tags=["developer-customer-commerce"],
    dependencies=[Depends(require_developer_authorization)],
)


def _profile_payload(item: CustomerCommerceProfile) -> dict:
    return {
        "profileId": str(item.customer_commerce_profile_id),
        "creatorProfileId": item.creator_profile_id,
        "fanvueAccountId": item.fanvue_account_id,
        "externalFanvueUserUuid": str(item.external_fanvue_user_uuid),
        "telegramIdentityMappingId": item.telegram_identity_mapping_id,
        "telegramUserId": item.telegram_user_id,
        "displayName": item.display_name,
        "handle": item.handle,
        "firstSeenAt": item.first_seen_at.isoformat(),
        "lastSeenAt": item.last_seen_at.isoformat(),
        "firstPurchaseAt": (
            item.first_purchase_at.isoformat() if item.first_purchase_at else None
        ),
        "lastPurchaseAt": (
            item.last_purchase_at.isoformat() if item.last_purchase_at else None
        ),
        "lifetimeGrossMinor": item.lifetime_gross_minor,
        "lifetimeNetMinor": item.lifetime_net_minor,
        "purchaseCount": item.purchase_count,
        "averageOrderValueMinor": item.average_order_value_minor,
        "largestPurchaseMinor": item.largest_purchase_minor,
        "lastTransactionOrderId": item.last_transaction_order_id,
        "lastPaymentStatus": item.last_payment_status,
        "lastPurchaseSource": item.last_purchase_source,
        "lastSyncedAt": (
            item.last_synced_at.isoformat() if item.last_synced_at else None
        ),
        "profileState": item.profile_state.value,
        "createdAt": item.created_at.isoformat(),
        "updatedAt": item.updated_at.isoformat(),
    }


def _statistics_payload(item: CustomerCommerceStatistics) -> dict:
    return {
        "profileCount": item.profile_count,
        "buyerCount": item.buyer_count,
        "lifetimeGrossMinor": item.lifetime_gross_minor,
        "lifetimeNetMinor": item.lifetime_net_minor,
        "purchaseCount": item.purchase_count,
        "averageOrderValueMinor": item.average_order_value_minor,
        "largestPurchaseMinor": item.largest_purchase_minor,
    }


@router.get("")
def list_customer_commerce_profiles(
    search: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    creator_profile_id = int(_creator_profile()["id"])
    items, total, current_page = CustomerCommerceRepository().list_profiles(
        creator_profile_id=creator_profile_id,
        search=search,
        page=page,
        page_size=page_size,
    )
    return {
        "items": [_profile_payload(item) for item in items],
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/statistics")
def get_customer_commerce_statistics():
    statistics = CustomerCommerceRepository().get_statistics(
        creator_profile_id=int(_creator_profile()["id"])
    )
    return _statistics_payload(statistics)


@router.get("/{profile_id}")
def get_customer_commerce_profile(profile_id: UUID):
    item = CustomerCommerceRepository().get_by_id(
        profile_id,
        creator_profile_id=int(_creator_profile()["id"]),
    )
    if item is None:
        raise HTTPException(
            status_code=404,
            detail="Customer commerce profile was not found.",
        )
    return _profile_payload(item)
