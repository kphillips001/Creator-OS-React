"""Read-only Sales Agent observability API."""

from datetime import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.api.customers import _account_id
from app.services.sales_workspace_service import SalesWorkspaceService


router = APIRouter(prefix="/api/v1/sales", tags=["sales"])


def _workspace_service() -> SalesWorkspaceService:
    return SalesWorkspaceService()


def _page(items: list[dict[str, Any]], page: int, page_size: int) -> dict[str, Any]:
    total = len(items); total_pages = max(1, (total + page_size - 1) // page_size); current = min(page, total_pages); start = (current - 1) * page_size
    return {"items": items[start:start + page_size], "total": total, "page": current, "pageSize": page_size, "totalPages": total_pages}


def _after(value: Any, expected: str | None) -> bool:
    if not expected: return True
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")) >= datetime.fromisoformat(expected.replace("Z", "+00:00"))
    except (TypeError, ValueError): return False


def _before(value: Any, expected: str | None) -> bool:
    if not expected: return True
    try: return datetime.fromisoformat(str(value).replace("Z", "+00:00")) <= datetime.fromisoformat(expected.replace("Z", "+00:00"))
    except (TypeError, ValueError): return False


@router.get("/overview")
def sales_overview():
    return jsonable_encoder(_workspace_service().overview(account_id=_account_id()))


@router.get("/decisions")
def sales_decisions(
    search: str | None = None, date_from: str | None = None, date_to: str | None = None,
    customer: str | None = None, provider: str | None = None, sell: bool | None = None,
    authorized: str | None = None, product: str | None = None, asset: str | None = None,
    outcome: str | None = None, page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100),
):
    items = list(_workspace_service().decisions(account_id=_account_id()))
    needle = str(search or "").strip().lower()
    items = [item for item in items if (not needle or any(needle in str(item.get(key) or "").lower() for key in ("customerName", "customerId", "messageSummary", "productId", "assetId", "reason"))) and _after(item.get("timestamp"), date_from) and _before(item.get("timestamp"), date_to) and (not customer or str(item.get("customerId")) == customer) and (not provider or str(item.get("provider")).lower() == provider.lower()) and (sell is None or bool(item.get("sellDecision")) is sell) and (not authorized or str(item.get("authorizationState")).lower() == authorized.lower()) and (not product or str(item.get("productId")) == product) and (not asset or str(item.get("assetId")) == asset) and (not outcome or str(item.get("outcomeState")).lower() == outcome.lower())]
    return jsonable_encoder(_page(items, page, page_size))


@router.get("/decisions/{decision_id}")
def sales_decision_detail(decision_id: str):
    try: item = _workspace_service().decision_detail(decision_id, account_id=_account_id())
    except (TypeError, ValueError): item = None
    if item is None: raise HTTPException(status_code=404, detail="Decision Activity not found.")
    return jsonable_encoder(item)


@router.get("/offers")
def sales_offers(
    search: str | None = None, customer: str | None = None, product: str | None = None,
    asset: str | None = None, offer_type: str | None = None, state: str | None = None,
    date_from: str | None = None, date_to: str | None = None,
    page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=100),
):
    items = list(_workspace_service().offers(account_id=_account_id())); needle = str(search or "").strip().lower()
    items = [item for item in items if (not needle or any(needle in str(item.get(key) or "").lower() for key in ("offerId", "customerId", "productId", "assetId"))) and (not customer or str(item.get("customerId")) == customer) and (not product or str(item.get("productId")) == product) and (not asset or str(item.get("assetId")) == asset) and (not offer_type or str(item.get("offerType")).lower() == offer_type.lower()) and (not state or state.upper() in item.get("states", [])) and _after(item.get("generatedAt"), date_from) and _before(item.get("generatedAt"), date_to)]
    return jsonable_encoder(_page(items, page, page_size))


@router.get("/learning")
def sales_learning():
    return jsonable_encoder(_workspace_service().learning(account_id=_account_id()))
