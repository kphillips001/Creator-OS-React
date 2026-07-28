from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import customer_commerce as api
from app.models.customer_commerce import (
    CustomerCommerceProfile,
    CustomerCommerceProfileState,
    CustomerCommerceStatistics,
)
from app.repositories.customer_commerce_repository import (
    CustomerCommerceRepository,
)
from app.services.customer_commerce_service import CustomerCommerceService


NOW = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
BUYER_UUID = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


def profile(**changes):
    values = {
        "customer_commerce_profile_id": uuid4(),
        "creator_profile_id": 2,
        "fanvue_account_id": 7,
        "external_fanvue_user_uuid": BUYER_UUID,
        "telegram_identity_mapping_id": None,
        "telegram_user_id": None,
        "display_name": "Eligible Asp",
        "handle": "eligible-asp-909",
        "first_seen_at": NOW,
        "last_seen_at": NOW,
        "first_purchase_at": None,
        "last_purchase_at": None,
        "lifetime_gross_minor": 0,
        "lifetime_net_minor": 0,
        "purchase_count": 0,
        "average_order_value_minor": 0,
        "largest_purchase_minor": 0,
        "last_transaction_order_id": None,
        "last_payment_status": None,
        "last_purchase_source": None,
        "last_synced_at": None,
        "profile_state": CustomerCommerceProfileState.UNKNOWN,
        "created_at": NOW,
        "updated_at": NOW,
    }
    values.update(changes)
    return CustomerCommerceProfile(**values)


class MemoryRepository:
    def __init__(self):
        self.profile = profile()
        self.transactions = set()

    def get_or_create(self, **values):
        self.profile = replace(
            self.profile,
            display_name=values.get("display_name"),
            handle=values.get("handle"),
            last_seen_at=max(self.profile.last_seen_at, values["seen_at"]),
        )
        return self.profile

    def record_purchase(self, **values):
        transaction_id = values["transaction_order_id"]
        if transaction_id in self.transactions:
            return self.profile, False
        self.transactions.add(transaction_id)
        count = self.profile.purchase_count + 1
        gross = self.profile.lifetime_gross_minor + values["gross_minor"]
        self.profile = replace(
            self.profile,
            first_purchase_at=self.profile.first_purchase_at
            or values["payment_timestamp"],
            last_purchase_at=values["payment_timestamp"],
            lifetime_gross_minor=gross,
            lifetime_net_minor=(
                self.profile.lifetime_net_minor + values["net_minor"]
            ),
            purchase_count=count,
            average_order_value_minor=gross // count,
            largest_purchase_minor=max(
                self.profile.largest_purchase_minor,
                values["gross_minor"],
            ),
            last_transaction_order_id=transaction_id,
            last_payment_status=values["payment_status"],
            last_purchase_source=values["purchase_source"],
            last_synced_at=NOW,
        )
        return self.profile, True


def test_verified_purchase_updates_customer_statistics():
    repository = MemoryRepository()
    result = CustomerCommerceService(repository).record_verified_purchase(
        creator_profile_id=2,
        fanvue_account_id=7,
        external_fanvue_user_uuid=BUYER_UUID,
        gross_minor=300,
        net_minor=240,
        transaction_order_id="FVE-20260724-104266",
        payment_status="pendingBalance",
        purchase_source="mediaLink",
        payment_timestamp=NOW,
        display_name="Eligible Asp",
        handle="eligible-asp-909",
    )
    assert result.transaction_recorded is True
    assert result.profile.purchase_count == 1
    assert result.profile.lifetime_gross_minor == 300
    assert result.profile.lifetime_net_minor == 240
    assert result.profile.average_order_value_minor == 300
    assert result.profile.largest_purchase_minor == 300
    assert result.profile.profile_state is CustomerCommerceProfileState.UNKNOWN


def test_duplicate_transaction_is_idempotent():
    repository = MemoryRepository()
    service = CustomerCommerceService(repository)
    values = {
        "creator_profile_id": 2,
        "fanvue_account_id": 7,
        "external_fanvue_user_uuid": BUYER_UUID,
        "gross_minor": 300,
        "net_minor": 240,
        "transaction_order_id": "FVE-20260724-104266",
        "payment_status": "pendingBalance",
        "purchase_source": "mediaLink",
        "payment_timestamp": NOW,
    }
    first = service.record_verified_purchase(**values)
    duplicate = service.record_verified_purchase(**values)
    assert first.transaction_recorded is True
    assert duplicate.transaction_recorded is False
    assert duplicate.profile.purchase_count == 1
    assert duplicate.profile.lifetime_gross_minor == 300


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("gross_minor", -1),
        ("net_minor", -1),
        ("transaction_order_id", ""),
        ("payment_status", ""),
        ("purchase_source", ""),
    ],
)
def test_invalid_verified_purchase_is_rejected(field, value):
    arguments = {
        "creator_profile_id": 2,
        "fanvue_account_id": 7,
        "external_fanvue_user_uuid": BUYER_UUID,
        "gross_minor": 300,
        "net_minor": 240,
        "transaction_order_id": "transaction-1",
        "payment_status": "succeeded",
        "purchase_source": "mediaLink",
        "payment_timestamp": NOW,
    }
    arguments[field] = value
    with pytest.raises(ValueError):
        CustomerCommerceService(MemoryRepository()).record_verified_purchase(
            **arguments
        )


def test_repository_hydrates_profile_and_has_structural_idempotency():
    item = profile()
    row = {
        **item.__dict__,
        "profile_state": item.profile_state.value,
    }
    assert CustomerCommerceRepository._profile(row) == item
    source = Path(
        "app/repositories/customer_commerce_repository.py"
    ).read_text(encoding="utf-8")
    assert "fanvue_account_id,transaction_order_id" in source
    assert "DO NOTHING" in source


def test_migration_defines_profile_states_and_unique_transactions():
    migration = Path(
        "migrations/forward/20260725_006_customer_commerce_intelligence.sql"
    ).read_text(encoding="utf-8")
    migration += Path(
        "migrations/forward/20260726_011_relationship_mode.sql"
    ).read_text(encoding="utf-8")
    for state in CustomerCommerceProfileState:
        assert f"'{state.value}'" in migration
    assert "UNIQUE (creator_profile_id, external_fanvue_user_uuid)" in migration
    assert "UNIQUE (fanvue_account_id, transaction_order_id)" in migration
    assert "commercial_offering" not in migration


class ApiRepository:
    item = profile(
        first_purchase_at=NOW,
        last_purchase_at=NOW,
        lifetime_gross_minor=300,
        lifetime_net_minor=240,
        purchase_count=1,
        average_order_value_minor=300,
        largest_purchase_minor=300,
        last_transaction_order_id="transaction-1",
        last_payment_status="succeeded",
        last_purchase_source="mediaLink",
    )

    def list_profiles(self, **_values):
        return (self.item,), 1, 1

    def get_by_id(self, *_args, **_values):
        return self.item

    def get_statistics(self, **_values):
        return CustomerCommerceStatistics(1, 1, 300, 240, 1, 300, 300)


def test_read_only_developer_api(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    monkeypatch.setattr(api, "CustomerCommerceRepository", ApiRepository)
    app = FastAPI()
    app.include_router(api.router)
    client = TestClient(app)
    headers = {"X-Creator-OS-Developer": "true"}
    listed = client.get(
        "/api/v1/developer/customer-commerce", headers=headers
    )
    assert listed.status_code == 200
    assert listed.json()["items"][0]["purchaseCount"] == 1
    detail = client.get(
        "/api/v1/developer/customer-commerce/"
        f"{ApiRepository.item.customer_commerce_profile_id}",
        headers=headers,
    )
    assert detail.status_code == 200
    assert detail.json()["lastTransactionOrderId"] == "transaction-1"
    statistics = client.get(
        "/api/v1/developer/customer-commerce/statistics", headers=headers
    )
    assert statistics.status_code == 200
    assert statistics.json()["lifetimeGrossMinor"] == 300
