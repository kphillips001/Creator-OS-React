from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.customer_commerce_memory import CustomerCommerceMemory
from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer,
    OwnershipAnswerState,
    OwnershipIdentity,
)
from app.repositories.content_unlock_repository import _resolve_asset_ids
from app.services.customer_commerce_memory_service import CustomerCommerceMemoryService
from app.services.realtime_monetization_event_service import RealtimeMonetizationEventService


NOW = datetime(2026, 8, 24, tzinfo=timezone.utc)


def identity(account=2, creator=1):
    return OwnershipIdentity(
        creator_profile_id=creator, fanvue_account_id=account,
        external_fanvue_user_uuid=uuid4(), telegram_user_id=55,
        legacy_fanvue_user_id="77",
    )


def answer(value, assets=(10, 11), offerings=(), products=(), insufficiencies=()):
    return CanonicalOwnershipAnswer(
        identity=value, evidence=(), owned_offering_ids=tuple(offerings),
        owned_product_ids=tuple(products), owned_asset_ids=tuple(assets),
        insufficiencies=tuple(insufficiencies),
        state=OwnershipAnswerState.CONFIRMED_OWNERSHIP if assets else OwnershipAnswerState.NO_DEMONSTRATED_OWNERSHIP,
    )


class Repository:
    def __init__(self, value):
        self.value = value
        self.old_offering = uuid4()
        self.new_offering = uuid4()
        self.product = uuid4()

    def verified_purchase_intents(self, value):
        base = dict(creator_profile_id=value.creator_profile_id,
                    fanvue_account_id=value.fanvue_account_id,
                    expected_price_minor=1200, expected_currency="USD",
                    provider_transaction_order_id="tx", status="PURCHASED",
                    attribution_result="ATTRIBUTED", offering_type="BUNDLE",
                    primary_sales_channel="AI_CHAT", sales_session_id=None,
                    asset_ids=[10, 11], intelligence_profiles=[{"themes": ["lace"]}])
        return (
            {**base, "purchase_intent_id": uuid4(), "commercial_offering_id": self.old_offering,
             "purchased_at": NOW - timedelta(days=365),
             "provider_transaction_order_id": "tx-old"},
            {**base, "purchase_intent_id": uuid4(), "commercial_offering_id": self.new_offering,
             "purchased_at": NOW - timedelta(days=2), "offering_type": "SINGLE_IMAGE",
             "asset_ids": [12], "provider_transaction_order_id": "tx-new",
             "intelligence_profiles": [{"themes": ["lace", "mirror"]}]},
        )

    def valid_entitlements(self, value):
        return ({"id": uuid4(), "product_id": self.product, "status": "active",
                 "source_type": "CONTENT_VAULT", "commerce_provider": "FANVUE",
                 "provider_transaction_id": "ent-tx", "granted_at": NOW - timedelta(days=40),
                 "fulfilled_at": None, "product_type": "PHOTO_SET", "asset_ids": [20, 21]},)

    def legacy_asset_purchases(self, value):
        return ({"id": 8, "content_item_id": 30, "usage_type": "content_unlocked",
                 "content_tag": "vault", "purchase_amount": 0,
                 "fanvue_media_uuid": "media", "purchased_at": NOW - timedelta(days=3)},)

    def unmatched_transactions(self, profile_id):
        return ({"customer_commerce_transaction_id": uuid4(), "fanvue_account_id": 2,
                 "transaction_order_id": "unmatched", "gross_minor": 900,
                 "net_minor": 700, "payment_status": "paid", "purchase_source": "FANVUE",
                 "payment_timestamp": NOW},)


def profile(value):
    return SimpleNamespace(
        customer_commerce_profile_id=uuid4(), purchase_count=7,
        first_purchase_at=NOW - timedelta(days=500), last_purchase_at=NOW,
        lifetime_gross_minor=9000, lifetime_net_minor=7000,
        average_order_value_minor=1285, largest_purchase_minor=2400,
    )


def test_memory_composes_all_authoritative_sources_and_unmatched_financial_evidence():
    value = identity()
    repo = Repository(value)
    service = CustomerCommerceMemoryService(
        repository=repo, ownership_service=SimpleNamespace(answer=lambda _: answer(value)),
        clock=lambda: NOW,
    )
    memory = service.build(identity=value, customer_profile=profile(value))
    assert [event.source_type for event in memory.purchase_events] == [
        "PURCHASE_INTENT", "ENTITLEMENT", "VAULT_UNLOCK", "PURCHASE_INTENT"
    ]
    assert memory.owned_asset_ids == (10, 11)
    assert memory.purchase_count == 7
    assert memory.channels_purchased_through == ("AI_CHAT", "CONTENT_VAULT", "TELEGRAM_WALL")
    assert memory.unmatched_financial_evidence[0]["ownershipCreated"] is False
    assert memory.attribution_insufficiencies[0].startswith("UNMATCHED_PROVIDER_TRANSACTION:")


def test_full_history_contributes_and_recent_affinity_is_weighted_more_strongly():
    value = identity()
    repo = Repository(value)
    memory = CustomerCommerceMemoryService(
        repository=repo, ownership_service=SimpleNamespace(answer=lambda _: answer(value)),
        clock=lambda: NOW,
    ).build(identity=value, customer_profile=profile(value))
    assert memory.affinity.historical_purchase_count == 4
    assert memory.affinity.recent_purchase_count == 2
    assert memory.affinity.offering_type_weights["SINGLE_IMAGE"] > memory.affinity.offering_type_weights["BUNDLE"]
    assert "lace" in memory.affinity.tag_weights


def test_unmatched_transaction_and_ownership_insufficiency_fail_closed_without_assets():
    value = identity()
    repo = Repository(value)
    repo.verified_purchase_intents = lambda _: ()
    repo.valid_entitlements = lambda _: ()
    repo.legacy_asset_purchases = lambda _: ()
    memory = CustomerCommerceMemoryService(
        repository=repo,
        ownership_service=SimpleNamespace(answer=lambda _: answer(value, assets=(), insufficiencies=("TAG_ONLY_LEGACY",))),
        clock=lambda: NOW,
    ).build(identity=value, customer_profile=profile(value))
    assert memory.owned_asset_ids == ()
    assert "TAG_ONLY_LEGACY" in memory.attribution_insufficiencies
    assert len(memory.unmatched_financial_evidence) == 1


class Cursor:
    def __init__(self, batches):
        self.batches = iter(batches)
        self.current = []
        self.calls = []
    def execute(self, sql, params):
        self.calls.append((sql, params)); self.current = next(self.batches)
    def fetchone(self):
        return self.current[0] if self.current else None
    def fetchall(self):
        return self.current


def test_vault_single_resolves_account_scoped_media_to_exact_asset():
    cursor = Cursor([[{"content_item_id": 42}]])
    assets, resolution = _resolve_asset_ids(
        cursor, fanvue_account_id=7, content_item_id=None,
        fanvue_media_uuid="media-1", commercial_offering_id=None,
        provider_resource_id=None,
    )
    assert assets == (42,)
    assert resolution == "ACCOUNT_SCOPED_MEDIA_UPLOAD"
    assert cursor.calls[0][1][0] == 7


def test_vault_bundle_resolves_all_and_only_canonical_offering_members():
    cursor = Cursor([[{"asset_id": 4}, {"asset_id": 9}]])
    assets, resolution = _resolve_asset_ids(
        cursor, fanvue_account_id=7, content_item_id=None,
        fanvue_media_uuid=None, commercial_offering_id=uuid4(),
        provider_resource_id=None,
    )
    assert assets == (4, 9)
    assert resolution == "COMMERCIAL_OFFERING_ASSETS"


def test_ambiguous_or_tag_only_unlock_does_not_create_exact_ownership():
    cursor = Cursor([[{"content_item_id": 4}, {"content_item_id": 9}]])
    assets, resolution = _resolve_asset_ids(
        cursor, fanvue_account_id=7, content_item_id=None,
        fanvue_media_uuid="ambiguous", commercial_offering_id=None,
        provider_resource_id=None,
    )
    assert assets == ()
    assert resolution == "AMBIGUOUS_MEDIA_UPLOAD"
    cursor = Cursor([])
    assert _resolve_asset_ids(cursor, fanvue_account_id=7, content_item_id=None,
                              fanvue_media_uuid=None, commercial_offering_id=None,
                              provider_resource_id=None) == ((), "EXACT_CONTENT_UNAVAILABLE")


def test_realtime_unlock_handler_passes_canonical_scope_and_exact_identifiers(monkeypatch):
    captured = {}
    monkeypatch.setattr("app.services.realtime_monetization_event_service.log_content_unlock",
                        lambda **kwargs: captured.update(kwargs) or {"ownership_resolved": True})
    service = RealtimeMonetizationEventService.__new__(RealtimeMonetizationEventService)
    result = service._handle_unlock_event({
        "fanvue_account_id": 7, "fanvue_user_id": "8", "content_item_id": 42,
        "commercial_offering_id": str(uuid4()), "provider_resource_id": "resource",
        "content_tag": "tag", "fanvue_media_uuid": "media", "amount": 12,
    })
    assert result["success"] is True
    assert captured["fanvue_account_id"] == 7
    assert captured["content_item_id"] == 42
    assert captured["provider_resource_id"] == "resource"


def test_broadcast_send_and_delivery_records_are_not_memory_purchase_sources():
    value = identity()
    repo = Repository(value)
    memory = CustomerCommerceMemoryService(
        repository=repo, ownership_service=SimpleNamespace(answer=lambda _: answer(value)),
        clock=lambda: NOW,
    ).build(identity=value, customer_profile=profile(value))
    assert "PPV_BROADCAST_LOG" not in {event.source_type for event in memory.purchase_events}
    assert "TELEGRAM_SALES_DELIVERY" not in {event.source_type for event in memory.purchase_events}
