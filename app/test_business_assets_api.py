from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import business_assets
from app.models.chat_commerce_inventory import (
    ChatCommerceInventoryItem,
    ChatCommerceInventoryResult,
    ChatCommerceInventorySummary,
)
from app.repositories.commerce_library_repository import CommerceLibraryListItem, CommerceLibraryPage


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
        return SimpleNamespace(asset_id=asset_id, creator_profile_id=7, content_intelligence_status="READY", content_intelligence_ready=True, to_context=lambda: {
            "asset_id": asset_id, "creator_profile_id": 7,
            "commerce_registration_status": "REGISTERED",
        })


class CommerceListRepository:
    def __init__(self):
        self.calls = []

    def list_page(self, **kwargs):
        self.calls.append(kwargs)
        status = "Chat Ready"
        items = () if kwargs.get("commerce_status") and kwargs["commerce_status"] != status else (
            CommerceLibraryListItem(
                item_id="asset:42", item_kind="asset", asset_id=42,
                creator_profile_id=7, asset_name="portrait.png",
                analysis_status="READY", current_lifecycle="CHAT_READY",
                commerce_status=status,
            ),
        )
        return CommerceLibraryPage(items=items, total=len(items), page=1)


def _client(monkeypatch):
    inventory = Inventory()
    listing = CommerceListRepository()
    monkeypatch.setattr(business_assets, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(business_assets, "_inventory_service", lambda: inventory)
    monkeypatch.setattr(business_assets, "_commerce_library_repository", lambda: listing)
    monkeypatch.setattr(business_assets, "_commerce_repository", CommerceRepository)
    monkeypatch.setattr(business_assets, "_photoshoot_repository", lambda: SimpleNamespace(list_active=lambda creator_id: ()))
    api = FastAPI(); api.include_router(business_assets.router)
    return TestClient(api), inventory, listing


def test_lists_existing_inventory_without_mutating_services(monkeypatch):
    client, inventory, listing = _client(monkeypatch)
    response = client.get("/api/v1/business-assets?recommendation_ready=true")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["asset_id"] == 42
    assert body["items"][0]["imageUrl"] == "/api/v1/assets/42/thumbnail"
    assert body["items"][0]["commerceStatus"] == "Chat Ready"
    assert "summary" not in body and "analysisResults" not in str(body)
    assert inventory.calls == []
    assert listing.calls[0]["creator_profile_id"] == 7
    assert listing.calls[0]["page_size"] == 24


def test_returns_composed_read_only_details(monkeypatch):
    client, _, _ = _client(monkeypatch)
    detail = SimpleNamespace(
        creator_profile_id=7,
        item=SimpleNamespace(file_name="portrait.png", media_type="image", classification="premium", status="approved", created_at=None, tags=("portrait",), themes=("studio",)),
    )
    monkeypatch.setattr(business_assets, "_asset_library_service", lambda: SimpleNamespace(get_asset_details=lambda asset_id: detail))
    monkeypatch.setattr(business_assets, "_content_intelligence_repository", lambda: SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(to_context=lambda: {"status": "COMPLETE", "ready": True})))
    monkeypatch.setattr(business_assets, "_asset_intelligence_repository", lambda: SimpleNamespace(list_provider_results=lambda asset_id: (
        SimpleNamespace(provider="nudenet", provider_version="nudenet-1", status="READY", metadata={"stage": "NUDENET"}, normalized_fields={"safety_classification": "SAFE", "keywords": ["FACE_FEMALE"]}, field_confidence={"safety_classification": .91}, raw_response={"must_not": "leak"}),
        SimpleNamespace(provider="gpt-vision", provider_version="vision-1", status="READY", metadata={"stage": "VISION"}, normalized_fields={"short_description": "Studio portrait", "tags": ["portrait"]}, field_confidence={}, raw_response={"must_not": "leak"}),
        SimpleNamespace(provider="grok-vision", provider_version="grok-1", status="READY", metadata={"stage": "GROK"}, normalized_fields={"mood": "calm", "content_summary": "Quiet confidence"}, field_confidence={}, raw_response={"must_not": "leak"}),
    )))
    monkeypatch.setattr(business_assets, "_destination_repository", lambda: SimpleNamespace(list_history=lambda asset_id: (), list_routing_intents=lambda asset_id: ()))
    monkeypatch.setattr(business_assets, "_fulfillment_service", lambda: SimpleNamespace(get_fulfillment_by_asset_id=lambda asset_id: None))
    monkeypatch.setattr(business_assets, "_chat_service", lambda: SimpleNamespace(get_by_asset_id=lambda asset_id: SimpleNamespace(to_context=lambda: {"chat_ready": True, "recommendation_eligible": True})))
    response = client.get("/api/v1/business-assets/42")
    assert response.status_code == 200
    body = response.json()
    assert body["contentIntelligence"]["status"] == "COMPLETE"
    assert body["analysis"] == {"NUDENET": "COMPLETE", "VISION": "COMPLETE", "GROK": "COMPLETE", "CONTENT_INTELLIGENCE": "COMPLETE"}
    assert body["analysisResults"]["NUDENET"] == {"status": "READY", "providerVersion": "nudenet-1", "classification": "SAFE", "confidence": .91, "detectedCategories": ["FACE_FEMALE"]}
    assert body["analysisResults"]["VISION"]["shortDescription"] == "Studio portrait"
    assert body["analysisResults"]["GROK"]["semanticSummary"] == "Quiet confidence"
    assert "raw_response" not in str(body) and "must_not" not in str(body)
    assert body["chatCommerce"]["recommendation_eligible"] is True
    assert body["destination"] == {"history": [], "routingIntents": []}


def test_hides_assets_owned_by_another_creator(monkeypatch):
    client, _, listing = _client(monkeypatch)
    listing.list_page = lambda **kwargs: CommerceLibraryPage(items=(), total=0, page=1)
    response = client.get("/api/v1/business-assets")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_filters_by_projected_commerce_status(monkeypatch):
    client, _, _ = _client(monkeypatch)
    response = client.get("/api/v1/business-assets?commerce_status=Needs%20Upload")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_projects_analysis_failure_instead_of_indefinite_analyzing(monkeypatch):
    client, _, listing = _client(monkeypatch)
    listing.list_page = lambda **kwargs: CommerceLibraryPage(items=(CommerceLibraryListItem(
        item_id="asset:42", item_kind="asset", asset_id=42, creator_profile_id=7,
        asset_name="portrait.png", analysis_status="VISION_FAILED",
        current_lifecycle="INTELLIGENCE_PENDING", commerce_status="Analysis Failed",
    ),), total=1, page=1)

    response = client.get("/api/v1/business-assets")

    assert response.status_code == 200
    item = response.json()["items"][0]
    assert item["analysisStatus"] == "VISION_FAILED"
    assert item["commerceStatus"] == "Analysis Failed"


def test_archives_owned_business_asset_without_deleting_related_data(monkeypatch):
    client, _, _ = _client(monkeypatch)
    archived = SimpleNamespace(
        asset_id=42,
        is_archived=True,
        archived_at="2026-07-20T20:00:00+00:00",
    )
    service = SimpleNamespace(archive_asset=lambda asset_id: archived)
    monkeypatch.setattr(business_assets, "_commerce_service", lambda: service)

    response = client.post("/api/v1/business-assets/42/archive")

    assert response.status_code == 200
    assert response.json() == {
        "assetId": 42,
        "isArchived": True,
        "archivedAt": "2026-07-20T20:00:00+00:00",
    }
