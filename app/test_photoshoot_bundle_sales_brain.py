from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus
from app.models.customer_sales_decision import (
    CustomerBuyerStage, CustomerSalesDecisionType, CustomerSalesReasonCode,
)
from app.models.ownership_intelligence import OwnershipIdentity
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.commercial_offering_selector_service import CommercialOfferingSelectorService
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_purchase_intent_service import TelegramPurchaseIntentService
from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService
from app.services.photoshoot_bundle_sales_context_service import (
    PhotoshootBundleSalesContextService,
)


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)
BUYER = uuid4()
CUSTOMER = uuid4()
LIFECYCLE = uuid4()


class Photoshoots:
    channel = "CHAT"

    def get_by_session(self, session_id):
        return {
            "deliverable_id": uuid4(), "photoshoot_session_id": session_id,
            "selling_mode": "BUNDLE", "display_name": "After Hours",
            "bundle_sales_channel": self.channel,
            "commercial_intelligence_status": "READY",
            "commercial_intelligence_stage": "COMPLETE",
            "intelligence_profile": {
                "commercial_title": "After Hours", "subtitle": "A private sequence",
                "commercial_summary": "A complete cinematic experience.",
                "theme": "after hours", "buyer_profile": {"audience": "collector"},
                "sales_strategy": {"positioning": "complete set"},
                "sales_brain_brief": "Sell the complete experience.",
            },
        }


class Preparation:
    status = "READY"
    link = "https://test.invalid/bundle"

    def inspect(self, deliverable_id, **kwargs):
        return {
            "status": self.status, "offeringId": "offer-1",
            "publicationId": "publication-1", "deliveryUrl": self.link,
            "mediaLinkUuid": "media-link-1", "priceMinor": 2500,
            "currency": "USD",
        }


class Teasers:
    status = "READY"
    asset_id = 90

    def inspect(self, deliverable_id, **kwargs):
        return {
            "status": self.status, "teaserAssetId": self.asset_id,
            "sourceAssetId": 11, "previewUrl": "/assets/90/media",
        }


class Ownership:
    purchased = False
    owned_count = 0

    def inspect(self, deliverable_id, **kwargs):
        return {
            "bundleOfferingId": "offer-1", "paidAssetIds": [11, 12, 13, 14, 15],
            "purchased": self.purchased, "purchasedAt": None,
            "ownedPaidAssetCount": self.owned_count,
            "ownershipState": "NO_DEMONSTRATED_OWNERSHIP",
        }


class Assets:
    def get_by_id(self, asset_id):
        return SimpleNamespace(asset_id=asset_id)


class Media:
    available = True

    def resolve_original(self, asset, require_exists=True):
        return SimpleNamespace(
            path="C:/test/teaser.png" if self.available else None,
            source="test",
        )


def context_service():
    return PhotoshootBundleSalesContextService(
        photoshoots=Photoshoots(), preparation=Preparation(),
        teasers=Teasers(), ownership=Ownership(), assets=Assets(), media=Media(),
    )


def identity():
    return OwnershipIdentity(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_user_uuid=BUYER, telegram_user_id=3,
    )


def test_ready_bundle_context_uses_teaser_and_one_canonical_offer():
    context = context_service().build(
        "shoot-1", identity=identity(), lifecycle_id=LIFECYCLE,
    )
    assert context["schemaVersion"] == "photoshoot_bundle_conversation_v1"
    assert context["eligible"] is True
    assert context["presentationPhase"] == "COMPLETE_PRESENTATION"
    assert context["promotionalTeaser"]["assetId"] == 90
    assert context["promotionalTeaser"]["sourceAssetId"] == 11
    assert context["bundleOffer"] == {
        "offeringId": "offer-1", "offeringType": "BUNDLE",
        "priceMinor": 2500, "currency": "USD",
        "publicationId": "publication-1", "provider": "FANVUE",
        "providerResourceId": "media-link-1",
        "mediaLink": "https://test.invalid/bundle", "paidMemberCount": 5,
    }
    assert "C:/test/teaser.png" not in context["promptBlock"]


def test_content_wall_bundle_fails_closed_before_chat_presentation():
    original = Photoshoots.channel
    try:
        Photoshoots.channel = "CONTENT_WALL"
        context = context_service().build("shoot-1", identity=identity())
        assert context["eligible"] is False
        assert context["bundleSalesChannel"] == "CONTENT_WALL"
        assert "BUNDLE_CHANNEL_CONTENT_WALL" in context["ineligibilityReasons"]
    finally:
        Photoshoots.channel = original


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda: setattr(Preparation, "status", "NEEDS_ATTENTION"), "BUNDLE_MEDIA_NOT_READY"),
        (lambda: setattr(Preparation, "link", None), "BUNDLE_MEDIA_NOT_READY"),
        (lambda: setattr(Teasers, "status", "NOT_CONFIGURED"), "BUNDLE_TEASER_NOT_READY"),
        (lambda: setattr(Teasers, "asset_id", None), "BUNDLE_TEASER_NOT_READY"),
        (lambda: setattr(Media, "available", False), "BUNDLE_TEASER_NOT_READY"),
    ],
)
def test_bundle_readiness_fails_closed(mutation, reason):
    originals = (Preparation.status, Preparation.link, Teasers.status,
                 Teasers.asset_id, Media.available)
    try:
        mutation()
        result = context_service().build("shoot-1", identity=identity())
        assert result["eligible"] is False
        assert reason in result["ineligibilityReasons"]
    finally:
        Preparation.status, Preparation.link, Teasers.status, Teasers.asset_id, Media.available = originals


@pytest.mark.parametrize(
    ("media_ready", "teaser_ready", "eligible"),
    [(False, False, False), (True, False, False),
     (False, True, False), (True, True, True)],
)
def test_combined_bundle_sellability_requires_both_components(
    media_ready, teaser_ready, eligible,
):
    originals = (Preparation.status, Teasers.status)
    try:
        Preparation.status = "READY" if media_ready else "NEEDS_ATTENTION"
        Teasers.status = "READY" if teaser_ready else "NOT_CONFIGURED"
        result = context_service().build("shoot-1", identity=identity())
        assert result["eligible"] is eligible
    finally:
        Preparation.status, Teasers.status = originals


def test_partial_and_independent_full_ownership_never_fabricate_purchase():
    original = Ownership.owned_count
    try:
        Ownership.owned_count = 1
        partial = context_service().build("shoot-1", identity=identity())
        assert "BUNDLE_PARTIALLY_OWNED" in partial["ineligibilityReasons"]
        assert partial["ownership"]["purchased"] is False
        Ownership.owned_count = 5
        full = context_service().build("shoot-1", identity=identity())
        assert "BUNDLE_FULLY_OWNED" in full["ineligibilityReasons"]
        assert full["ownership"]["purchased"] is False
    finally:
        Ownership.owned_count = original


@pytest.mark.parametrize(
    ("owned_count", "purchased", "reason", "eligible"),
    [
        (0, False, None, True),
        (1, False, "BUNDLE_PARTIALLY_OWNED", False),
        (4, False, "BUNDLE_PARTIALLY_OWNED", False),
        (5, False, "BUNDLE_FULLY_OWNED", False),
        (5, True, "BUNDLE_ALREADY_PURCHASED", False),
    ],
)
def test_bundle_overlap_policy_matrix(owned_count, purchased, reason, eligible):
    original = (Ownership.owned_count, Ownership.purchased)
    try:
        Ownership.owned_count, Ownership.purchased = owned_count, purchased
        result = context_service().build("shoot-1", identity=identity())
        assert result["eligible"] is eligible
        if reason:
            assert reason in result["ineligibilityReasons"]
    finally:
        Ownership.owned_count, Ownership.purchased = original


class Customers:
    profile = SimpleNamespace(customer_commerce_profile_id=CUSTOMER)

    def get_by_buyer_uuid(self, **kwargs):
        return self.profile


class Lifecycles:
    lifecycle = SimpleNamespace(
        lifecycle_id=LIFECYCLE, photoshoot_id="shoot-1",
        status=CustomerPhotoshootStatus.ACTIVE,
    )

    def context_for_customer(self, **kwargs):
        return {}

    def resolve_recommendation(self, **kwargs):
        return self.lifecycle

    def bundle_teaser_presented(self, lifecycle):
        return False


class BundleContext:
    def resolve_mode(self, session_id):
        return "BUNDLE"

    def build(self, session_id, **kwargs):
        return {
            "eligible": True, "ineligibilityReasons": [],
            "presentationPhase": "COMPLETE_PRESENTATION",
            "lifecycleId": str(LIFECYCLE),
            "photoshoot": {"photoshootSessionId": session_id},
            "promotionalTeaser": {"assetId": 90, "sourceAssetId": 11},
            "bundleOffer": {"offeringId": str(OFFERING)},
            "ownership": {"purchased": False},
            "_delivery": {"teaserAssetPath": "C:/test/teaser.png"},
        }


class ContentWallBundleContext(BundleContext):
    def build(self, session_id, **kwargs):
        return {
            "eligible": False,
            "ineligibilityReasons": ["BUNDLE_CHANNEL_CONTENT_WALL"],
            "bundleSalesChannel": "CONTENT_WALL",
            "presentationPhase": "PROMOTIONAL_TEASER",
            "lifecycleId": str(LIFECYCLE),
            "photoshoot": {"photoshootSessionId": session_id},
            "promotionalTeaser": {"assetId": 90, "sourceAssetId": 11},
            "bundleOffer": {"offeringId": str(OFFERING)},
            "_delivery": {"teaserAssetPath": "C:/test/teaser.png"},
        }


class Firewall:
    calls = 0

    def evaluate(self, **kwargs):
        self.calls += 1
        raise AssertionError("Session Runtime must not run for Bundle mode")

    def ordered_assets(self, **kwargs):
        self.calls += 1
        raise AssertionError("Session progression must not run for Bundle mode")

    def decide(self, **kwargs):
        self.calls += 1
        raise AssertionError("Autonomous Session progression must not run")


OFFERING = uuid4()
PUBLICATION = uuid4()


def test_sales_brain_dispatches_bundle_before_every_session_service():
    firewall = Firewall()
    service = CustomerSalesBrainService(
        customer_repository=Customers(), photoshoot_lifecycle_service=Lifecycles(),
        bundle_sales_context_service=BundleContext(),
        session_runtime_service=firewall, progression_repository=firewall,
        autonomous_progression_service=firewall,
    )
    experience = SimpleNamespace(
        photoshoot_id="shoot-1", recommendation_explanation="test",
    )
    recommendation = SimpleNamespace(
        offering_id=OFFERING, publication_id=PUBLICATION,
        delivery_url="https://test.invalid/bundle", title="Bundle",
        short_description="Complete set", price_minor=2500, currency="USD",
        photoshoot_experience=experience,
    )
    result = service._finish(
        0.0, NOW, creator_profile_id=1, fanvue_account_id=2,
        buyer_uuid=BUYER, telegram_user_id=3, identity_resolved=True,
        decision=CustomerSalesDecisionType.PRESENT_OFFER,
        reason=CustomerSalesReasonCode.REPEAT_BUYER, summary="test",
        stage=CustomerBuyerStage.REPEAT_BUYER, recommendation=recommendation,
        sell_allowed=True,
    )
    assert firewall.calls == 0
    assert result.next_sales_action is None
    assert result.bundle_sales_context["presentationPhase"] == "COMPLETE_PRESENTATION"
    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True


def test_content_wall_bundle_is_no_sale_without_session_fallback():
    firewall = Firewall()
    service = CustomerSalesBrainService(
        customer_repository=Customers(), photoshoot_lifecycle_service=Lifecycles(),
        bundle_sales_context_service=ContentWallBundleContext(),
        session_runtime_service=firewall, progression_repository=firewall,
        autonomous_progression_service=firewall,
    )
    recommendation = SimpleNamespace(
        offering_id=OFFERING, publication_id=PUBLICATION,
        delivery_url="https://test.invalid/bundle", title="Bundle",
        short_description="Complete set", price_minor=2500, currency="USD",
        photoshoot_experience=SimpleNamespace(
            photoshoot_id="shoot-1", recommendation_explanation="test",
        ),
    )
    result = service._finish(
        0.0, NOW, creator_profile_id=1, fanvue_account_id=2,
        buyer_uuid=BUYER, telegram_user_id=3, identity_resolved=True,
        decision=CustomerSalesDecisionType.PRESENT_OFFER,
        reason=CustomerSalesReasonCode.REPEAT_BUYER, summary="test",
        stage=CustomerBuyerStage.REPEAT_BUYER, recommendation=recommendation,
        sell_allowed=True,
    )
    assert firewall.calls == 0
    assert result.decision is CustomerSalesDecisionType.NO_SALE
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    assert result.reason_summary == "BUNDLE_CHANNEL_CONTENT_WALL"
    gateway = ConversationGateway.__new__(ConversationGateway)
    assert gateway._free_teaser_delivery(result) is None


def test_gateway_delivers_derivative_not_original_as_bundle_teaser():
    gateway = ConversationGateway.__new__(ConversationGateway)
    decision = SimpleNamespace(
        bundle_sales_context={
            "eligible": True, "presentationPhase": "COMPLETE_PRESENTATION",
            "lifecycleId": str(LIFECYCLE),
            "photoshoot": {"photoshootSessionId": "shoot-1"},
            "promotionalTeaser": {"assetId": 90, "sourceAssetId": 11},
            "_delivery": {"teaserAssetPath": "C:/test/blurred-90.png"},
        }, next_sales_action=None,
    )
    teaser = gateway._free_teaser_delivery(decision)
    assert teaser["asset_id"] == 90
    assert teaser["source_asset_id"] == 11
    assert teaser["asset_path"] == "C:/test/blurred-90.png"
    assert "11" not in teaser["asset_path"]
    offering = SimpleNamespace(
        delivery_url="https://test.invalid/bundle", offering_type="BUNDLE",
        offering_id=OFFERING, publication_id=PUBLICATION, provider="FANVUE",
        provider_resource_id="media-link-1", price_minor=2500,
        currency="USD",
    )
    delivery = gateway._authoritative_delivery(
        response_text="A preview\n\nBundle — USD 25.00: https://test.invalid/bundle",
        offering=offering,
        customer_sales_decision=decision,
    )
    assert delivery[:4] == (
        "https://test.invalid/bundle", "BUNDLE", "provider_link", True,
    )
    assert delivery[4]["asset_path"] == "C:/test/blurred-90.png"
    assert delivery[4]["media_link"] == "https://test.invalid/bundle"
    assert "https://test.invalid/bundle" in delivery[4]["message_text"]
    assert delivery[4]["metadata"]["bundle_complete_presentation"] is True
    assert "bundle_teaser_delivery" in delivery[4]["metadata"]
    assert "free_teaser_delivery" not in delivery[4]["metadata"]


def test_legacy_teaser_only_evidence_resumes_with_paid_offer_only():
    context = context_service().build(
        "shoot-1", identity=identity(), lifecycle_id=LIFECYCLE,
        teaser_presented=True,
    )
    assert context["eligible"] is True
    assert context["presentationPhase"] == "PAID_OFFER_ONLY"
    gateway = ConversationGateway.__new__(ConversationGateway)
    decision = SimpleNamespace(bundle_sales_context=context, next_sales_action=None)
    assert gateway._free_teaser_delivery(decision) is None


def test_completed_presentation_is_not_eligible_for_silent_resend():
    context = context_service().build(
        "shoot-1", identity=identity(), lifecycle_id=LIFECYCLE,
        teaser_presented=True, offer_presented=True,
    )
    assert context["eligible"] is False
    assert context["presentationPhase"] == "ALREADY_PRESENTED"
    assert "BUNDLE_ALREADY_PRESENTED" in context["ineligibilityReasons"]


class IntentWriter:
    def __init__(self):
        self.values = []

    def replace_active_intent(self, **values):
        self.values.append(values)
        return SimpleNamespace(purchase_intent_id=uuid4())


def test_one_paid_bundle_presentation_creates_one_intent_for_one_offering():
    writer = IntentWriter()
    identity_row = SimpleNamespace(
        id=4, telegram_user_id=3, telegram_chat_id=5,
        external_fanvue_user_uuid=BUYER, fanvue_account_id=2,
    )
    identities = SimpleNamespace(
        get_by_telegram_user_id=lambda user_id: identity_row
    )
    service = TelegramPurchaseIntentService(
        creator_profile_id=1, fanvue_account_id=2,
        identity_repository=identities, purchase_intent_service=writer,
        sales_session_service=SimpleNamespace(), clock=lambda: NOW,
    )
    diagnostics = {
        "final_offer_authorized": True,
        "customer_sales_brain_evaluated": True,
        "offering_selected": True,
        "offering_id": str(OFFERING), "publication_id": str(PUBLICATION),
        "delivery_url": "https://test.invalid/bundle",
        "provider_resource_id": "media-link-1", "provider": "FANVUE",
        "price_minor": 2500, "currency": "USD",
        "bundle_sales_context": {
            "schemaVersion": "photoshoot_bundle_conversation_v1",
            "photoshoot": {"deliverableId": "deliverable-1"},
        },
    }
    result = SimpleNamespace(
        diagnostic_metadata=diagnostics, correlation_id=uuid4(),
    )
    payload = SimpleNamespace(telegram_user_id=3, message_id=10)
    service.create_before_delivery(result, payload)
    assert len(writer.values) == 1
    created = writer.values[0]
    assert created["commercial_offering_id"] == OFFERING
    assert created["commercial_publication_id"] == PUBLICATION
    assert created["expected_price_minor"] == 2500
    assert created["delivery_url"] == "https://test.invalid/bundle"
    assert created["created_metadata"]["photoshoot_bundle"]["photoshoot"]["deliverableId"] == "deliverable-1"


class BundleLifecycleRepository:
    def __init__(self):
        self.transitions = []
        self.lifecycle = SimpleNamespace(
            lifecycle_id=LIFECYCLE, status=CustomerPhotoshootStatus.ACTIVE,
        )

    def get_by_id(self, lifecycle_id):
        return self.lifecycle

    def bundle_teaser_asset_id(self, lifecycle_id):
        return 90

    def get_for_purchase_intent(self, intent):
        return self.lifecycle

    def offering_selling_mode(self, offering_id):
        return "BUNDLE"

    def transition(self, lifecycle_id, **values):
        self.transitions.append(values)
        return self.lifecycle

    def history(self, lifecycle_id):
        return tuple(self.transitions)


def test_bundle_teaser_event_is_non_sequential_and_authoritative():
    repository = BundleLifecycleRepository()
    service = CustomerPhotoshootLifecycleService(repository=repository)
    service.record_bundle_teaser_delivery(
        lifecycle_id=LIFECYCLE, asset_id=90, provider="TELEGRAM",
        provider_delivery_id="message-1",
    )
    event = repository.transitions[0]
    assert event["event_type"] == "BUNDLE_TEASER_PRESENTED"
    assert event["asset_id"] == 90
    assert event["metadata"]["session_progression"] is False
    assert service.bundle_teaser_presented(repository.lifecycle) is True
    with pytest.raises(ValueError):
        service.record_bundle_teaser_delivery(
            lifecycle_id=LIFECYCLE, asset_id=11, provider="TELEGRAM",
            provider_delivery_id="message-2",
        )


def test_bundle_offer_presentation_records_one_non_asset_event():
    repository = BundleLifecycleRepository()
    service = CustomerPhotoshootLifecycleService(repository=repository)
    intent = SimpleNamespace(
        commercial_offering_id=OFFERING, purchase_intent_id=uuid4(),
    )
    service.record_presentation(intent)
    assert len(repository.transitions) == 1
    event = repository.transitions[0]
    assert event["event_type"] == "BUNDLE_OFFER_PRESENTED"
    assert "asset_id" not in event
    assert event["metadata"]["session_progression"] is False


def bundle_candidate(**changes):
    values = {
        "offering_id": OFFERING, "creator_profile_id": 1,
        "title": "Bundle", "offering_type": "BUNDLE",
        "offering_status": "READY", "primary_sales_channel": "AI_CHAT",
        "publication_status": "LIVE", "provider": "FANVUE",
        "provider_resource_status": "PRESENT",
        "delivery_url": "https://test.invalid/bundle", "price_minor": 2500,
        "destinations": ["BUNDLE", "BUNDLE"], "asset_ids": [11, 12],
        "photoshoot_identifier": "shoot-1",
        "photoshoot_identifiers": ["shoot-1"],
        "photoshoot_selling_mode": "BUNDLE",
        "bundle_teaser_asset_id": 90, "bundle_teaser_source_asset_id": 11,
        "bundle_teaser_registered": True,
    }
    values.update(changes)
    return values


def test_selector_suppresses_bundle_member_collisions_and_missing_teaser():
    selector = CommercialOfferingSelectorService.__new__(
        CommercialOfferingSelectorService
    )
    member = selector._evaluate(
        bundle_candidate(offering_type="SINGLE_IMAGE"),
        creator_profile_id=1, channel="AI_CHAT", purchased=frozenset(),
    )
    assert "BUNDLE_MEMBER_OFFERING_SUPPRESSED" in member.exclusion_reasons
    missing = selector._evaluate(
        bundle_candidate(bundle_teaser_asset_id=None),
        creator_profile_id=1, channel="AI_CHAT", purchased=frozenset(),
    )
    assert "BUNDLE_TEASER_NOT_READY" in missing.exclusion_reasons


def test_active_bundle_opportunity_reuses_canonical_bundle_without_progression():
    selector = CommercialOfferingSelectorService.__new__(
        CommercialOfferingSelectorService
    )
    selector.progression_repository = Firewall()
    candidate = bundle_candidate()
    opportunity = SimpleNamespace(photoshoot_id="shoot-1")
    selected = selector._active_opportunity_candidates(
        (candidate,), opportunity, 1,
        SimpleNamespace(customer_commerce_profile_id=CUSTOMER),
    )
    assert selected == (candidate,)
    assert selector.progression_repository.calls == 0
