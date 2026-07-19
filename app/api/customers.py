"""Read-only Customer Workspace HTTP adapter for React."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.api.content_studio import _current_account_id
from app.services.customer_workspace_service import CustomerWorkspaceService


router = APIRouter(prefix="/api/v1/customers", tags=["customers"])


def _workspace_service() -> CustomerWorkspaceService:
    return CustomerWorkspaceService()


def _account_id() -> int:
    account_id = _current_account_id()
    if account_id is None:
        raise HTTPException(status_code=400, detail="Creator account required before using Customers.")
    return int(account_id)


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
    return jsonable_encoder(customer)
