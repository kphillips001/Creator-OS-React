"""Read-only Product Workspace HTTP adapter for React."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.api.asset_library import _creator_profile
from app.services.product_workspace_service import ProductWorkspaceService


router = APIRouter(prefix="/api/v1/products", tags=["products"])


def _workspace_service() -> ProductWorkspaceService:
    return ProductWorkspaceService()


@router.get("")
def list_products(
    search: str | None = None,
    product_status: str | None = None,
    approval_status: str | None = None,
    product_type: str | None = None,
    lifecycle: str | None = None,
    availability: str | None = None,
    publishing_status: str | None = None,
    fulfillment_status: str | None = None,
    recommendation_eligible: bool | None = None,
    origin: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    creator_profile_id = int(_creator_profile()["id"])
    service = _workspace_service()
    products = list(service.list_products(
        creator_profile_id=creator_profile_id,
        include_archived=True,
        limit=5000,
    ))
    needle = str(search or "").strip().lower()
    filters: tuple[tuple[str, str | None], ...] = (
        ("productStatus", product_status),
        ("approvalStatus", approval_status),
        ("productType", product_type),
        ("lifecycleStage", lifecycle),
        ("availabilityStatus", availability),
        ("publishingStatus", publishing_status),
        ("fulfillmentStatus", fulfillment_status),
        ("productOrigin", origin),
    )
    products = [
        product for product in products
        if (
            not needle
            or needle in str(product.get("displayName") or "").lower()
            or needle in str(product.get("internalName") or "").lower()
            or needle in str(product.get("productId") or "").lower()
        )
        and all(not expected or product.get(key) == expected for key, expected in filters)
        and (
            recommendation_eligible is None
            or bool(product["recommendationEligibility"]["eligible"])
            is recommendation_eligible
        )
    ]
    total = len(products)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    return jsonable_encoder({
        "items": products[start:start + page_size],
        "summary": service.summarize(products),
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
    })


@router.get("/{product_id}")
def product_details(product_id: UUID) -> Any:
    creator_profile_id = int(_creator_profile()["id"])
    product = _workspace_service().get_product(
        product_id,
        creator_profile_id=creator_profile_id,
    )
    if product is None:
        raise HTTPException(status_code=404, detail="Product not found.")
    return jsonable_encoder(product)
