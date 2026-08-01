from types import SimpleNamespace
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commercial_administration
from app.services.legacy_commerce_migration_service import (
    LegacyCommerceDecision,
    LegacyCommerceMigrationReport,
)


class FakeRepository:
    creator_profile_id = None

    def list_page(self, **values):
        self.creator_profile_id = values["creator_profile_id"]
        item = SimpleNamespace(
            purchase_intent_id=UUID("00000000-0000-0000-0000-000000000001"),
            creator_profile_id=7, fanvue_account_id=11,
            telegram_identity_mapping_id=None, telegram_user_id=None,
            telegram_chat_id=None, external_fanvue_user_uuid=None,
            commercial_offering_id=UUID("00000000-0000-0000-0000-000000000002"),
            commercial_publication_id=UUID("00000000-0000-0000-0000-000000000003"),
            provider="FANVUE", provider_resource_id="resource-1",
            delivery_url="https://example.invalid/delivery",
            telegram_message_id=None, conversation_id=None,
            correlation_id=UUID("00000000-0000-0000-0000-000000000004"),
            expected_price_minor=1000, expected_currency="USD",
            status=SimpleNamespace(value="PRESENTED"),
            provider_transaction_order_id=None, provider_payment_id=None,
            provider_event_id=None,
            attribution_result=SimpleNamespace(value="PENDING"),
            attribution_reason=None, purchase_acknowledged_at=None,
            created_metadata={}, created_at=None, presented_at=None,
            clicked_at=None, expires_at=None, abandoned_at=None,
            purchased_at=None, updated_at=None,
        )
        return (item,), 1, 1


def test_purchase_intent_projection_is_read_only_and_creator_scoped(monkeypatch):
    repository = FakeRepository()
    monkeypatch.setattr(commercial_administration, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(commercial_administration, "PurchaseIntentRepository", lambda: repository)
    app = FastAPI(); app.include_router(commercial_administration.router)
    response = TestClient(app).get("/api/v1/commercial-administration/purchase-intents")
    assert response.status_code == 200
    assert response.json()["items"][0]["purchaseIntentId"].endswith("1")
    assert repository.creator_profile_id == 7
    assert {method for route in commercial_administration.router.routes for method in route.methods} == {"GET"}


def test_legacy_migration_status_is_read_only_and_creator_scoped(monkeypatch):
    report = LegacyCommerceMigrationReport(
        mode="REVALIDATE", records_seen=2, writes_performed=0,
        certification_valid=True,
        decisions=tuple(
            LegacyCommerceDecision(
                legacy_record_id=index, creator_profile_id=creator,
                classification="HISTORICAL_ONLY", commerce_action="NONE",
                canonical_asset_id=index, product_id=None, offering_ids=(),
                exclusion_reason="inactive_historical_content",
                source_reference=f"vault/{index}.jpg", active=False,
            )
            for index, creator in ((1, 7), (2, 8))
        ),
    )
    service = SimpleNamespace(run=lambda _mode: report)
    monkeypatch.setattr(commercial_administration, "_creator_profile", lambda: {"id": 7})
    monkeypatch.setattr(commercial_administration, "LegacyCommerceMigrationService", lambda: service)
    app = FastAPI(); app.include_router(commercial_administration.router)

    response = TestClient(app).get("/api/v1/commercial-administration/legacy-commerce-migration")

    assert response.status_code == 200
    assert response.json()["records_seen"] == 1
    assert response.json()["writes_performed"] == 0
    assert response.json()["decisions"][0]["legacy_record_id"] == 1
