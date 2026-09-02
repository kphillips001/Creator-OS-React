"""Read-only Customer Workspace HTTP adapter for React."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from fastapi.encoders import jsonable_encoder

from app.api.content_studio import _current_account_id
from app.services.customer_workspace_service import CustomerWorkspaceService
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.customer_interaction_safety_service import CustomerInteractionSafetyService


router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def _workspace_service() -> CustomerWorkspaceService:
    return CustomerWorkspaceService()


def _account_id() -> int:
    account_id = _current_account_id()
    if account_id is None:
        raise HTTPException(status_code=400, detail="Creator account required before using Customers.")
    return int(account_id)


def _customer_identity(customer_id: str):
    account_id = _account_id()
    try:
        parsed_account, user_id = (int(value) for value in str(customer_id).split(":", 1))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=404, detail="Customer not found.") from error
    if parsed_account != account_id:
        raise HTTPException(status_code=404, detail="Customer not found.")
    profile = get_active_creator_profile(str(account_id)) or {}
    if not profile.get("id"):
        raise HTTPException(status_code=409, detail="Active creator profile is required.")
    return int(profile["id"]), account_id, user_id


class CustomerSafetyUpdate(BaseModel):
    safetyStatus: str
    reason: str = Field(min_length=5, max_length=1000)


class AbuseReviewResolution(BaseModel):
    reason: str = Field(min_length=5, max_length=1000)
    reviewedBy: str = Field(default="CREATOR_OS_OPERATOR", min_length=3, max_length=200)


@router.get("")
def list_customers(
    search: str | None = None,
    relationship_stage: str | None = None,
    buyer_tier: str | None = None,
    value_tier: str | None = None,
    customer_health: str | None = None,
    lifecycle: str | None = None,
    retention_risk: str | None = None,
    active_session: bool | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    service = _workspace_service()
    customers = list(service.list_customers(fanvue_account_id=_account_id(), limit=5000))
    needle = str(search or "").strip().lower()
    expected = {
        "relationshipStage": relationship_stage,
        "buyerTier": buyer_tier,
        "valueTier": value_tier,
        "customerHealth": customer_health,
        "lifecycleStage": lifecycle,
        "retentionRisk": retention_risk,
    }
    customers = [
        customer for customer in customers
        if (
            not needle
            or needle in str(customer.get("displayName") or "").lower()
            or needle in str(customer.get("customerId") or "").lower()
            or any(needle in str(identity.get("username") or "").lower() for identity in customer.get("providerIdentities") or ())
        )
        and all(not value or str(customer.get(key) or "").lower() == str(value).lower() for key, value in expected.items())
        and (active_session is None or bool(customer.get("activeBuyerSession")) is active_session)
    ]
    total = len(customers)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    return jsonable_encoder({
        "items": customers[start:start + page_size],
        "summary": service.summarize(customers),
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
    })


@router.get("/{customer_id}")
def customer_details(customer_id: str):
    try:
        customer = _workspace_service().get_customer(customer_id, fanvue_account_id=_account_id())
    except (TypeError, ValueError):
        customer = None
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    creator_id, account_id, user_id = _customer_identity(customer_id)
    safety = CustomerInteractionSafetyService()
    state = safety.repository.get(creator_profile_id=creator_id,
        fanvue_account_id=account_id, fanvue_user_id=user_id)
    decision = safety.decide(creator_profile_id=creator_id,
        fanvue_account_id=account_id, fanvue_user_id=user_id)
    customer["interactionSafety"] = {
        "safetyStatus": decision.safety_status, "decision": decision.code,
        "policyEnabled": decision.policy_enabled,
        "reason": (state or {}).get("reason"),
        "effectiveAt": (state or {}).get("effective_at"),
        "history": safety.repository.history(creator_profile_id=creator_id,
            fanvue_account_id=account_id, fanvue_user_id=user_id),
    }
    return jsonable_encoder(customer)


@router.put("/{customer_id}/safety")
def update_customer_safety(customer_id: str, payload: CustomerSafetyUpdate):
    if _workspace_service().get_customer(customer_id, fanvue_account_id=_account_id()) is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    creator_id, account_id, user_id = _customer_identity(customer_id)
    try:
        CustomerInteractionSafetyService().set_status(
            creator_profile_id=creator_id, fanvue_account_id=account_id,
            fanvue_user_id=user_id, safety_status=payload.safetyStatus,
            reason=payload.reason)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return customer_details(customer_id)


@router.post("/abuse-reviews/{incident_id}/release")
def release_abuse_review(incident_id: str, payload: AbuseReviewResolution):
    from uuid import UUID
    from app.services.customer_abuse_policy_service import CustomerAbusePolicyService
    try:
        profile = get_active_creator_profile(str(_account_id())) or {}
        result = CustomerAbusePolicyService().release(
            incident_id=UUID(incident_id), reviewed_by=payload.reviewedBy,
            reason=payload.reason, creator_profile_id=int(profile.get("id") or 0),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid incident ID.") from error
    if result is None:
        raise HTTPException(status_code=409, detail="Abuse review is not OPEN.")
    return jsonable_encoder(result)


@router.post("/abuse-reviews/{incident_id}/manual-block")
def manually_block_abuse_review(incident_id: str, payload: AbuseReviewResolution):
    from uuid import UUID
    from app.services.customer_abuse_policy_service import CustomerAbusePolicyService
    try:
        profile = get_active_creator_profile(str(_account_id())) or {}
        result = CustomerAbusePolicyService().manual_block(
            incident_id=UUID(incident_id), reviewed_by=payload.reviewedBy,
            reason=payload.reason, creator_profile_id=int(profile.get("id") or 0),
        )
    except ValueError as error:
        raise HTTPException(status_code=400, detail="Invalid incident ID.") from error
    if result is None:
        raise HTTPException(status_code=409, detail="Abuse review is not OPEN.")
    return jsonable_encoder(result)
