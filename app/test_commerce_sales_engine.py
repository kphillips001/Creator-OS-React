from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commerce_sales as api
from app.models.commercial_fulfillment import CommercialFulfillment
from app.repositories.commerce_sales_repository import CommerceSalesRepository
from app.services.commerce_sales_service import (
    CommerceSalesDecisionError,
    CommerceSalesService,
)


def fulfillment(**changes):
    values = {
        "offering_id": uuid4(), "title": "Beach Set", "description": "Sunny",
        "offering_type": "PHOTOSET", "primary_sales_channel": "AI_CHAT",
        "price_minor": 999, "currency": "USD", "hero_asset_id": 42,
        "ordered_asset_ids": (42,), "publication_id": uuid4(),
        "provider": "FANVUE", "provider_resource_id": "link-1",
        "delivery_url": "https://fanvue.com/fvml-1",
        "publication_status": "LIVE", "provider_resource_status": "PRESENT",
        "last_reconciled_at": datetime.now(timezone.utc),
        "published_at": datetime.now(timezone.utc), "fulfillable": True,
        "ineligibility_reason": None, "eligible_for_ai_chat": True,
        "eligible_for_telegram_wall": False,
    }
    values.update(changes)
    return CommercialFulfillment(**values)


class Fulfillments:
    def __init__(self, items):
        self.items = tuple(items)
        self.calls = []

    def list_fulfillable(self, **values):
        self.calls.append(values)
        items = self.items
        if values.get("offering_type"):
            items = tuple(
                item for item in items
                if item.offering_type == values["offering_type"]
            )
        return items, len(items), values["page"]


def sales_service(items):
    fulfillments = Fulfillments(items)
    return CommerceSalesService(
        repository=CommerceSalesRepository(fulfillment_service=fulfillments)
    ), fulfillments


def test_only_ai_chat_and_supported_offering_types_are_accepted():
    service, fulfillments = sales_service([fulfillment()])
    items, total, page = service.list_eligible_offerings(
        creator_profile_id=2, primary_sales_channel="AI_CHAT",
        requested_media_type="PHOTOSET",
    )
    assert total == 1 and page == 1 and items[0].primary_sales_channel == "AI_CHAT"
    assert fulfillments.calls[0]["primary_sales_channel"] == "AI_CHAT"
    with pytest.raises(CommerceSalesDecisionError) as telegram:
        service.list_eligible_offerings(
            creator_profile_id=2, primary_sales_channel="TELEGRAM_WALL"
        )
    assert telegram.value.code == "UNSUPPORTED_SALES_CHANNEL"
    with pytest.raises(CommerceSalesDecisionError) as bundle:
        service.list_eligible_offerings(
            creator_profile_id=2, primary_sales_channel="AI_CHAT",
            requested_media_type="BUNDLE",
        )
    assert bundle.value.code == "UNSUPPORTED_OFFERING_TYPE"


@pytest.mark.parametrize(
    "changes",
    [
        {"provider_resource_status": "MISSING", "fulfillable": False},
        {"provider_resource_status": "UNVERIFIED", "fulfillable": False},
        {"publication_status": "ARCHIVED", "fulfillable": False},
        {"delivery_url": None, "fulfillable": False},
    ],
)
def test_sales_engine_defensively_rejects_stale_fulfillment(changes):
    service, _ = sales_service([fulfillment(**changes)])
    with pytest.raises(CommerceSalesDecisionError) as error:
        service.list_eligible_offerings(
            creator_profile_id=2, primary_sales_channel="AI_CHAT"
        )
    assert error.value.code == "INELIGIBLE_FULFILLMENT_PROJECTION"


def test_projection_returns_price_url_and_deterministic_best_result():
    first = fulfillment(title="Newest deterministic result")
    service, _ = sales_service([first])
    result = service.recommend_best(
        creator_profile_id=2, primary_sales_channel="AI_CHAT"
    )
    assert result.title == "Newest deterministic result"
    assert result.price_minor == 999
    assert result.delivery_url == "https://fanvue.com/fvml-1"


class ApiSales:
    def list_eligible_offerings(self, **_values):
        service, _ = sales_service([fulfillment()])
        return service.list_eligible_offerings(
            creator_profile_id=2, primary_sales_channel="AI_CHAT"
        )


def test_commerce_sales_api(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    monkeypatch.setattr(api, "CommerceSalesService", ApiSales)
    app = FastAPI()
    app.include_router(api.router)
    response = TestClient(app).get(
        "/api/v1/commerce/sales?channel=AI_CHAT&offering_type=PHOTOSET",
        headers={"X-Creator-OS-Developer": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["priceMinor"] == 999
    assert body["items"][0]["deliveryUrl"] == "https://fanvue.com/fvml-1"
    assert body["items"][0]["status"] == "FULFILLABLE"


def test_fulfillment_sql_order_is_deterministic():
    source = open(
        "app/repositories/commercial_fulfillment_repository.py", encoding="utf-8"
    ).read()
    assert "offering.created_at DESC, offering.offering_id ASC" in source
