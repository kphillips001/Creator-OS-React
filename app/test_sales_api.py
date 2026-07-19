from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import sales
from app.services.sales_workspace_service import SalesWorkspaceService


def decision(**updates):
    item = {"decisionId": "decision-1", "timestamp": "2026-07-19T12:00:00Z", "customerId": "7:42", "customerName": "Avery", "provider": "fanvue", "messageSummary": "hello", "sellDecision": True, "authorizationState": "unknown", "productId": "product-1", "assetId": "101", "outcomeState": "none_confirmed", "reason": "Offer selected"}
    item.update(updates); return item


class ApiWorkspace:
    def overview(self, **kwargs): return {"metrics": {"decisionActivitiesToday": 0}, "warnings": ["Decision Activity is not a confirmed send."]}
    def decisions(self, **kwargs): return (decision(), decision(decisionId="decision-2", customerName="Morgan", sellDecision=False, productId=None))
    def decision_detail(self, decision_id, **kwargs): return decision() if decision_id == "decision-1" else None
    def offers(self, **kwargs): return ({"offerId": "rec-1", "customerId": "7:42", "productId": "product-1", "assetId": 101, "offerType": "vip", "state": "PURCHASED", "states": ["OFFERED", "PURCHASED"], "generatedAt": "2026-07-19T12:00:00Z"},)
    def learning(self, **kwargs): return {"summary": {"purchases": 1}, "warnings": []}


def client(monkeypatch):
    workspace = ApiWorkspace(); monkeypatch.setattr(sales, "_account_id", lambda: 7); monkeypatch.setattr(sales, "_workspace_service", lambda: workspace)
    app = FastAPI(); app.include_router(sales.router); return TestClient(app)


def test_sales_endpoints_are_read_only_and_creator_scoped(monkeypatch):
    api = client(monkeypatch)
    assert api.get("/api/v1/sales/overview").status_code == 200
    assert api.get("/api/v1/sales/learning").json()["summary"]["purchases"] == 1
    assert api.get("/api/v1/sales/decisions/decision-1").status_code == 200
    assert api.get("/api/v1/sales/decisions/decision-999").status_code == 404
    assert {method for route in sales.router.routes for method in route.methods} == {"GET"}


def test_decision_filters_search_and_pagination(monkeypatch):
    body = client(monkeypatch).get("/api/v1/sales/decisions?search=avery&sell=true&page_size=1").json()
    assert body["total"] == 1 and body["items"][0]["decisionId"] == "decision-1"


def test_offer_filters(monkeypatch):
    body = client(monkeypatch).get("/api/v1/sales/offers?state=PURCHASED&customer=7:42").json()
    assert body["total"] == 1 and body["items"][0]["offerId"] == "rec-1"


class LearningRepo:
    def list_recommendation_events(self):
        return (
            {"event_id": "e1", "recommendation_id": "rec-1", "event_state": "PURCHASED", "asset_id": 101, "product_id": "product-1", "customer_id": "7:42", "provider_account_id": 7, "event_timestamp": "2026-07-19T12:01:00Z", "outcome_metadata": {"net_revenue_cents": 2500}},
            {"event_id": "e2", "recommendation_id": "other", "event_state": "PURCHASED", "asset_id": 202, "customer_id": "8:9", "provider_account_id": 8},
        )
    def list_business_outcomes(self): return ()
    def list_failed_learning_events(self): return ()


class EmptyRepo:
    def list_outcomes(self): return ()
    def list_events(self): return ()


class ContentLearning:
    def list_asset_learning_profiles(self): return ()


class BusinessLearning:
    def build_learning_snapshot(self, **kwargs): return SimpleNamespace(learning_insights=(), learning_recommendations=())


class Customers:
    def get_customer(self, *args, **kwargs): return {"customerId": "7:42", "relationshipStage": "engaged"}
    def list_customers(self, **kwargs): return ()


def workspace():
    row = {"id": 1, "fanvue_account_id": 7, "fanvue_user_id": 42, "fanvue_user_uuid": "fan-42", "route": "sales", "offer_type": "vip", "price": 25, "created_at": "2026-07-19T12:00:00Z", "send_status": "sent", "payload": {"message": "buy it", "send_offer": True, "route": {"route": "sales", "reason": "Buying intent"}, "offer": {"offer_type": "vip", "price": 25, "content": {"asset_id": 101, "product_id": "product-1", "recommendation_id": "rec-1"}}}, "response": {"text": "Here you go"}}
    return SalesWorkspaceService(decision_list_reader=lambda account, limit: (row,), decision_detail_reader=lambda account, activity: row if account == 7 and activity == 1 else None, learning_repository=LearningRepo(), outcome_repository=EmptyRepo(), delivery_repository=EmptyRepo(), content_learning_service=ContentLearning(), business_learning_service=BusinessLearning(), customer_workspace_service=Customers())


def test_decision_activity_never_claims_send_and_preserves_partial_correlation():
    item = workspace().decisions(account_id=7)[0]
    assert item["activityLabel"] == "Decision Activity"
    assert item["authorizationState"] == "unknown"
    assert item["deliveryState"] == "not_confirmed"
    assert item["dataStatus"] == "partial"
    assert all("sent" not in warning.lower() for warning in item["warnings"])


def test_creator_isolation_offer_lifecycle_and_detail():
    service = workspace(); offers = service.offers(account_id=7)
    assert [item["offerId"] for item in offers] == ["rec-1"]
    detail = service.decision_detail("decision-1", account_id=7)
    assert detail["customerContext"]["customerId"] == "7:42"
    assert detail["outcomeAndLearning"]["events"][0]["event_state"] == "PURCHASED"
    assert service.decision_detail("decision-1", account_id=8) is None


def test_empty_data_and_learning_projection():
    service = workspace(); service._list_decisions = lambda account, limit: ()
    assert service.decisions(account_id=7) == ()
    learning = service.learning(account_id=7)
    assert learning["summary"]["purchases"] == 1
    assert learning["topAssets"] == []


def test_sales_observability_has_no_execution_or_mutation_dependencies():
    source = Path("app/services/sales_workspace_service.py").read_text(encoding="utf-8")
    for forbidden in ("ConversationGateway", "DecisionEngine(", "process_message(", "TelegramTransport", "FanvueTransport", "update_user_memory", "record_outcome(", "execute_fulfillment"):
        assert forbidden not in source
