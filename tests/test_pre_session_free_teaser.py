from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.conversational_sales_progression_service import (
    ConversationalSalesProgressionService,
)
from app.services.gpt_service import GPTService
from app.testing.session5_scenario_harness import ScenarioLabRuntimeMediaResolver


POSITIVES = (
    "tease me a little",
    "give me a little tease",
    "show me a little preview",
    "give me a sneak peek",
    "let me have a little taste",
)
NEGATIVES = (
    "you're such a tease",
    "you look good",
    "you've got my attention",
    "I like talking to you",
    "what are you doing?",
)


def test_c20_opening_trajectory_preserves_attention_then_reaches_teaser_authority():
    progression = ConversationalSalesProgressionService()
    turns = (
        "you've got me curious tonight",
        "okay, now you've got my attention",
        "tease me a little",
    )

    turn_one = "Curiosity suits you."
    turn_two = GPTService._foreground_semantic_fallback(
        turns[1], effort_mode="FULL",
    )
    assert GPTService._foreground_semantic_relevance(
        turns[0], turn_one,
    )["satisfied"] is True
    assert turn_two == "good, I was hoping I had your attention"
    assert "?" not in turn_two
    assert not any(progression.has_direct_purchase_intent(turn) for turn in turns)
    assert not progression.has_explicit_teaser_asset_request(turns[0])
    assert not progression.has_explicit_teaser_asset_request(turns[1])
    assert progression.has_explicit_teaser_asset_request(turns[2])


def test_scenario_transport_resolves_only_marked_certification_media():
    resolver = ScenarioLabRuntimeMediaResolver()
    fixture = SimpleNamespace(
        id=2911,
        file_path="certification/C20/session-teaser.jpg",
        local_vault_path=None,
        media_metadata={"certification_fixture": {
            "scenario_id": "C20", "session_role": "FREE_TEASER",
        }},
    )
    resolved = resolver.resolve_original(fixture, require_exists=True)
    assert resolved.path.as_posix() == "certification/C20/session-teaser.jpg"
    assert resolved.source == "scenario_lab.certification_fixture"
    assert resolved.exists is True

    ordinary = SimpleNamespace(
        id=2912,
        file_path="certification/C20/unmarked.jpg",
        local_vault_path=None,
        media_metadata={},
    )
    rejected = resolver.resolve_original(ordinary, require_exists=True)
    assert rejected.path is None


def test_explicit_teaser_asset_semantics_are_distinct_from_flirting_and_paid_intent():
    service = ConversationalSalesProgressionService()
    assert all(service.has_explicit_teaser_asset_request(value) for value in POSITIVES)
    assert not any(service.has_explicit_teaser_asset_request(value) for value in NEGATIVES)
    assert not service.has_direct_purchase_intent("tease me a little")
    assert service.has_direct_purchase_intent("show me more")


def _decision(authority):
    return CustomerSalesDecision(
        creator_profile_id=1, fanvue_account_id=2,
        external_fanvue_buyer_uuid=None, telegram_user_id=3,
        identity_resolved=False, decision=CustomerSalesDecisionType.TEASE,
        reason_code=CustomerSalesReasonCode.EXPLICIT_FREE_TEASER_REQUEST,
        reason_summary="explicit free teaser", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=MappingProxyType({}), active_purchase_intent_id=None,
        active_offering_id=None, active_offer_status=None,
        active_offer_conversion_state="NONE", recommended_offering_id=None,
        recommended_publication_id=None, recommended_delivery_url=None,
        sell_allowed=False, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=datetime.now(timezone.utc),
        decision_metadata=MappingProxyType({"preSessionFreeTeaser": authority}),
    )


def test_gateway_delivers_exact_pre_session_teaser_without_paid_payload():
    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(
        get_by_id=lambda asset_id: SimpleNamespace(id=asset_id)
    )
    gateway._runtime_media_resolver = SimpleNamespace(
        resolve_original=lambda asset, require_exists: SimpleNamespace(
            path="C:/safe/teaser.jpg", source="content_item.file_path"
        )
    )
    provisional_id = uuid4()
    decision = _decision({
        "authorized": True, "provisionalSessionId": str(provisional_id),
        "photoshoot_reference": "foundation-1", "teaser_asset_id": 10,
        "next_position": 2, "next_asset_id": 20,
        "next_sales_role": "FIRST_UNLOCK", "next_offering_id": str(uuid4()),
        "next_price_minor": 900, "currency": "USD",
    })

    teaser = gateway._free_teaser_delivery(decision)
    assert teaser == {
        "provisional_session_id": str(provisional_id),
        "photoshoot_session_id": "foundation-1", "asset_id": 10,
        "position": 1, "next_position": 2, "next_asset_id": 20,
        "next_sales_role": "FIRST_UNLOCK",
        "next_offering_id": teaser["next_offering_id"],
        "next_price_minor": 900, "currency": "USD",
        "sales_role": "FREE_TEASER", "asset_path": "C:/safe/teaser.jpg",
        "asset_path_source": "content_item.file_path",
        "authority": "PRE_SESSION_CANONICAL_SESSION_GRAPH",
    }
    delivery = gateway._authoritative_delivery(
        response_text="just a little preview for you", offering=None,
        customer_sales_decision=decision,
    )
    assert delivery[:4] == (None, "FREE", "asset", False)
    payload = delivery[4]
    assert payload["asset_path"] == "C:/safe/teaser.jpg"
    assert "free_teaser_delivery" in payload["metadata"]
    assert "media_link" not in payload
    assert "product_reference" not in payload


def test_missing_or_unauthorized_pre_session_teaser_fails_closed():
    gateway = ConversationGateway.__new__(ConversationGateway)
    decision = _decision({
        "explicitRequestDetected": True, "authorized": False,
        "failureReason": "CANONICAL_FREE_TEASER_UNAVAILABLE_OR_AMBIGUOUS",
    })
    assert gateway._free_teaser_delivery(decision) is None


def test_delivery_finalization_marks_authority_pending_not_delivered():
    decision, diagnostics = ConversationGateway._finalize_progression_delivery(
        _decision({"authorized": True}), response_text="here you go",
        blocked=False, offer_authorized=False,
        style={"turnObligationsSatisfied": True, "meaningfulContribution": True},
    )
    assert diagnostics["commercial_tease_authorized"] is True
    assert diagnostics["commercial_tease_delivered"] is False
    assert diagnostics["commercial_tease_delivery_pending_confirmation"] is True
    assert decision.sell_allowed is False
