from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import purchase_intents as api
from app.models.purchase_intent import (
    AttributionResult,
    PurchaseIntent,
    PurchaseIntentStatistics,
    PurchaseIntentStatus,
)
from app.services.purchase_intent_service import PurchaseIntentService


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)


def intent(**changes):
    values = dict(
        purchase_intent_id=uuid4(), creator_profile_id=2,
        fanvue_account_id=7, telegram_identity_mapping_id=11,
        telegram_user_id=22, telegram_chat_id=33,
        external_fanvue_user_uuid=uuid4(), commercial_offering_id=uuid4(),
        commercial_publication_id=uuid4(), provider="FANVUE",
        provider_resource_id="link-1", delivery_url="https://fanvue.com/link-1",
        telegram_message_id=None, conversation_id="conversation-1",
        correlation_id=uuid4(), expected_price_minor=999,
        expected_currency="USD", status=PurchaseIntentStatus.CREATED,
        created_at=NOW, presented_at=None, clicked_at=None,
        expires_at=NOW + timedelta(hours=1), abandoned_at=None,
        purchased_at=None, provider_transaction_order_id=None,
        provider_payment_id=None, provider_event_id=None,
        attribution_result=AttributionResult.PENDING,
        attribution_reason=None, created_metadata={"source": "test"},
        updated_at=NOW,
    )
    values.update(changes)
    return PurchaseIntent(**values)


class MemoryRepository:
    def __init__(self):
        self.items = {}

    def get(self, item_id):
        return self.items.get(item_id)

    def get_active_for_buyer(self, **buyer):
        return next((item for item in self.items.values()
                     if item.creator_profile_id == buyer["creator_profile_id"]
                     and item.fanvue_account_id == buyer["fanvue_account_id"]
                     and item.telegram_user_id == buyer["telegram_user_id"]
                     and item.status in {
                         PurchaseIntentStatus.CREATED,
                         PurchaseIntentStatus.PRESENTED,
                         PurchaseIntentStatus.CLICKED,
                     }), None)

    def create(self, **values):
        item = intent(**values)
        self.items[item.purchase_intent_id] = item
        return item

    def replace_active(self, **values):
        active = self.get_active_for_buyer(**{
            key: values[key] for key in (
                "creator_profile_id", "fanvue_account_id", "telegram_user_id"
            )
        })
        if active:
            self.items[active.purchase_intent_id] = replace(
                active, status=PurchaseIntentStatus.SUPERSEDED
            )
        return self.create(**values)

    def update(self, item_id, **changes):
        item = replace(self.items[item_id], **changes)
        self.items[item_id] = item
        return item

    def mark_presented(self, item_id, *, at, telegram_message_id):
        return self.update(item_id, status=PurchaseIntentStatus.PRESENTED,
                           presented_at=at, telegram_message_id=telegram_message_id)

    def mark_clicked(self, item_id, *, at):
        return self.update(item_id, status=PurchaseIntentStatus.CLICKED, clicked_at=at)

    def mark_unknown(self, item_id, *, reason):
        return self.update(item_id, status=PurchaseIntentStatus.UNKNOWN,
                           attribution_result=AttributionResult.UNKNOWN,
                           attribution_reason=reason)

    def expire_due(self, *, now):
        expired = []
        for item in list(self.items.values()):
            if item.expires_at <= now and item.status in {
                PurchaseIntentStatus.CREATED, PurchaseIntentStatus.PRESENTED,
                PurchaseIntentStatus.CLICKED,
            }:
                expired.append(self.update(
                    item.purchase_intent_id,
                    status=PurchaseIntentStatus.EXPIRED,
                ))
        return expired


class CommerciallyEligible:
    def require_offering_id(self, *_args, **_kwargs): pass


def creation_values(**changes):
    values = dict(
        creator_profile_id=2, fanvue_account_id=7,
        telegram_identity_mapping_id=11, telegram_user_id=22,
        telegram_chat_id=33, external_fanvue_user_uuid=uuid4(),
        commercial_offering_id=uuid4(), commercial_publication_id=uuid4(),
        provider="FANVUE", provider_resource_id="link-1",
        delivery_url="https://fanvue.com/link-1", conversation_id="conversation-1",
        correlation_id=uuid4(), expected_price_minor=999,
        expected_currency="usd", expires_at=NOW + timedelta(hours=1),
        created_metadata={"source": "test"},
    )
    values.update(changes)
    return values


def test_status_lifecycle_and_payment_reference_are_deterministic():
    repository = MemoryRepository()
    service = PurchaseIntentService(
        repository, clock=lambda: NOW,
        commercial_eligibility=CommerciallyEligible(),
    )
    created = service.create_before_presentation(**creation_values())
    assert created.expected_currency == "USD"
    presented = service.confirm_presented(
        created.purchase_intent_id, telegram_message_id=91
    )
    assert presented.status is PurchaseIntentStatus.PRESENTED
    clicked = service.record_click(created.purchase_intent_id)
    assert clicked.status is PurchaseIntentStatus.CLICKED
    referenced = service.record_payment_reference(
        created.purchase_intent_id, transaction_order_id="order-1",
        payment_id="payment-1", event_id="event-1",
    )
    assert referenced.status is PurchaseIntentStatus.CLICKED
    assert referenced.attribution_result is AttributionResult.PENDING
    assert service.record_payment_reference(
        created.purchase_intent_id, transaction_order_id="order-1"
    ) == referenced
    with pytest.raises(ValueError, match="another value"):
        service.record_payment_reference(
            created.purchase_intent_id, transaction_order_id="order-2"
        )


def test_single_active_rule_and_replacement_preserve_history():
    repository = MemoryRepository()
    service = PurchaseIntentService(
        repository, clock=lambda: NOW,
        commercial_eligibility=CommerciallyEligible(),
    )
    first = service.create_before_presentation(**creation_values())
    with pytest.raises(ValueError, match="active"):
        service.create_before_presentation(**creation_values())
    second = service.replace_active_intent(**creation_values(
        commercial_offering_id=uuid4(), provider_resource_id="link-2"
    ))
    assert repository.get(first.purchase_intent_id).status is PurchaseIntentStatus.SUPERSEDED
    assert repository.get(second.purchase_intent_id).status is PurchaseIntentStatus.CREATED
    assert len(repository.items) == 2


def test_expiration_and_unknown_do_not_assign_ownership():
    repository = MemoryRepository()
    service = PurchaseIntentService(
        repository, clock=lambda: NOW,
        commercial_eligibility=CommerciallyEligible(),
    )
    old = intent(expires_at=NOW - timedelta(seconds=1))
    active = intent(expires_at=NOW + timedelta(minutes=5))
    repository.items[old.purchase_intent_id] = old
    repository.items[active.purchase_intent_id] = active
    assert service.expire_due()[0].status is PurchaseIntentStatus.EXPIRED
    assert repository.get(active.purchase_intent_id).status is PurchaseIntentStatus.CREATED
    assert service.expire_due() == []
    repository.items.pop(active.purchase_intent_id)
    pending = service.create_before_presentation(**creation_values())
    unknown = service.mark_unknown(pending.purchase_intent_id, reason="No proof")
    assert unknown.status is PurchaseIntentStatus.UNKNOWN
    assert unknown.attribution_result is AttributionResult.UNKNOWN


def test_observed_lifecycle_events_are_forwarded_to_commerce_learning():
    class Learning:
        def __init__(self):
            self.events = []

        def observe_purchase_intent(
            self, observed_intent, outcome_type, *, source_event_key,
        ):
            self.events.append((
                observed_intent.purchase_intent_id,
                outcome_type,
                source_event_key,
            ))

    repository = MemoryRepository()
    learning = Learning()
    service = PurchaseIntentService(
        repository, learning_service=learning, clock=lambda: NOW,
        commercial_eligibility=CommerciallyEligible(),
    )
    created = service.create_before_presentation(**creation_values())
    service.confirm_presented(created.purchase_intent_id)
    service.record_click(created.purchase_intent_id)

    assert [event[1] for event in learning.events] == [
        "PRESENTED", "OPENED",
    ]
    assert all(
        str(created.purchase_intent_id) in event[2]
        for event in learning.events
    )


def test_migration_structurally_enforces_active_and_provider_uniqueness():
    sql = Path(
        "migrations/forward/20260725_007_purchase_intent_offer_lifecycle.sql"
    ).read_text(encoding="utf-8")
    assert "idx_purchase_intents_active_buyer" in sql
    assert "WHERE status IN ('CREATED','PRESENTED','CLICKED')" in sql
    assert "idx_purchase_intents_provider_transaction" in sql
    assert "ON DELETE RESTRICT" in sql
    assert "DELETE" not in Path(
        "app/repositories/purchase_intent_repository.py"
    ).read_text(encoding="utf-8")


def test_read_only_api_list_detail_and_statistics(monkeypatch):
    sample = intent()

    class FakeRepository:
        def list_page(self, **kwargs):
            return [sample], 1, 1

        def get_statistics(self, **kwargs):
            return PurchaseIntentStatistics(1, 1, 0, 0, 0, 0, 0)

        def get(self, item_id, **kwargs):
            return sample if item_id == sample.purchase_intent_id else None

    monkeypatch.setattr(api, "PurchaseIntentRepository", FakeRepository)
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)
    headers = {"X-Creator-OS-Developer": "true"}
    listed = client.get(
        "/api/v1/developer/purchase-intents", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["status"] == "CREATED"
    assert client.get(
        "/api/v1/developer/purchase-intents/statistics", headers=headers
    ).json()["active"] == 1
    assert client.get(
        f"/api/v1/developer/purchase-intents/{sample.purchase_intent_id}",
        headers=headers,
    ).json()["createdMetadata"] == {"source": "test"}
    assert client.post(
        "/api/v1/developer/purchase-intents", json={}, headers=headers
    ).status_code == 405
