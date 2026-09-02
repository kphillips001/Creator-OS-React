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

    def refine_for_readiness(self, *_args, **_kwargs):
        raise AssertionError(
            "DecisionEngine observations must not refine the final sales decision."
        )


class LiveCommerceMode:
    def get_mode(self):
        return CommerceMode.LIVE


class Brain:
    def __init__(
        self, send_offer=True, response_text="Ava's existing reply.",
        commerce_readiness=None,
    ):
        self.send_offer = send_offer
        self.response_text = response_text
        self.commerce_readiness = commerce_readiness or {
            "conversation_ready_for_offer": True,
            "current_buying_intent": True,
        }
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
            "response": self.response_text,
            "send_offer": self.send_offer,
            "blocked": False,
            "route": {"route": "sales", "reason": "fixture"},
            "commerce_readiness": dict(self.commerce_readiness),
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
    response_text="Ava's existing reply.",
    presentation_generator=None,
    acknowledgement_generator=None,
    commerce_readiness=None,
    message_text="Show me one photo",
    chat_history=None,
):
    engine = Brain(
        send_offer=engine_send_offer, response_text=response_text,
        commerce_readiness=commerce_readiness,
    )
    sales = Sales(selected)
    customer_brain = SalesBrain(decision)
    gateway = ConversationGateway(
        engine, allowed_fanvue_hostnames=("fanvue.com", "share.fanvue.com"),
        creator_profile_id=7,
        chat_commerce_service=ChatCommerceService(
            sales_service=sales, commerce_mode="AUTHORITATIVE"
        ),
        customer_sales_brain_service=customer_brain,
        commercial_presentation_copy_generator=(presentation_generator or (
            lambda **_kwargs: "Here it is - unlock this private one."
        )),
        purchase_acknowledgement_copy_generator=acknowledgement_generator,
        commerce_mode_service=commerce_mode or LiveCommerceMode(),
        relationship_mode_service=relationship_mode,
    )
    output = gateway.execute(ConversationGatewayInput(
        engine_user_id="4:-123", message_text=message_text,
        chat_history=list(chat_history or []), correlation_id="turn-1",
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


def test_controlled_identity_executes_real_offer_while_global_mode_stays_relationship(monkeypatch):
    from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
    selected = offering()
    selected.price_minor = 300
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "true")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID", "123")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID", "123")

    class Mode:
        def get_mode(self): return CommerceMode.RELATIONSHIP

    with ControlledAutonomyTestService().scope(telegram_user_id=123, telegram_chat_id=123):
        output, engine, sales, _ = execute(
            sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
            selected, commerce_mode=Mode(),
        )
    assert output.offer_authorized is True
    assert output.offer_link == selected.delivery_url
    assert output.delivery_requires_payment is True
    assert "USD 3.00" not in output.response_text
    assert selected.price_minor == 300
    assert output.delivery_payload["media_link"] == selected.delivery_url
    assert sales.resolve_calls
    assert engine.calls[0]["runtime_injection"]["commerce_execution_policy"] == "COMMERCE_PRESENTATION_ALLOWED"
    assert output.diagnostic_metadata["controlled_test_commerce_override"] is True
    assert output.diagnostic_metadata["commerce_prompt_mode"] == "PRESENT_OFFER"


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
                    "customer_safe_description": "A private photo.",
                    "customer_safe_copy_available": True,
            },
            "paid_presentation_contract": {
                "price_neutral": True,
                "presentation_complete": True,
                "customer_facing_price_status": "STRUCTURED_PAID_PRESENTATION",
                "conversational_price_suppressed": True,
            },
        }
    assert engine.calls[0]["runtime_injection"][
        "commerce_execution_policy"
    ] == "COMMERCE_DISABLED_FOR_TURN"
    assert len(sales.resolve_calls) == 1
    assert sales.resolve_calls[0]["offering_id"] == selected.offering_id
    assert sales.recommend_calls == []
    assert selected.delivery_url not in output.response_text
    assert "USD 9.99" not in output.response_text
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


def test_customer_initiated_active_offer_continuation_reuses_structured_offer():
    selected = offering()
    intent_id = uuid4()
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
            selected=selected,
            reason=(CustomerSalesReasonCode
                    .CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION),
        ),
        active_purchase_intent_id=intent_id,
        active_offering_id=selected.offering_id,
        active_offer_status="PRESENTED",
        decision_metadata=MappingProxyType({
            "activeOfferContinuation": {
                "customerInitiatedOfferContinuation": True,
                "continuationIntentType": "SEND_OR_LINK_REQUEST",
                "nudgeCooldownApplies": False,
                "structuredOfferReused": True,
                "purchaseIntentReused": True,
                "relationshipDiscoverySuppressed": True,
            },
            "offerLifecycle": {
                "messagePurpose": "ACTIVE_OFFER_CONTINUATION",
                "purchaseIntentId": str(intent_id),
            },
        }),
    )
    output, _, sales, _ = execute(
        decision, selected,
        response_text="I'm not dropping links just yet.",
        presentation_generator=lambda **values: values["draft"],
    )
    assert output.offer_authorized is True, {
        key: output.diagnostic_metadata.get(key) for key in (
            "commerce_execution_policy", "authoritative_selection_missing",
            "commerce_offer_allowed", "final_offer_authorized", "blocked",
            "paid_presentation_validated", "presentation_copy_failure_reason",
            "commerce_mode", "configured_commerce_mode",
        )
    }
    assert output.delivery_requires_payment is True
    assert output.delivery_payload["product_reference"] == str(
        selected.offering_id
    )
    assert output.delivery_payload["metadata"]["message_purpose"] == (
        "ACTIVE_OFFER_CONTINUATION"
    )
    assert "not dropping links" not in output.response_text.lower()
    assert "$9.99" not in output.response_text
    assert output.diagnostic_metadata["active_purchase_intent_id"] == str(
        intent_id
    )
    assert len(sales.resolve_calls) == 1


def test_paid_offer_regenerates_authoritative_copy_when_initial_draft_is_empty():
    selected = offering()
    output, _, _, _ = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected,
        response_text="   ",
    )
    assert output.blocked is False
    assert output.offer_authorized is True
    assert "Here it is - unlock this private one." in output.response_text
    assert output.delivery_requires_payment is True
    assert output.diagnostic_metadata["paid_presentation_validated"] is True


def test_structured_offer_authority_repairs_vague_generated_caption():
    selected = offering()
    output, _, _, _ = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected,
        presentation_generator=lambda **_kwargs: "maybe I have something...",
    )
    assert output.blocked is False
    assert output.offer_authorized is True
    assert output.delivery_payload["product_reference"] == str(selected.offering_id)
    assert output.delivery_payload["media_link"] == selected.delivery_url
    assert "USD 9.99" not in output.response_text
    assert "unlock it" in output.response_text.lower()
    assert output.diagnostic_metadata["presentation_authority_repair"] == {
        "applied": True,
        "reason": "PAID_PRESENTATION_NOT_AN_OFFER",
        "authority": "STRUCTURED_SELECTED_OFFERING",
    }
    assert output.diagnostic_metadata["paid_presentation_validated"] is True


def test_structured_offer_authority_repairs_numeric_price_leakage():
    selected = offering()
    output, _, _, _ = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected,
        presentation_generator=lambda **_kwargs: "Here it is, unlock it for $5.",
    )
    assert output.blocked is False
    assert output.offer_authorized is True
    assert "$5" not in output.response_text
    assert output.diagnostic_metadata["presentation_authority_repair"] == {
        "applied": True,
        "reason": "PAID_PRESENTATION_CONTRADICTORY_PRICE",
        "authority": "STRUCTURED_SELECTED_OFFERING",
    }
    assert output.diagnostic_metadata["numericPricePresentInAvaProse"] is False


def test_price_continuation_reuses_offer_but_repairs_repeated_paid_prose():
    selected = offering()
    intent_id = uuid4()
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
            selected=selected,
            reason=(CustomerSalesReasonCode
                    .CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION),
        ),
        active_purchase_intent_id=intent_id,
        active_offering_id=selected.offering_id,
        active_offer_status="PRESENTED",
        decision_metadata=MappingProxyType({
            "activeOfferContinuation": {
                "customerInitiatedOfferContinuation": True,
                "continuationIntentType": "PRICE_REQUEST",
                "nudgeCooldownApplies": False,
                "structuredOfferReused": True,
                "purchaseIntentReused": True,
                "relationshipDiscoverySuppressed": True,
            },
        }),
    )
    generated = iter((
        "Here you go — unlock it whenever you want.",
        "You can check it on the offer right here — unlock it whenever you want.",
    ))
    calls = []

    def generate(**kwargs):
        calls.append(kwargs)
        return next(generated)

    output, _, sales, _ = execute(
        decision, selected,
        message_text="how much is it?",
        chat_history=[{
            "role": "assistant",
            "content": "Here you go — unlock it whenever you want.",
        }],
        presentation_generator=generate,
    )

    assert len(sales.resolve_calls) == 1
    assert output.diagnostic_metadata["paidPresentationPurpose"] == (
        "PRICE_REQUEST_CONTINUATION"
    )
    assert output.diagnostic_metadata["sameOfferAsPreviousPresentation"] is True
    assert output.diagnostic_metadata["repetitionRepairAttempted"] is True
    assert output.diagnostic_metadata["repetitionRepairOutcome"] == "SUCCEEDED"
    assert calls[1]["repetition_repair"] is True
    assert "$9.99" not in output.response_text
    assert output.response_text.startswith("You can check it")
    assert output.diagnostic_metadata["active_purchase_intent_id"] == str(intent_id)


def test_send_link_continuation_uses_purpose_aware_safe_fallback():
    selected = offering()
    intent_id = uuid4()
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
            selected=selected,
            reason=(CustomerSalesReasonCode
                    .CUSTOMER_INITIATED_ACTIVE_OFFER_CONTINUATION),
        ),
        active_purchase_intent_id=intent_id,
        active_offering_id=selected.offering_id,
        active_offer_status="PRESENTED",
        decision_metadata=MappingProxyType({
            "activeOfferContinuation": {
                "customerInitiatedOfferContinuation": True,
                "continuationIntentType": "SEND_OR_LINK_REQUEST",
                "nudgeCooldownApplies": False,
                "structuredOfferReused": True,
                "purchaseIntentReused": True,
                "relationshipDiscoverySuppressed": True,
            },
        }),
    )
    output, _, sales, _ = execute(
        decision, selected,
        message_text="send me the link",
        presentation_generator=lambda **_kwargs: "maybe later",
    )
    assert len(sales.resolve_calls) == 1
    assert output.diagnostic_metadata["paidPresentationPurpose"] == (
        "SEND_OR_LINK_CONTINUATION"
    )
    assert output.diagnostic_metadata["paidPresentationWordingSource"] == (
        "PURPOSE_AWARE_SAFE_FALLBACK"
    )
    assert output.response_text == (
        "Here you go — the Unlock button has the link for this one."
    )
    assert "?" not in output.response_text
    assert "$9.99" not in output.response_text


def test_buyer_initiated_next_offer_wording_is_not_a_resend():
    selected = offering()
    decision = replace(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        active_offer_conversion_state="PURCHASED",
    )
    output, _, sales, _ = execute(
        decision, selected,
        message_text="what else have you got?",
        presentation_generator=lambda **_kwargs: "maybe later",
    )
    assert len(sales.resolve_calls) == 1
    assert output.diagnostic_metadata["paidPresentationPurpose"] == (
        "BUYER_INITIATED_NEXT_OFFER"
    )
    assert output.response_text.startswith("Here's another one")
    assert "$9.99" not in output.response_text
    assert output.offer_authorized is True


def test_paid_presentation_repetition_protection_never_suppresses_commerce():
    selected = offering()
    repeated = "Here you go — unlock it whenever you want."
    output, _, sales, _ = execute(
        sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
        selected,
        chat_history=[
            {"role": "assistant", "content": repeated},
            {"role": "assistant", "content": repeated},
            {"role": "assistant", "content": repeated},
        ],
        presentation_generator=lambda **_kwargs: repeated,
    )
    assert len(sales.resolve_calls) == 1
    assert output.offer_authorized is True
    assert output.delivery_payload["product_reference"] == str(selected.offering_id)
    assert output.diagnostic_metadata["repetitionRepairAttempted"] is True
    assert output.diagnostic_metadata["repetitionRepairOutcome"] == "SAFE_FALLBACK"
    assert output.response_text == repeated


def test_purpose_aware_fallbacks_are_price_neutral_and_question_free():
    selected = offering()
    outputs = {
        purpose: ConversationGateway._purpose_aware_paid_fallback(purpose, selected)
        for purpose in (
            "INITIAL_OFFER", "PRICE_REQUEST_CONTINUATION",
            "SEND_OR_LINK_CONTINUATION", "ALTERNATIVE_OFFER",
            "BUYER_INITIATED_NEXT_OFFER", "UPSELL", "CROSS_SELL",
            "SESSION_PAID_STEP",
        )
    }
    assert len(set(outputs.values())) >= 6
    for text in outputs.values():
        assert "?" not in text
        assert "$9.99" not in text
        assert "nine" not in text.lower()


def test_paid_offer_regeneration_does_not_preserve_bad_initial_draft_claims():
    selected = offering()
    for text, reason in (
        ("Pay at https://evil.example instead", "PAID_PRESENTATION_UNAUTHORIZED_URL"),
        ("I'll make it $5 for you", "PAID_PRESENTATION_CONTRADICTORY_PRICE"),
        ("I have a different bundle instead", "PAID_PRESENTATION_ALTERNATE_OFFER"),
    ):
        output, _, _, _ = execute(
            sales_decision(CustomerSalesDecisionType.PRESENT_OFFER, selected=selected),
            selected,
            response_text=text,
        )
        assert output.blocked is False
        assert output.offer_authorized is True
        assert output.diagnostic_metadata["paid_presentation_validated"] is True
        assert text not in output.response_text


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
    conversation_context = customer_brain.calls[0]["conversation_context"]
    assert {key: conversation_context[key] for key in (
        "purchase_acknowledgement_pending", "latest_message", "conversation_id",
        "requested_media_type", "recent_conversation_requests",
    )} == {
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


def test_purchase_acknowledgement_repairs_ordinary_chat_and_reports_final_truth():
    calls = []
    def repair(**kwargs):
        calls.append(kwargs)
        return "I saw you grabbed it — hope you enjoy it while you scroll."
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        response_text="No worries, take your time while you scroll.",
        acknowledgement_generator=repair,
    )
    assert output.blocked is False
    assert output.response_text == "I saw you grabbed it — hope you enjoy it while you scroll."
    assert len(calls) == 1
    assert sales.resolve_calls == []
    diagnostics = output.diagnostic_metadata
    assert diagnostics["purchaseAcknowledgementRequired"] is True
    assert diagnostics["purchaseAcknowledgementSatisfied"] is True
    assert diagnostics["purchase_acknowledgement_validated"] is True
    assert diagnostics["purchaseAcknowledgementRewriteAttempted"] is True
    assert diagnostics["purchaseAcknowledgementRewriteOutcome"] == "PROVIDER_REPAIR_SUCCEEDED"


def test_invalid_acknowledgement_repair_uses_safe_truth_preserving_fallback_once():
    calls = []
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        response_text="Unlock it when you're ready.",
        acknowledgement_generator=lambda **kwargs: calls.append(kwargs) or "Still scrolling?",
    )
    assert output.blocked is False
    assert output.response_text == "I saw you grabbed it — hope you enjoy this one."
    assert len(calls) == 1
    assert sales.resolve_calls == []
    assert output.diagnostic_metadata["purchaseAcknowledgementSatisfied"] is True
    assert output.diagnostic_metadata["purchaseAcknowledgementRewriteOutcome"] == (
        "PROVIDER_REPAIR_REJECTED_SAFE_FALLBACK"
    )


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
    ]["customer_safe_description"] == selected.description
    assert "title" not in engine.calls[0]["runtime_injection"][
        "commerce_decision"
    ]["selected_offering"]
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
        commerce_readiness={
            "conversation_ready_for_offer": False,
            "current_buying_intent": False,
            "recommended_conversational_action": "CONTINUE_CONVERSATION",
        },
    )

    assert output.diagnostic_metadata["legacy_offer_requested"] is False
    assert output.diagnostic_metadata["commerce_offer_authorized"] is True
    assert output.diagnostic_metadata["final_offer_authorized"] is True
    assert output.offer_authorized is True
    assert len(sales.resolve_calls) == 1


def test_gpt_keeps_wording_freedom_without_changing_commercial_strategy():
    outputs = [
        execute(
            sales_decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION),
            response_text=text,
        )[0]
        for text in (
            "haha okay, tell me what happened next",
            "wait 😂 now I need the rest of that story",
        )
    ]

    assert outputs[0].response_text != outputs[1].response_text
    assert {
        output.diagnostic_metadata["customer_sales_decision"]
        for output in outputs
    } == {"CONTINUE_CONVERSATION"}
    assert all(output.offer_authorized is False for output in outputs)


def test_ai_readiness_is_observational_and_cannot_change_continue_strategy():
    output, engine, sales, _ = execute(
        sales_decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION),
        engine_send_offer=True,
    )

    assert len(engine.calls) == 1
    assert output.offer_authorized is False
    assert sales.resolve_calls == []
    assert output.diagnostic_metadata["customer_sales_decision"] == (
        "CONTINUE_CONVERSATION"
    )
    authority = output.diagnostic_metadata["commercial_strategy_authority"]
    assert authority == {
        "owner": "CustomerSalesBrainService",
        "finalizedBeforeGeneration": True,
        "aiRole": "WORDING_AND_NON_AUTHORITATIVE_OBSERVATION",
        "aiAlteredFinalCommercialStrategy": False,
        "finalDecision": "CONTINUE_CONVERSATION",
        "reasonCode": "ACTIVE_OFFER_NOT_YET_ELIGIBLE_FOR_NUDGE",
    }
    observation = output.diagnostic_metadata[
        "ai_commerce_readiness_observation"
    ]
    assert observation["conversation_ready_for_offer"] is True
    assert observation["authority"] == "NON_AUTHORITATIVE_AI_OBSERVATION"
    assert observation["alteredFinalCommercialStrategy"] is False


def test_ai_readiness_cannot_replace_wait_backoff_or_acknowledgement_strategy():
    cases = (
        CustomerSalesDecisionType.WAIT,
        CustomerSalesDecisionType.BACK_OFF,
        CustomerSalesDecisionType.NO_SALE,
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
    )
    for decision_type in cases:
        decision = sales_decision(
            decision_type,
            reason=(CustomerSalesReasonCode.PURCHASE_VERIFIED
                    if decision_type is CustomerSalesDecisionType.CONGRATULATE_PURCHASE
                    else None),
            congratulate=(
                decision_type is CustomerSalesDecisionType.CONGRATULATE_PURCHASE
            ),
        )
        output, _, sales, _ = execute(decision, engine_send_offer=True)

        assert output.offer_authorized is False
        assert sales.resolve_calls == []
        assert output.diagnostic_metadata["customer_sales_decision"] == (
            decision_type.value
        )
        assert output.diagnostic_metadata[
            "commercial_strategy_authority"
        ]["aiAlteredFinalCommercialStrategy"] is False


def test_full_analysis_separates_final_strategy_from_ai_observation():
    output, _, _, _ = execute(
        sales_decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION),
    )

    analysis = output.diagnostic_metadata["commercial_summary"]
    assert analysis["finalSalesDecision"]["decision"] == (
        "CONTINUE_CONVERSATION"
    )
    assert analysis["commercialStrategyAuthority"]["owner"] == (
        "CustomerSalesBrainService"
    )
    assert analysis["aiCommerceReadinessObservation"]["authority"] == (
        "NON_AUTHORITATIVE_AI_OBSERVATION"
    )
    assert analysis["aiCommerceReadinessObservation"][
        "alteredFinalCommercialStrategy"
    ] is False


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
        CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER:
            CommerceExecutionPolicy.PRESENTATION_ALLOWED,
        CustomerSalesDecisionType.UPSELL:
            CommerceExecutionPolicy.PRESENTATION_ALLOWED,
        CustomerSalesDecisionType.CROSS_SELL:
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
                decision_type in {
                    CustomerSalesDecisionType.PRESENT_OFFER,
                    CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
                    CustomerSalesDecisionType.UPSELL,
                    CustomerSalesDecisionType.CROSS_SELL,
                }
            ) else None,
        )
        assert derive_commerce_execution_policy(decision) is policy
