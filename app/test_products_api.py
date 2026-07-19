from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import products


PRODUCT_ID = "ac107a53-1548-4414-b243-e68d59672dd8"


def product_payload(**overrides):
    payload = {
        "productId": PRODUCT_ID,
        "creatorProfileId": 7,
        "internalName": "premium-portrait",
        "displayName": "Premium Portrait",
        "description": "A premium portrait.",
        "productType": "SINGLE_IMAGE",
        "deliveryType": "PAID",
        "productStatus": "ACTIVE",
        "approvalStatus": "APPROVED",
        "reviewStatus": "Publishing Review",
        "productOrigin": "AI Product Draft",
        "priceCents": 2499,
        "currency": "USD",
        "fulfillmentStatus": "READY",
        "publishingStatus": "Fanvue URL available",
        "lifecycleStage": "ACTIVE",
        "availabilityStatus": "AVAILABLE",
        "recommendationEligibility": {"eligible": True, "reason": None},
        "assetCount": 1,
        "warnings": [],
    }
    payload.update(overrides)
    return payload


class Workspace:
    def __init__(self):
        self.list_calls = []
        self.detail_calls = []

    def list_products(self, **kwargs):
        self.list_calls.append(kwargs)
        return (product_payload(), product_payload(
            productId="d6c670be-2a66-4cec-b08b-12a420f21d47",
            displayName="Draft Bundle", productStatus="DRAFT",
            approvalStatus="NEEDS_REVIEW", productType="BUNDLE",
            recommendationEligibility={"eligible": False, "reason": "not_active:DRAFT"},
        ))

    def get_product(self, product_id: UUID, **kwargs):
        self.detail_calls.append((product_id, kwargs))
        return product_payload() if str(product_id) == PRODUCT_ID else None

    def summarize(self, items):
        values = tuple(items)
        return {"total": len(values), "active": sum(item["productStatus"] == "ACTIVE" for item in values)}


def client(monkeypatch):
    workspace = Workspace()
    monkeypatch.setattr(products, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(products, "_workspace_service", lambda: workspace)
    app = FastAPI(); app.include_router(products.router)
    return TestClient(app), workspace


def test_lists_creator_scoped_product_projections_with_filters(monkeypatch):
    api, workspace = client(monkeypatch)
    response = api.get("/api/v1/products?search=premium&product_status=ACTIVE&recommendation_eligible=true")
    assert response.status_code == 200
    body = response.json()
    assert [item["productId"] for item in body["items"]] == [PRODUCT_ID]
    assert body["summary"] == {"total": 1, "active": 1}
    assert workspace.list_calls == [{"creator_profile_id": 7, "include_archived": True, "limit": 5000}]


def test_returns_read_only_product_detail(monkeypatch):
    api, workspace = client(monkeypatch)
    response = api.get(f"/api/v1/products/{PRODUCT_ID}")
    assert response.status_code == 200
    assert response.json()["recommendationEligibility"]["eligible"] is True
    assert workspace.detail_calls[0][1] == {"creator_profile_id": 7}


def test_returns_not_found_without_cross_creator_fallback(monkeypatch):
    api, _ = client(monkeypatch)
    response = api.get("/api/v1/products/00000000-0000-0000-0000-000000000000")
    assert response.status_code == 404
    assert response.json()["detail"] == "Product not found."


def test_router_exposes_get_operations_only():
    methods = {
        method
        for route in products.router.routes
        for method in route.methods
    }
    assert methods == {"GET"}
