from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.commercial_intelligence import (
    BundleCompositionEvidence,
    BundleEligibility,
    CommercialIntelligenceContext,
    OwnershipCoverage,
    SellingStrategy,
    StrategyConstraints,
    StrategyDecisionReason,
)
from app.services.commercial_intelligence_context_service import (
    CommercialIntelligenceContextService,
)
from app.services.commercial_intelligence_service import (
    CommercialIntelligenceService,
)
from app.services.commercial_offering_selector_service import (
    CommercialOfferingSelectorService,
)
from app.services.telegram_purchase_intent_service import (
    TelegramPurchaseIntentService,
)


def context(**changes):
    values = {
        "creator_profile_id": 1,
        "fanvue_account_id": 2,
        "telegram_user_id": 3,
        "available_offering_types": ("SINGLE_IMAGE", "BUNDLE"),
        "intended_photoshoot_reference": "photoshoot-1",
        "bundle_compositions": (
            BundleCompositionEvidence(
                photoshoot_reference="photoshoot-1",
                asset_ids=(10, 11),
                complete_set=True,
                provenance=("APPROVED_PHOTOSHOOT_MEMBERSHIP",),
            ),
        ),
    }
    values.update(changes)
    return CommercialIntelligenceContext(**values)


def test_active_session_durable_fact_outranks_complete_set_request():
    session_id = uuid4()
    result = CommercialIntelligenceService().recommend(context(
        active_sales_session_id=session_id,
        sales_session_state="ACTIVE",
        sales_session_progression="PREMIUM",
        sales_session_foundation="photoshoot-1",
        session_participated=True,
        latest_message="show me the complete set",
    ))
    assert result.strategy is SellingStrategy.SESSION_SELLING
    assert result.sales_session_context["salesSessionId"] == str(session_id)
    assert result.constraints.required_photoshoot_reference == "photoshoot-1"
    assert result.constraints.progression == "PREMIUM"
    assert result.constraints.continuation_required is True


def test_conversation_session_does_not_invent_a_photoshoot_constraint():
    session_id = uuid4()
    result = CommercialIntelligenceService().recommend(context(
        active_sales_session_id=session_id,
        sales_session_state="ACTIVE",
        sales_session_progression="DISCOVERY",
        sales_session_foundation_type="CONVERSATION",
        sales_session_foundation=None,
        session_participated=True,
    ))

    assert result.strategy is SellingStrategy.SESSION_SELLING
    assert result.constraints.required_photoshoot_reference is None
    assert result.sales_session_context["foundationType"] == "CONVERSATION"


def test_explicit_request_recommends_library_without_selecting_or_authorizing():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="show me a beach outfit photo",
        requested_themes=("beach",),
    ))
    assert result.strategy is SellingStrategy.LIBRARY_SELLING
    assert result.constraints.requested_themes == ("beach",)
    assert not hasattr(result, "offering_id")
    assert not hasattr(result, "sell_allowed")


def test_no_evidence_is_explicit_no_strategy():
    result = CommercialIntelligenceService().recommend(context(
        available_offering_types=(),
    ))
    assert result.strategy is None
    assert result.evidence_sufficient is False


def test_bundle_partial_session_purchase_requires_continuation():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="I want the complete set",
        session_participated=True,
        session_purchase_count=1,
        ownership=OwnershipCoverage(
            owned_asset_ids=(10,), session_owned_asset_ids=(10,),
            evidence_sources=("ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE",),
        ),
    ))
    assert result.strategy is None
    assert result.bundle_eligibility is BundleEligibility.PARTIAL_SESSION_PURCHASE
    assert result.constraints.remaining_value_required is True


def test_complete_owner_bundle_request_is_suppressed_before_selection():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="I want the complete set",
        ownership=OwnershipCoverage(
            owned_asset_ids=(10, 11),
            evidence_sources=("CORE_USER_PRODUCT_ENTITLEMENT",),
        ),
    ))
    assert result.strategy is None
    assert result.bundle_eligibility is BundleEligibility.COMPLETE_VALUE_OWNED
    assert result.constraints.remaining_value_required is False


def test_bundle_incomplete_ownership_is_not_assumed_eligible():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="send the full photoshoot",
        ownership=OwnershipCoverage(incomplete=True),
    ))
    assert result.strategy is None
    assert (
        result.bundle_eligibility
        is BundleEligibility.INSUFFICIENT_OWNERSHIP_EVIDENCE
    )


def test_library_selling_fails_closed_on_incomplete_ownership():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="show me a beach photo",
        ownership=OwnershipCoverage(incomplete=True),
    ))

    assert result.strategy is None
    assert result.evidence_sufficient is False
    assert (
        result.reason
        is StrategyDecisionReason.INSUFFICIENT_OWNERSHIP_EVIDENCE
    )


def test_missed_session_customer_may_receive_bundle_selling():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="send the complete set",
        session_participated=False,
        session_purchase_count=0,
    ))
    assert result.strategy is SellingStrategy.BUNDLE_SELLING
    assert result.bundle_eligibility is BundleEligibility.BUNDLE_ELIGIBLE


def test_participated_without_purchase_may_receive_bundle_selling():
    result = CommercialIntelligenceService().recommend(context(
        latest_message="send the complete set",
        session_participated=True,
        session_purchase_count=0,
    ))
    assert result.strategy is SellingStrategy.BUNDLE_SELLING
    assert result.bundle_eligibility is BundleEligibility.BUNDLE_ELIGIBLE


def candidate(offering_type="BUNDLE", asset_ids=(10, 11)):
    return {
        "offering_id": uuid4(), "title": "Complete Set",
        "creator_profile_id": 1, "commercially_eligible": True,
        "offering_status": "READY", "primary_sales_channel": "AI_CHAT",
        "publication_status": "LIVE", "provider": "FANVUE",
        "provider_resource_status": "PRESENT",
        "delivery_url": "https://fanvue.com/link", "price_minor": 1000,
        "destinations": ["BUNDLE"] * len(asset_ids),
        "offering_type": offering_type, "asset_ids": list(asset_ids),
        "publication_id": uuid4(), "published_at": datetime.now(timezone.utc),
        "photoshoot_identifier": "photoshoot-1",
        "photoshoot_identifiers": ["photoshoot-1"],
        "commercial_roles": ["CORE", "PREMIUM"],
    }


def test_selector_enforces_bundle_and_complete_ownership_constraints():
    service = CommercialOfferingSelectorService(repository=SimpleNamespace())
    partial = service._evaluate(
        candidate(), creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(),
        constraints=StrategyConstraints(
            required_offering_types=("BUNDLE",),
            complete_set_required=True, excluded_asset_ids=(10,),
        ),
    )
    complete = service._evaluate(
        candidate(), creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(),
        constraints=StrategyConstraints(
            required_offering_types=("BUNDLE",),
            complete_set_required=True, excluded_asset_ids=(10, 11),
        ),
    )
    assert "BUNDLE_PARTIALLY_OWNED" in partial.exclusion_reasons
    assert "BUNDLE_FULLY_OWNED" in complete.exclusion_reasons


def test_selector_enforces_authoritative_session_selling_mode_constraint():
    service = CommercialOfferingSelectorService(repository=SimpleNamespace())
    ordinary = candidate()
    ordinary["photoshoot_selling_mode"] = None
    session = candidate()
    session["photoshoot_selling_mode"] = "SESSION"
    constraints = StrategyConstraints(required_selling_modes=("SESSION",))

    ordinary_result = service._evaluate(
        ordinary, creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(), constraints=constraints,
    )
    session_result = service._evaluate(
        session, creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(), constraints=constraints,
    )

    assert "STRATEGY_SELLING_MODE_MISMATCH" in ordinary_result.exclusion_reasons
    assert "STRATEGY_SELLING_MODE_MISMATCH" not in session_result.exclusion_reasons


def test_selector_fails_closed_when_progression_role_evidence_is_missing():
    service = CommercialOfferingSelectorService(repository=SimpleNamespace())
    value = candidate()
    value["commercial_roles"] = []
    result = service._evaluate(
        value, creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(),
        constraints=StrategyConstraints(progression="PREMIUM"),
    )
    assert "STRATEGY_ROLE_EVIDENCE_MISSING" in result.exclusion_reasons


def test_selector_rejects_offering_unrelated_to_session_photoshoot():
    service = CommercialOfferingSelectorService(repository=SimpleNamespace())
    result = service._evaluate(
        candidate(), creator_profile_id=1, channel="AI_CHAT",
        purchased=frozenset(),
        constraints=StrategyConstraints(
            required_photoshoot_reference="photoshoot-other",
        ),
    )
    assert "STRATEGY_PHOTOSHOOT_MISMATCH" in result.exclusion_reasons


class Ownership:
    def get(self, **kwargs):
        return {
            "owned_offering_ids": (), "owned_asset_ids": (10,),
            "purchase_asset_ids": (10,),
            "evidence_sources": ("ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE",),
            "incomplete": False, "conflicts": (),
        }


def test_context_assembly_is_read_only_and_preserves_provenance():
    service = CommercialIntelligenceContextService(
        ownership_repository=Ownership()
    )
    result = service.assemble(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_user_uuid=uuid4(), telegram_user_id=3,
        conversation_context={"latest_message": "show me a photo"},
    )
    assert result.ownership.owned_asset_ids == (10,)
    assert result.provenance["ownership"] == (
        "ATTRIBUTED_COMMERCIAL_OFFERING_PURCHASE",
    )


class Identity:
    def get_by_telegram_user_id(self, user_id):
        return SimpleNamespace(
            id=7, telegram_user_id=user_id, telegram_chat_id=99,
            external_fanvue_user_uuid=uuid4(), fanvue_account_id=2,
        )


class Intents:
    def __init__(self):
        self.intent = SimpleNamespace(purchase_intent_id=uuid4())

    def replace_active_intent(self, **values):
        return self.intent


class Sessions:
    def __init__(self):
        self.calls = []

    def associate_purchase_intent(self, **values):
        self.calls.append(values)


class SyntheticUnlockGateway:
    def issue(self, _intent):
        return None, "https://creator.example/api/v1/commerce/unlock/synthetic"


def test_authorized_session_purchase_intent_uses_canonical_association():
    sessions = Sessions()
    service = TelegramPurchaseIntentService(
        creator_profile_id=1, fanvue_account_id=2,
        identity_repository=Identity(), purchase_intent_service=Intents(),
        sales_session_service=sessions,
        unlock_gateway_service=SyntheticUnlockGateway(),
    )
    session_id = uuid4()
    result = SimpleNamespace(
        correlation_id=str(uuid4()),
        delivery_payload={"message_text": "Synthetic session offer."},
        diagnostic_metadata={
            "final_offer_authorized": True,
            "customer_sales_brain_evaluated": True,
            "offering_selected": True,
            "delivery_url": "https://fanvue.com/link",
            "provider_resource_id": "resource",
            "publication_id": str(uuid4()),
            "offering_id": str(uuid4()),
            "provider": "FANVUE", "price_minor": 1000, "currency": "USD",
            "commercial_intelligence": {
                "strategy": "SESSION_SELLING",
                "salesSessionContext": {
                    "salesSessionId": str(session_id),
                },
            },
        },
    )
    payload = SimpleNamespace(telegram_user_id=3, message_id=4)
    intent = service.create_before_delivery(result, payload)
    assert intent is not None
    assert sessions.calls[0]["session_id"] == str(session_id)
    assert sessions.calls[0]["purchase_intent_id"] == intent.purchase_intent_id
