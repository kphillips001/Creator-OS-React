from dataclasses import replace
from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import UUID, uuid4

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.services.chat_commerce_service import ChatCommerceService
from app.services.conversation_gateway import ConversationGateway
from app.services.commerce_execution_policy import (
    CommerceExecutionPolicy,
    derive_commerce_execution_policy,
)
from app.models.commerce_mode import CommerceMode


BUYER = UUID("9d7ce679-ccef-4bb9-9b01-7ee8b97516bc")


def offering():
    return SimpleNamespace(
        offering_id=uuid4(), publication_id=uuid4(),
        title="Private Release", description="A private photo.",
        offering_type="SINGLE_IMAGE", price_minor=999, currency="USD",
        primary_sales_channel="AI_CHAT", hero_asset_id=42,
        delivery_url="https://share.fanvue.com/ava/release",
        provider="FANVUE", provider_resource_id="media-link-1",
        published_at=datetime.now(timezone.utc),
    )


def sales_decision(
    decision_type, *, selected=None, reason=None, congratulate=False,
):
    selected = selected if decision_type in {
        CustomerSalesDecisionType.PRESENT_OFFER,
        CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
    } else None
    return CustomerSalesDecision(
        creator_profile_id=7, fanvue_account_id=4,
        external_fanvue_buyer_uuid=BUYER, telegram_user_id=123,
        identity_resolved=True, decision=decision_type,
        reason_code=reason or (
            CustomerSalesReasonCode.NO_ACTIVE_OFFER
            if selected else
            CustomerSalesReasonCode.ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE
        ),
        reason_summary="Deterministic fixture.",
        buyer_stage=CustomerBuyerStage.FIRST_TIME_BUYER,
        commerce_signal=MappingProxyType({}),
        active_purchase_intent_id=None, active_offering_id=None,
        active_offer_status=None,
        active_offer_conversion_state="NO_ACTIVE_OFFER",
        recommended_offering_id=selected.offering_id if selected else None,
        recommended_publication_id=(
            selected.publication_id if selected else None
        ),
        recommended_delivery_url=(
            selected.delivery_url if selected else None
        ),
        sell_allowed=(
            selected is not None
            and decision_type is CustomerSalesDecisionType.PRESENT_OFFER
        ),
        nudge_allowed=(
            decision_type is CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER
        ),
        upsell_allowed=False, cross_sell_allowed=False,
        congratulate_allowed=congratulate, cooldown_until=None,
        evaluated_at=datetime.now(timezone.utc),
        decision_metadata=MappingProxyType({}),
        recommended_offering_title=selected.title if selected else None,
        recommended_offering_short_description=(
            selected.description if selected else None
        ),
        recommended_offering_price_minor=(
            selected.price_minor if selected else None
        ),
        recommended_offering_currency=(
            selected.currency if selected else None
        ),
    )


class SalesBrain:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def evaluate_for_telegram_user(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


class Brain:
    def __init__(self, send_offer=True):
        self.send_offer = send_offer
        self.calls = []

    def process_message(
        self, user_id, message, chat_history=None, runtime_injection=None,
    ):
        self.calls.append({
            "user_id": user_id, "message": message,
            "chat_history": chat_history,
            "runtime_injection": runtime_injection,
        })
        return {
            "response": "Ava's existing reply.",
            "send_offer": self.send_offer,
            "blocked": False,
            "route": {"route": "sales", "reason": "fixture"},
            "commerce_readiness": {
                "conversation_ready_for_offer": True,
                "current_buying_intent": True,
            },
        }


def test_gateway_preserves_exact_selector_recommendation_trace():
    trace = [{
        "rank": 1, "offeringId": str(uuid4()), "title": "Beach Set",
        "selected": True, "finalScore": 0.843, "components": [],
    }]
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.PRESENT_OFFER,
            selected=offering(),
        ),
        decision_metadata=MappingProxyType({
            "offeringSelector": {
                "recommendationEngineVersion":
                    "commerce_recommendation_v2_intelligent",
                "recommendationTrace": trace,
                "eligibleCount": 1,
            },
        }),
    )

    diagnostics = ConversationGateway._customer_sales_diagnostics(decision)

    assert diagnostics["recommendation_trace"] is trace
    assert diagnostics["recommendation_diagnostics"][
        "recommendationTrace"
    ] is trace


class Sales:
    def __init__(self, selected):
        self.selected = selected
        self.resolve_calls = []
        self.recommend_calls = []

    def resolve_recommended_offering(self, **kwargs):
        self.resolve_calls.append(kwargs)
        return self.selected

    def recommend_best(self, **kwargs):
        self.recommend_calls.append(kwargs)
        raise AssertionError("The Conversation Brain must not reselect an offer.")


def execute(
    decision, selected=None, *, acknowledgement=False,
    engine_send_offer=True, commerce_mode=None, relationship_mode=None,
):
    engine = Brain(send_offer=engine_send_offer)
    sales = Sales(selected)
    customer_brain = SalesBrain(decision)
    gateway = ConversationGateway(
        engine, allowed_fanvue_hostnames=("fanvue.com", "share.fanvue.com"),
        creator_profile_id=7,
        chat_commerce_service=ChatCommerceService(
            sales_service=sales, commerce_mode="AUTHORITATIVE"
        ),
        customer_sales_brain_service=customer_brain,
        commerce_mode_service=commerce_mode,
        relationship_mode_service=relationship_mode,
    )
    output = gateway.execute(ConversationGatewayInput(
        engine_user_id="4:-123", message_text="Show me one photo",
        chat_history=[], correlation_id="turn-1",
        brain_context=ConversationBrainContext(
            creator_profile_id=7, customer_identifier="4:-123",
            conversation_identifier="conversation-1",
            telegram_user_id=123,
            purchase_acknowledgement_pending=acknowledgement,
        ),
    ))
    return output, engine, sales, customer_brain


def test_relationship_mode_runs_recommendation_but_suppresses_commerce_execution():
    selected = offering()

    class Mode:
        def get_mode(self): return CommerceMode.RELATIONSHIP

    class Relationship:
        def __init__(self): self.recorded = []
        def record_would_have_sold(self, decision, *, correlation_id):
            self.recorded.append((decision.recommended_offering_id, correlation_id))
        def response(self, **_): return "You're catching me early 😊"

    relationship = Relationship()
    output, engine, sales, customer_brain = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected, commerce_mode=Mode(), relationship_mode=relationship,
    )

    assert len(customer_brain.calls) == 1
    assert len(engine.calls) == 1
    assert engine.calls[0]["runtime_injection"]["commerce_decision"]["decision"] == "PRE_LAUNCH"
    assert engine.calls[0]["runtime_injection"]["commerce_execution_policy"] == "COMMERCE_DISABLED_FOR_TURN"
    assert output.offer_authorized is False
    assert output.offer_link is None
    assert output.delivery_payload["delivery_method"] == "text"
    assert output.delivery_requires_payment is False
    assert "delivery_url" not in output.delivery_payload
    assert selected.delivery_url not in output.response_text
    assert "catching me early" in output.response_text
    assert sales.resolve_calls == []
    assert relationship.recorded == [(selected.offering_id, "turn-1")]
    assert output.diagnostic_metadata["would_have_sold"] is True
    assert output.diagnostic_metadata["commerce_suppression_reason"] == "RELATIONSHIP_MODE"
    assert output.diagnostic_metadata["no_purchase_intent_created"] is True


def test_present_offer_is_evaluated_once_and_uses_existing_workflow():
    selected = offering()
    output, engine, sales, customer_brain = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected,
    )
    assert len(customer_brain.calls) == 1
    assert len(engine.calls) == 1
    assert engine.calls[0]["runtime_injection"]["commerce_decision"] == {
        "decision": "PRESENT_OFFER",
        "reason_code": "NO_ACTIVE_OFFER",
        "buyer_stage": "FIRST_TIME_BUYER",
        "current_offer_status": None,
        "conversion_state": "NO_ACTIVE_OFFER",
        "commerce_execution_policy": "COMMERCE_DISABLED_FOR_TURN",
        "selected_offering": {
            "title": "Private Release",
            "short_description": "A private photo.",
            "price_minor": 999,
            "currency": "USD",
        },
    }
    assert engine.calls[0]["runtime_injection"][
        "commerce_execution_policy"
    ] == "COMMERCE_DISABLED_FOR_TURN"
    assert len(sales.resolve_calls) == 1
    assert sales.resolve_calls[0]["offering_id"] == selected.offering_id
    assert sales.recommend_calls == []
    assert selected.delivery_url in output.response_text
    assert output.offer_authorized is True
    assert output.diagnostic_metadata["customer_sales_brain_evaluated"] is True
    assert output.diagnostic_metadata["legacy_offer_requested"] is True
    assert output.diagnostic_metadata["commerce_offer_authorized"] is True
    assert output.diagnostic_metadata["final_offer_authorized"] is True
    assert output.offer_link == selected.delivery_url
    assert output.delivery_payload["media_link"] == selected.delivery_url
    assert output.delivery_payload["product_reference"] == str(
        selected.offering_id
    )
    assert output.diagnostic_metadata["commerce_mode"] == "AUTHORITATIVE"
    assert output.diagnostic_metadata["compatibility_mode"] is False
    assert output.diagnostic_metadata["delivery_source"] == (
        "RESOLVED_COMMERCIAL_OFFERING"
    )
    assert output.diagnostic_metadata["legacy_delivery_used"] is False
    assert output.diagnostic_metadata["legacy_memory_mutated"] is False


def test_wait_suppresses_existing_engine_offer_without_reselection():
    output, _, sales, customer_brain = execute(
        sales_decision(CustomerSalesDecisionType.WAIT),
    )
    assert len(customer_brain.calls) == 1
    assert output.offer_authorized is False
    assert output.response_text == "Ava's existing reply."
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []


def test_purchase_acknowledgement_context_and_decision_reach_brain():
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, engine, _, customer_brain = execute(
        decision, acknowledgement=True,
    )
    assert customer_brain.calls[0]["conversation_context"] == {
        "purchase_acknowledgement_pending": True,
        "latest_message": "Show me one photo",
        "conversation_id": "conversation-1",
        "requested_media_type": "SINGLE_IMAGE",
        "recent_conversation_requests": (),
    }
    injected = engine.calls[0]["runtime_injection"]["commerce_decision"]
    assert injected["decision"] == "CONGRATULATE_PURCHASE"
    assert injected["reason_code"] == "PURCHASE_VERIFIED"
    assert output.offer_authorized is False


def test_nudge_reuses_selector_result_without_resolving_or_reselecting():
    selected = offering()
    output, engine, sales, customer_brain = execute(
        sales_decision(
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
            selected=selected,
            reason=CustomerSalesReasonCode.ACTIVE_OFFER_NUDGE_ELIGIBLE,
        ),
        selected,
    )

    assert len(customer_brain.calls) == 1
    assert engine.calls[0]["runtime_injection"][
        "commerce_execution_policy"
    ] == "COMMERCE_NUDGE_ALLOWED"
    assert engine.calls[0]["runtime_injection"]["commerce_decision"][
        "selected_offering"
    ]["title"] == selected.title
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []
    assert selected.delivery_url not in output.response_text
    assert output.diagnostic_metadata["selection_source"] == (
        "COMMERCIAL_OFFERING_SELECTOR"
    )


def test_missing_authoritative_selection_fails_closed_without_fallback():
    selected = offering()
    malformed = replace(
        sales_decision(
            CustomerSalesDecisionType.PRESENT_OFFER,
            selected=selected,
        ),
        recommended_offering_title=None,
    )

    output, engine, sales, _ = execute(malformed, selected)

    assert engine.calls[0]["runtime_injection"][
        "commerce_execution_policy"
    ] == "COMMERCE_DISABLED_FOR_TURN"
    assert output.offer_authorized is False
    assert output.diagnostic_metadata[
        "authoritative_offering_selected"
    ] is False
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []


def test_sales_brain_presentation_is_final_authority_over_legacy_readiness():
    selected = offering()
    output, _, sales, _ = execute(
        sales_decision(
            CustomerSalesDecisionType.PRESENT_OFFER,
            selected=selected,
        ),
        selected,
        engine_send_offer=False,
    )

    assert output.diagnostic_metadata["legacy_offer_requested"] is False
    assert output.diagnostic_metadata["commerce_offer_authorized"] is True
    assert output.diagnostic_metadata["final_offer_authorized"] is True
    assert output.offer_authorized is True
    assert len(sales.resolve_calls) == 1


def test_gpt_prompt_contains_only_compact_authoritative_commerce_context():
    source = open("app/services/gpt_service.py", encoding="utf-8").read()
    assert "AUTHORITATIVE COMMERCE" in source
    assert "Treat this deterministic commerce decision as authoritative" in source
    assert "recommended_offering_id" not in source


def test_all_customer_sales_decisions_map_to_one_internal_execution_policy():
    expected = {
        CustomerSalesDecisionType.WAIT:
            CommerceExecutionPolicy.DISABLED_FOR_TURN,
        CustomerSalesDecisionType.PAYMENT_PENDING:
            CommerceExecutionPolicy.PAYMENT_PENDING,
        CustomerSalesDecisionType.MANUAL_REVIEW:
            CommerceExecutionPolicy.MANUAL_REVIEW,
        CustomerSalesDecisionType.NO_SALE:
            CommerceExecutionPolicy.DISABLED_FOR_TURN,
        CustomerSalesDecisionType.CONTINUE_CONVERSATION:
            CommerceExecutionPolicy.DISABLED_FOR_TURN,
        CustomerSalesDecisionType.PRESENT_OFFER:
            CommerceExecutionPolicy.PRESENTATION_ALLOWED,
        CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER:
            CommerceExecutionPolicy.NUDGE_ALLOWED,
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE:
            CommerceExecutionPolicy.ACKNOWLEDGEMENT_ALLOWED,
    }
    selected = offering()
    for decision_type, policy in expected.items():
        decision = sales_decision(
            decision_type,
            selected=selected if (
                decision_type is CustomerSalesDecisionType.PRESENT_OFFER
            ) else None,
        )
        assert derive_commerce_execution_policy(decision) is policy
