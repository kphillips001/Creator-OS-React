from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import business_assets
from app.models.chat_commerce_inventory import (
    ChatCommerceInventoryItem,
    ChatCommerceInventoryResult,
    ChatCommerceInventorySummary,
)


def _item(asset_id=42):
    return ChatCommerceInventoryItem(
        asset_id=asset_id,
        asset_name="portrait.png",
        source_workflow="photoshoot",
        current_lifecycle="CHAT_READY",
        commerce_destination="CUSTOMER_CONVERSATIONS",
        chat_ready=True,
        fulfillment_ready=True,
        recommendation_ready=True,
        product_ids=("product-1",),
        experience_ids=("experience-1",),
        availability="Chat Ready",
        lifecycle_steps=(("Intelligence", "Complete"), ("Chat", "Ready")),
    )


class Inventory:
    def __init__(self):
        self.calls = []

    def build_inventory(self, **kwargs):
        self.calls.append(kwargs)
        return ChatCommerceInventoryResult(
            items=(_item(),), summary=ChatCommerceInventorySummary(total_business_assets=1)
        )

    def summarize_items(self, items):
        return ChatCommerceInventorySummary(
            total_business_assets=len(items), chat_ready=sum(item.chat_ready for item in items),
            fulfillment_ready=sum(item.fulfillment_ready for item in items),
            recommendation_ready=sum(item.recommendation_ready for item in items),
        )


class CommerceRepository:
    def get_by_asset_id(self, asset_id):
        return SimpleNamespace(asset_id=asset_id, creator_profile_id=7, to_context=lambda: {
            "asset_id": asset_id, "creator_profile_id": 7,
            "commerce_registration_status": "REGISTERED",
        })


def _client(monkeypatch):
    inventory = Inventory()
    monkeypatch.setattr(business_assets, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(business_assets, "_inventory_service", lambda: inventory)
    monkeypatch.setattr(business_assets, "_commerce_repository", CommerceRepository)
    api = FastAPI(); api.include_router(business_assets.router)
    return TestClient(api), inventory


def test_lists_existing_inventory_without_mutating_services(monkeypatch):
    client, inventory = _client(monkeypatch)
    response = client.get("/api/v1/business-assets?recommendation_ready=true")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["asset_id"] == 42
    assert body["items"][0]["recommendation_ready"] is True
    assert body["items"][0]["imageUrl"] == "/api/v1/assets/42/media"
    assert inventory.calls[0]["filters"].recommendation_ready is True


def test_returns_composed_read_only_details(monkeypatch):
    client, _ = _client(monkeypatch)
    detail = SimpleNamespace(
        creator_profile_id=7,
        item=SimpleNamespace(file_name="portrait.png", media_type="image", classification="premium", status="approved", created_at=None, tags=("portrait",), themes=("studio",)),
    )
    monkeypatch.setattr(business_assets, "_asset_library_service", lambda: SimpleNamespace(get_asset_details=lambda asset_id: detail))
    monkeypatch.setattr(business_assets, "_content_intelligence_repository", lambda: SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(to_context=lambda: {"status": "COMPLETE", "ready": True})))
    monkeypatch.setattr(business_assets, "_destination_repository", lambda: SimpleNamespace(list_history=lambda asset_id: (), list_routing_intents=lambda asset_id: ()))
    monkeypatch.setattr(business_assets, "_fulfillment_service", lambda: SimpleNamespace(get_fulfillment_by_asset_id=lambda asset_id: None))
    monkeypatch.setattr(business_assets, "_chat_service", lambda: SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(to_context=lambda: {"chat_ready": True, "recommendation_eligible": True})))
    response = client.get("/api/v1/business-assets/42")
    assert response.status_code == 200
    body = response.json()
    assert body["contentIntelligence"]["status"] == "COMPLETE"
    assert body["chatCommerce"]["recommendation_eligible"] is True
    assert body["destination"] == {"history": [], "routingIntents": []}


def test_hides_assets_owned_by_another_creator(monkeypatch):
    client, _ = _client(monkeypatch)
    monkeypatch.setattr(business_assets, "_commerce_repository", lambda: SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(asset_id=asset_id, creator_profile_id=99)))
    response = client.get("/api/v1/business-assets")
    assert response.status_code == 200
    assert response.json()["items"] == []
