from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commercial_offering_selector as api
from app.models.commercial_offering_selection import OfferingSelectionReason
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.services.commerce_recommendation_engine import (
    CommerceRecommendationEngine,
)


NOW = datetime(2026, 7, 26, tzinfo=timezone.utc)
BUYER = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


def candidate(**changes):
    values = {
        "offering_id": uuid4(), "creator_profile_id": 2,
        "title": "Private Release", "description": "A private image.",
        "offering_type": "SINGLE_IMAGE",
        "primary_sales_channel": "AI_CHAT", "price_minor": 999,
        "currency": "USD", "hero_asset_id": 42,
        "offering_status": "READY", "created_at": NOW - timedelta(days=2),
        "asset_ids": [42], "destinations": ["SINGLE_PPV"],
        "publication_id": uuid4(), "provider": "FANVUE",
        "external_product_id": "media-link-1",
        "delivery_url": "https://share.fanvue.com/release",
        "publication_status": "LIVE",
        "provider_resource_status": "PRESENT",
        "last_reconciled_at": NOW, "published_at": NOW - timedelta(days=1),
    }
    values.update(changes)
    return values


class Repository:
    def __init__(self, candidates=(), purchased=(), history=(), learning=None):
        self.candidates = tuple(candidates)
        self.purchased = frozenset(purchased)
        self.history = tuple(history)
        self.learning = learning
        self.get_calls = []
        self.candidate_calls = 0
        self.history_calls = 0
        self.purchase_calls = 0

    def list_candidates(self, **kwargs):
        self.candidate_calls += 1
        return self.candidates

    def get_candidate(self, offering_id, **kwargs):
        self.get_calls.append((offering_id, kwargs))
        return next(
            (item for item in self.candidates
             if item["offering_id"] == offering_id),
            None,
        )

    def list_purchased_offering_ids(self, **kwargs):
        self.purchase_calls += 1
        return self.purchased

    def list_recommendation_history(self, **kwargs):
        self.history_calls += 1
        return self.history

    def get_commerce_learning_profile(self, **kwargs):
        return self.learning


def profile(telegram_user_id=22):
    return SimpleNamespace(
        creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_user_uuid=BUYER,
        telegram_user_id=telegram_user_id,
        display_name="Buyer", handle="buyer",
    )


def select(repository, *, active=None):
    return CommercialOfferingSelectorService(
        repository=repository, clock=lambda: NOW,
    ).select(
        creator_profile_id=2, telegram_user_id=22,
        customer_profile=profile(), commerce_signal=None,
        active_purchase_intent=active,
        conversation_context={"primary_sales_channel": "AI_CHAT"},
    )


def test_active_intent_reuses_same_offering():
    other, active_offer = candidate(), candidate()
    active = SimpleNamespace(
        commercial_offering_id=active_offer["offering_id"]
    )
    result = select(Repository((other, active_offer)), active=active)
    assert result.offering_id == active_offer["offering_id"]
    assert result.selection_reason is OfferingSelectionReason.ACTIVE_INTENT
    assert result.selector_metadata["activeIntentApplied"] is True
    assert result.selector_metadata["recommendationTrace"][0][
        "activeIntentMatch"
    ] == 1.0


def test_invalid_active_intent_preserves_no_fallback_behavior():
    valid = candidate()
    invalid_active = candidate(publication_status="FAILED")
    active = SimpleNamespace(
        commercial_offering_id=invalid_active["offering_id"]
    )
    result = select(Repository((valid, invalid_active)), active=active)
    assert result.offering_id is None
    assert result.selection_reason is OfferingSelectionReason.NO_ELIGIBLE_OFFERING
    assert result.recommendation_result.candidate_count == 0


def test_attributed_purchase_excludes_owned_offering():
    owned, available = candidate(), candidate()
    result = select(Repository(
        (owned, available), purchased=(owned["offering_id"],),
    ))
    assert result.offering_id == available["offering_id"]
    rejected = next(
        item for item in result.evaluations
        if item.offering_id == owned["offering_id"]
    )
    assert "OFFERING_ALREADY_PURCHASED" in rejected.exclusion_reasons


@pytest.mark.parametrize(
    ("changes", "reason"),
    [
        ({"publication_status": "DRAFT"}, "PUBLICATION_NOT_LIVE"),
        ({"provider_resource_status": "MISSING"}, "PROVIDER_RESOURCE_NOT_PRESENT"),
        ({"delivery_url": None}, "DELIVERY_URL_MISSING"),
        ({"creator_profile_id": 99}, "CREATOR_MISMATCH"),
        ({"primary_sales_channel": "TELEGRAM_WALL"}, "SALES_CHANNEL_MISMATCH"),
        ({"destinations": ["PHOTOSET"]}, "DESTINATION_NOT_COMMERCIALLY_AVAILABLE"),
        ({"offering_status": "ARCHIVED"}, "OFFERING_ARCHIVED"),
        ({"offering_status": "DRAFT"}, "OFFERING_NOT_ACTIVE"),
        ({"provider": None}, "PROVIDER_NOT_ENABLED"),
    ],
)
def test_deterministic_eligibility_filters(changes, reason):
    result = select(Repository((candidate(**changes),)))
    assert result.offering_id is None
    assert result.selection_reason is OfferingSelectionReason.NO_ELIGIBLE_OFFERING
    assert reason in result.evaluations[0].exclusion_reasons


def test_most_recent_then_stable_uuid_ordering():
    old = candidate(published_at=NOW - timedelta(days=3))
    newest = candidate(published_at=NOW)
    result = select(Repository((old, newest)))
    assert result.offering_id == newest["offering_id"]
    assert result.selection_reason is OfferingSelectionReason.INTELLIGENT_RANKING

    first_id = UUID("00000000-0000-0000-0000-000000000001")
    second_id = UUID("00000000-0000-0000-0000-000000000002")
    tied = select(Repository((
        candidate(offering_id=second_id, published_at=NOW),
        candidate(offering_id=first_id, published_at=NOW),
    )))
    assert tied.offering_id == first_id
    assert tied.selection_reason is OfferingSelectionReason.DEFAULT_ORDER


def test_selector_delegates_only_eligible_candidates_to_recommendation_engine():
    class RecordingEngine(CommerceRecommendationEngine):
        def __init__(self):
            super().__init__()
            self.received = None

        def rank(self, candidates, context, **kwargs):
            self.received = (tuple(candidates), context, kwargs)
            return super().rank(candidates, context, **kwargs)

    valid = candidate()
    invalid = candidate(publication_status="FAILED")
    engine = RecordingEngine()
    result = CommercialOfferingSelectorService(
        repository=Repository((invalid, valid)),
        clock=lambda: NOW,
        recommendation_engine=engine,
    ).select(
        creator_profile_id=2, telegram_user_id=22,
        customer_profile=profile(), commerce_signal=None,
        active_purchase_intent=None,
        conversation_context={"primary_sales_channel": "AI_CHAT"},
    )
    received, ranking_context, options = engine.received
    assert [item.offering_id for item in received] == [valid["offering_id"]]
    assert ranking_context.creator_profile_id == 2
    assert options["rejection_count"] == 1
    assert result.offering_id == valid["offering_id"]
    assert (
        result.selector_metadata["recommendationEngineVersion"]
        == "commerce_recommendation_v2_intelligent"
    )
    assert result.recommendation_result.selected_candidate.offering_id == result.offering_id


def test_selector_enriches_candidates_and_uses_only_attributed_purchase_affinity():
    coastal = candidate(
        title="Coastal Set", published_at=NOW - timedelta(days=20),
        asset_intelligence=[{
            "asset_id": 42,
            "profile_data": {"themes": ["beach"], "keywords": ["sunset"]},
        }],
    )
    studio = candidate(
        title="Studio Set", published_at=NOW,
        asset_intelligence=[{
            "asset_id": 43,
            "profile_data": {"themes": ["studio"]},
        }],
    )
    history = (
        {
            "commercial_offering_id": uuid4(),
            "status": "PURCHASED", "attribution_result": "ATTRIBUTED",
            "offering_type": "SINGLE_IMAGE",
            "presented_at": NOW - timedelta(days=3),
            "purchased_at": NOW - timedelta(days=3),
            "asset_intelligence": [{"themes": ["beach"], "keywords": ["sunset"]}],
        },
        {
            "commercial_offering_id": uuid4(),
            "status": "PURCHASED", "attribution_result": "UNKNOWN",
            "offering_type": "SINGLE_IMAGE",
            "presented_at": NOW - timedelta(days=2),
            "purchased_at": NOW - timedelta(days=2),
            "asset_intelligence": [{"themes": ["studio"]}],
        },
    )
    repository = Repository((studio, coastal), history=history)
    result = CommercialOfferingSelectorService(
        repository=repository, clock=lambda: NOW,
    ).select(
        creator_profile_id=2, telegram_user_id=22,
        customer_profile=profile(), commerce_signal=None,
        active_purchase_intent=None,
        conversation_context={
            "primary_sales_channel": "AI_CHAT",
            "latest_message": "show me a beach sunset",
        },
    )
    assert result.offering_id == coastal["offering_id"]
    recommendation = result.recommendation_result
    selected = recommendation.ranked_candidates[0]
    affinity = next(
        item for item in selected.components if item.key == "customer_affinity"
    )
    assert set(affinity.evidence["matchedTags"]) == {"beach", "sunset"}
    assert "studio" not in affinity.evidence["matchedTags"]
    assert repository.purchase_calls == 1
    assert repository.history_calls == 1
    assert repository.candidate_calls == 1


def test_selector_consumes_persisted_learning_profile():
    coastal = candidate(
        title="Coastal Set", published_at=NOW - timedelta(days=20),
        asset_intelligence=[{
            "asset_id": 42,
            "profile_data": {"themes": ["beach"]},
        }],
    )
    studio = candidate(
        title="Studio Set", published_at=NOW,
        asset_intelligence=[{
            "asset_id": 43,
            "profile_data": {"themes": ["studio"]},
        }],
    )
    learning = SimpleNamespace(
        preferences={
            "themes": {
                "beach": {
                    "score": 1.0, "confidence": 1.0, "observations": 5,
                },
            },
        },
        preferred_offering_type="SINGLE_IMAGE",
        favorite_media_type="SINGLE_IMAGE",
        average_price_minor=999,
        preferred_price_min_minor=999,
        preferred_price_max_minor=999,
        repeat_purchase_frequency=0.6,
        confidence=1.0,
        evidence_count=10,
    )
    result = select(Repository((studio, coastal), learning=learning))

    assert result.offering_id == coastal["offering_id"]
    affinity = next(
        item for item in result.recommendation_result.ranked_candidates[0].components
        if item.key == "customer_affinity"
    )
    assert affinity.evidence["sourceTypes"] == (
        "COMMERCE_LEARNING_PROFILE",
    )


def test_no_eligible_offering_exposes_filtering_summary():
    result = select(Repository((
        candidate(publication_status="FAILED"),
        candidate(delivery_url=None),
    )))
    assert result.offering_id is None
    assert result.selector_metadata["eligibleCount"] == 0
    assert result.selector_metadata["rejectedCount"] == 2
    assert "PUBLICATION_NOT_LIVE" in result.exclusion_reasons


def test_read_only_developer_api(monkeypatch):
    selected = candidate()

    class Customers:
        def list_profiles(self, **kwargs):
            return (profile(),), 1, 1

        def get_by_buyer_uuid(self, **kwargs):
            return profile()

    class Intents:
        def get_active_for_buyer(self, **kwargs):
            return None

    class Signals:
        def get_signal(self, **kwargs):
            return None

    class Selector:
        def select(self, **kwargs):
            return select(Repository((selected,)))

    class Identities:
        def get_by_telegram_user_id(self, telegram_user_id):
            return SimpleNamespace(external_fanvue_user_uuid=BUYER)

    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    monkeypatch.setattr(api, "CustomerCommerceRepository", Customers)
    monkeypatch.setattr(api, "PurchaseIntentRepository", Intents)
    monkeypatch.setattr(api, "CommerceSignalService", Signals)
    monkeypatch.setattr(api, "CommercialOfferingSelectorService", Selector)
    monkeypatch.setattr(api, "TelegramIdentityRepository", Identities)
    application = FastAPI()
    application.include_router(api.router)
    response = TestClient(application).get(
        "/api/v1/developer/offering-selector",
        headers={"X-Creator-OS-Developer": "true"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["selectedOffering"]["offeringId"] == str(
        selected["offering_id"]
    )
    assert body["items"][0]["selectionReason"] == "MOST_RECENT"
    detail = TestClient(application).get(
        "/api/v1/developer/offering-selector/22",
        headers={"X-Creator-OS-Developer": "true"},
    )
    assert detail.status_code == 200
    assert detail.json()["selectedOffering"]["offeringId"] == str(
        selected["offering_id"]
    )
