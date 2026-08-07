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
from app.models.autonomous_sales_progression import ProgressionAssetRole, SellableProgressionAsset
from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootLifecycle, CustomerPhotoshootStatus


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
        self.ownership_conflicts = ()
        self.ownership_insufficiencies = ()

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


class Ownership:
    def __init__(self, repository):
        self.repository = repository

    def answer(self, _identity):
        return SimpleNamespace(
            owned_offering_ids=tuple(self.repository.purchased),
            owned_asset_ids=(),
            conflicts=self.repository.ownership_conflicts,
            insufficiencies=self.repository.ownership_insufficiencies,
        )


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
        ownership_intelligence=Ownership(repository),
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
    ("field", "reason"),
    [
        ("ownership_insufficiencies", "OWNERSHIP_EVIDENCE_INSUFFICIENT"),
        ("ownership_conflicts", "OWNERSHIP_CONFLICT"),
    ],
)
def test_selector_fails_closed_on_uncertain_ownership(field, reason):
    repository = Repository((candidate(),))
    setattr(repository, field, ("test-evidence",))

    result = select(repository)

    assert result.offering_id is None
    assert result.selection_reason is OfferingSelectionReason.NO_ELIGIBLE_OFFERING
    assert reason in result.exclusion_reasons
    assert repository.candidate_calls == 0


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
        ownership_intelligence=Ownership(repository),
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
    assert repository.purchase_calls == 0
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


def test_selector_recommends_aggregated_photoshoot_experience():
    single = candidate(
        title="Sunday Porch",
        photoshoot_identifier="photoshoot-sunday-porch",
        photoshoot_intelligence={"themes": ["warm porch", "slow morning"]},
        asset_ids=[42, 43],
        published_at=NOW - timedelta(days=2),
    )
    alternate_fulfillment = candidate(
        title="Sunday Porch Complete Set",
        offering_type="PHOTOSET",
        destinations=["PHOTOSET"],
        photoshoot_identifier="photoshoot-sunday-porch",
        photoshoot_identifiers=["photoshoot-sunday-porch"],
        photoshoot_intelligence={"mood": ["intimate"]},
        asset_ids=[42, 43, 44],
        published_at=NOW,
    )

    result = select(Repository((single, alternate_fulfillment)))

    experience = result.photoshoot_experience
    assert experience is not None
    assert experience.photoshoot_id == "photoshoot-sunday-porch"
    assert experience.commercial_offering_id == result.offering_id
    assert experience.commercial_offering_id == alternate_fulfillment["offering_id"]
    assert experience.theme == "warm porch"
    assert experience.supporting_asset_ids == (43, 44)
    assert experience.photoshoot_intelligence["photoshoot_mood"] == ("intimate",)
    assert experience.recommendation_score >= 0
    assert "Selected" in experience.recommendation_explanation
    assert result.recommendation_result.candidate_count == 1
    assert result.selector_metadata["recommendationLayer"] == "PHOTOSHOOT_EXPERIENCE"
    assert result.selector_metadata["fulfillmentOfferingId"] == str(result.offering_id)


def test_selector_falls_back_to_offering_when_photoshoot_is_unresolved():
    offering = candidate(title="Legacy Offering", photoshoot_identifier=None)

    result = select(Repository((offering,)))

    assert result.offering_id == offering["offering_id"]
    assert result.photoshoot_experience is None
    assert result.recommendation_result.candidate_count == 1
    assert result.selector_metadata["recommendationLayer"] == (
        "COMMERCIAL_OFFERING_FALLBACK"
    )


def test_active_photoshoot_blocks_every_other_commercial_recommendation():
    customer_id = uuid4(); current = candidate(
        photoshoot_identifier="active-shoot", asset_ids=[42],
    ); other_photo = candidate(
        photoshoot_identifier="other-shoot", asset_ids=[43],
    ); standalone = candidate(asset_ids=[44], photoshoot_identifier=None)
    active = CustomerPhotoshootLifecycle(
        uuid4(), 2, customer_id, "active-shoot", CustomerPhotoshootStatus.ACTIVE,
    )

    class Opportunities:
        def context_for_customer(self, **kwargs): return {"active-shoot": active}

    class Progression:
        def ordered_assets(self, **kwargs):
            return (SellableProgressionAsset(
                42, 1, ProgressionAssetRole.CORE_SESSION,
                offering_id=current["offering_id"], publication_id=current["publication_id"],
                delivery_url=current["delivery_url"],
            ),)

    customer = profile(); customer.customer_commerce_profile_id = customer_id
    result = CommercialOfferingSelectorService(
        repository=Repository((standalone, other_photo, current)),
        clock=lambda: NOW, ownership_intelligence=Ownership(Repository()),
        photoshoot_lifecycle_service=Opportunities(), progression_repository=Progression(),
    ).select(
        creator_profile_id=2, telegram_user_id=22, customer_profile=customer,
        commerce_signal=None, active_purchase_intent=None,
        conversation_context={"primary_sales_channel": "AI_CHAT"},
    )
    assert result.offering_id == current["offering_id"]


def test_photoshoot_teaser_can_never_be_selected_as_a_paid_offering():
    teaser = candidate(
        photoshoot_identifier="protected-shoot",
        asset_content_types=["teaser"],
    )
    result = select(Repository((teaser,)))
    assert result.offering_id is None
    assert "PROTECTED_PHOTOSHOOT_TEASER_NOT_SELLABLE" in result.evaluations[0].exclusion_reasons


def test_objection_stage_blocks_all_commercial_recommendations_during_recovery():
    customer_id = uuid4(); protected = candidate(photoshoot_identifier="active-shoot")
    standalone = candidate(asset_ids=[44], photoshoot_identifier=None)
    objection = CustomerPhotoshootLifecycle(uuid4(), 2, customer_id, "active-shoot", CustomerPhotoshootStatus.OBJECTION)
    class Opportunities:
        def context_for_customer(self, **kwargs): return {"active-shoot": objection}
    customer = profile(); customer.customer_commerce_profile_id = customer_id
    result = CommercialOfferingSelectorService(
        repository=Repository((protected, standalone)), clock=lambda: NOW,
        ownership_intelligence=Ownership(Repository()), photoshoot_lifecycle_service=Opportunities(),
    ).select(creator_profile_id=2, telegram_user_id=22, customer_profile=customer,
             commerce_signal=None, active_purchase_intent=None,
             conversation_context={"primary_sales_channel": "AI_CHAT"})
    assert result.offering_id is None


@pytest.mark.parametrize("status", [
    CustomerPhotoshootStatus.CLOSED,
    CustomerPhotoshootStatus.COMPLETED,
    CustomerPhotoshootStatus.DECLINED,
])
def test_terminal_photoshoot_is_not_automatically_resumed(status):
    customer_id = uuid4(); historical = candidate(photoshoot_identifier="old-shoot")
    available = candidate(asset_ids=[77], photoshoot_identifier=None)
    terminal = CustomerPhotoshootLifecycle(uuid4(), 2, customer_id, "old-shoot", status)
    class Opportunities:
        def context_for_customer(self, **kwargs): return {"old-shoot": terminal}
    customer = profile(); customer.customer_commerce_profile_id = customer_id
    result = CommercialOfferingSelectorService(
        repository=Repository((historical, available)), clock=lambda: NOW,
        ownership_intelligence=Ownership(Repository()),
        photoshoot_lifecycle_service=Opportunities(),
    ).select(
        creator_profile_id=2, telegram_user_id=22, customer_profile=customer,
        commerce_signal=None, active_purchase_intent=None,
        conversation_context={"primary_sales_channel": "AI_CHAT"},
    )
    assert result.offering_id == available["offering_id"]


@pytest.mark.parametrize("available", [
    candidate(asset_ids=[81], photoshoot_identifier="new-shoot"),
    candidate(asset_ids=[82], photoshoot_identifier=None),
    candidate(offering_type="VIDEO", asset_ids=[83], photoshoot_identifier=None),
        candidate(offering_type="BUNDLE", asset_ids=[84, 85], destinations=["BUNDLE", "BUNDLE"],
                  photoshoot_identifier="bundle-shoot", photoshoot_identifiers=["bundle-shoot"],
                  photoshoot_selling_mode="BUNDLE", bundle_teaser_asset_id=184,
                  bundle_teaser_source_asset_id=84, bundle_teaser_registered=True),
])
def test_closed_opportunity_releases_sales_brain_to_every_commercial_type(available):
    customer_id = uuid4(); old = candidate(photoshoot_identifier="old-shoot")
    closed = CustomerPhotoshootLifecycle(uuid4(), 2, customer_id, "old-shoot", CustomerPhotoshootStatus.CLOSED)
    class Opportunities:
        def context_for_customer(self, **kwargs): return {"old-shoot": closed}
    customer = profile(); customer.customer_commerce_profile_id = customer_id
    result = CommercialOfferingSelectorService(
        repository=Repository((old, available)), clock=lambda: NOW,
        ownership_intelligence=Ownership(Repository()), photoshoot_lifecycle_service=Opportunities(),
    ).select(creator_profile_id=2, telegram_user_id=22, customer_profile=customer,
             commerce_signal=None, active_purchase_intent=None,
             conversation_context={"primary_sales_channel": "AI_CHAT"})
    assert result.offering_id == available["offering_id"]


def test_no_eligible_offering_exposes_filtering_summary():
    result = select(Repository((
        candidate(publication_status="FAILED"),
        candidate(delivery_url=None),
    )))
    assert result.offering_id is None
    assert result.selector_metadata["eligibleCount"] == 0
    assert result.selector_metadata["rejectedCount"] == 2
    assert "PUBLICATION_NOT_LIVE" in result.exclusion_reasons


def test_content_wall_bundle_and_member_offerings_are_suppressed_from_chat():
    bundle = candidate(
        offering_type="BUNDLE", asset_ids=[84, 85], destinations=["BUNDLE", "BUNDLE"],
        photoshoot_identifier="bundle-shoot", photoshoot_identifiers=["bundle-shoot"],
        photoshoot_selling_mode="BUNDLE", photoshoot_bundle_sales_channel="CONTENT_WALL",
        bundle_teaser_asset_id=184, bundle_teaser_source_asset_id=84,
        bundle_teaser_registered=True,
    )
    member = candidate(
        photoshoot_identifier="bundle-shoot", photoshoot_selling_mode="BUNDLE",
        photoshoot_bundle_sales_channel="CONTENT_WALL",
    )
    result = select(Repository((bundle, member)))
    assert result.offering_id is None
    assert "BUNDLE_CHANNEL_CONTENT_WALL" in result.exclusion_reasons
    assert "BUNDLE_MEMBER_OFFERING_SUPPRESSED" in result.exclusion_reasons


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
