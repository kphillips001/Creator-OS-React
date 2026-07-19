from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import customers


def customer_payload(**overrides):
    payload = {
        "customerId": "7:42",
        "displayName": "Avery",
        "providerIdentities": [{"provider": "fanvue", "username": "avery"}],
        "relationshipStatus": "subscriber",
        "relationshipStage": "engaged",
        "buyerTier": "warm",
        "valueTier": "HIGH_VALUE",
        "customerHealth": "HEALTHY",
        "lifecycleStage": "ACTIVE_RELATIONSHIP",
        "totalSpendCents": 4200,
        "purchaseCount": 2,
        "lastActivityAt": "2026-07-19T10:00:00Z",
        "retentionRisk": "HEALTHY",
        "activeBuyerSession": True,
        "nextRecommendedAction": "Continue relationship building",
        "isSubscriber": True,
        "isFollower": True,
    }
    payload.update(overrides)
    return payload


class Workspace:
    def __init__(self):
        self.list_calls = []
        self.detail_calls = []

    def list_customers(self, **kwargs):
        self.list_calls.append(kwargs)
        return (
            customer_payload(),
            customer_payload(customerId="7:43", displayName="Morgan", relationshipStage="dormant", valueTier="NEW", customerHealth="AT_RISK", activeBuyerSession=False),
        )

    def get_customer(self, customer_id, **kwargs):
        self.detail_calls.append((customer_id, kwargs))
        if customer_id != "7:42":
            return None
        return customer_payload(identity={"customer_id": "7:42"}, relationship={"stage": "engaged"}, customerValue={"tier": "HIGH_VALUE"})

    def summarize(self, items):
        values = tuple(items)
        return {"total": len(values), "active": sum(item["relationshipStage"] == "engaged" for item in values)}


def client(monkeypatch):
    workspace = Workspace()
    monkeypatch.setattr(customers, "_current_account_id", lambda: 7)
    monkeypatch.setattr(customers, "_workspace_service", lambda: workspace)
    app = FastAPI()
    app.include_router(customers.router)
    return TestClient(app), workspace


def test_lists_creator_scoped_customer_projections_with_filters(monkeypatch):
    api, workspace = client(monkeypatch)
    response = api.get("/api/v1/customers?search=avery&relationship_stage=engaged&active_session=true")
    assert response.status_code == 200
    body = response.json()
    assert [item["customerId"] for item in body["items"]] == ["7:42"]
    assert body["summary"] == {"total": 1, "active": 1}
    assert workspace.list_calls == [{"fanvue_account_id": 7, "limit": 5000}]


def test_returns_read_only_customer_detail(monkeypatch):
    api, workspace = client(monkeypatch)
    response = api.get("/api/v1/customers/7:42")
    assert response.status_code == 200
    assert response.json()["customerValue"]["tier"] == "HIGH_VALUE"
    assert workspace.detail_calls == [("7:42", {"fanvue_account_id": 7})]


def test_returns_not_found_without_cross_creator_fallback(monkeypatch):
    api, _ = client(monkeypatch)
    response = api.get("/api/v1/customers/8:42")
    assert response.status_code == 404
    assert response.json()["detail"] == "Customer not found."


def test_router_exposes_get_operations_only():
    assert {method for route in customers.router.routes for method in route.methods} == {"GET"}


def test_customer_presentation_does_not_reference_execution_boundaries():
    source = Path("app/services/customer_workspace_service.py").read_text(encoding="utf-8")
    for forbidden in ("ConversationGateway", "TelegramTransport", "FanvueTransport", "MemoryService", "update_user_memory", "fulfill(", "send_message"):
        assert forbidden not in source
