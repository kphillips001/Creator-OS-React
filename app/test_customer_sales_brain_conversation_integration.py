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
from app.services.gpt_service import GPTService
from app.services.commerce_execution_policy import (
    CommerceExecutionPolicy,
    derive_commerce_execution_policy,
)
from app.models.commerce_mode import CommerceMode
from app.testing.session5_scenario_harness import HistoricalPurchaseFixtureBuilder


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
        commerce_readiness=None, diagnostics=None,
    ):
        self.send_offer = send_offer
        self.response_text = response_text
        self.commerce_readiness = commerce_readiness or {
            "conversation_ready_for_offer": True,
            "current_buying_intent": True,
        }
        self.diagnostics = dict(diagnostics or {})
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
            **self.diagnostics,
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


def test_verified_purchase_context_reaches_generation_with_safe_asset_detail():
    asset = SimpleNamespace(
        short_safe_summary="an outdoor portrait set",
        suggested_tags=["outdoor", "portrait"],
        detected_themes=["natural light"],
    )
    gateway = object.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(
        get_by_id=lambda asset_id: asset if asset_id == 42 else None
    )
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerCommerceMemory": {
                "verifiedPurchaseCount": 1,
                "ownedAssetIds": [42],
                "ownedOfferingIds": ["internal-offering-id"],
                "recentVerifiedPurchaseEvidence": [{
                    "assetIds": [42], "saleType": "SINGLE_IMAGE",
                }],
            },
        }),
    )

    context = gateway._commerce_runtime_injection(decision)["commerce_decision"]

    assert context["customer_commerce_memory"]["verifiedPurchaseCount"] == 1
    purchased = context["recent_purchased_content"]
    assert purchased["referenceIsUnambiguous"] is True
    assert purchased["purchasedContentHistoryCount"] == 1
    assert purchased["boundedHistoryEntryCount"] == 1
    assert purchased["maximumHistoryEntries"] == 20
    assert purchased["contentType"] == "SINGLE_IMAGE"
    assert purchased["safeSummary"] == "an outdoor portrait set"
    assert purchased["safeTags"] == ("outdoor", "portrait")
    assert purchased["safeThemes"] == ("natural light",)
    assert purchased["historyEntries"][0]["ownershipConfirmed"] is True


def test_multiple_purchases_project_bounded_ordered_authoritative_history():
    gateway = object.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(
        get_by_id=lambda asset_id: SimpleNamespace(
            short_safe_summary=("outdoor portrait" if asset_id == 42 else None),
            suggested_tags=(["outdoor"] if asset_id == 42 else []),
            detected_themes=[],
        )
    )

    result = gateway._recent_purchased_content_context({
        "verifiedPurchaseCount": 2,
        "ownedAssetIds": [41, 42],
        "recentVerifiedPurchaseEvidence": [
            {"assetIds": [41], "grossMinor": 1200, "currency": "USD"},
            {"assetIds": [42], "grossMinor": 1800, "currency": "USD"},
        ],
    })

    assert result["referenceIsUnambiguous"] is False
    assert [item["ordinal"] for item in result["historyEntries"]] == [1, 2]
    assert result["historyEntries"][1]["safeTags"] == ("outdoor",)
    assert all(item["ownershipConfirmed"] for item in result["historyEntries"])


def test_large_purchase_history_projection_is_capped_at_twenty():
    gateway = object.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(get_by_id=lambda _asset_id: None)
    result = gateway._recent_purchased_content_context({
        "verifiedPurchaseCount": 100,
        "recentVerifiedPurchaseEvidence": [
            {"assetIds": [index]} for index in range(1, 31)
        ],
    })

    assert result["boundedHistoryEntryCount"] == 20
    assert result["purchasedContentHistoryCount"] == 100
    assert [item["ordinal"] for item in result["historyEntries"]] == list(
        range(81, 101)
    )


def test_c13_fixture_intelligence_projects_and_resolves_authoritatively():
    specifications = HistoricalPurchaseFixtureBuilder.C13_PURCHASED_ASSET_INTELLIGENCE
    assets = {
        2481: SimpleNamespace(
            short_safe_summary=specifications[1]["short_description"],
            suggested_tags=specifications[1]["tags"],
            detected_themes=specifications[1]["themes"],
        ),
        2482: SimpleNamespace(
            short_safe_summary=specifications[2]["short_description"],
            suggested_tags=specifications[2]["tags"],
            detected_themes=specifications[2]["themes"],
        ),
    }
    gateway = object.__new__(ConversationGateway)
    gateway._asset_repository = SimpleNamespace(get_by_id=assets.get)
    projected = gateway._recent_purchased_content_context({
        "verifiedPurchaseCount": 2,
        "ownedAssetIds": [2481, 2482],
        "recentVerifiedPurchaseEvidence": [
            {
                "purchasedAt": "2026-09-03T16:08:33.137156-05:00",
                "saleType": "SINGLE_IMAGE", "assetIds": [2481],
                "grossMinor": 1200, "currency": "USD",
            },
            {
                "purchasedAt": "2026-09-03T16:08:33.817764-05:00",
                "saleType": "SINGLE_IMAGE", "assetIds": [2482],
                "grossMinor": 1800, "currency": "USD",
            },
        ],
    })
    resolve = GPTService._resolve_purchase_history_reference

    assert projected["historyEntries"][0]["safeTags"] == (
        "indoor", "portrait", "studio",
    )
    assert projected["historyEntries"][1]["safeTags"] == (
        "outdoor", "portrait", "natural light",
    )
    assert resolve("the indoor one", projected)["resolvedOrdinal"] == 1
    assert resolve("the outdoor one", projected)["resolvedOrdinal"] == 2
    assert resolve("the second set", projected)["resolutionType"] == "ORDINAL"
    assert resolve("the $18 one", projected)["resolutionType"] == "UNIQUE_PRICE"
    assert resolve("the beach one", projected)["purchaseHistoryReferentResolved"] is False
    assert resolve("the portrait one", projected)["purchaseHistoryReferentResolved"] is False


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
    engine_diagnostics=None,
    conversational_memory=None,
):
    engine = Brain(
        send_offer=engine_send_offer, response_text=response_text,
        commerce_readiness=commerce_readiness,
        diagnostics=engine_diagnostics,
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
            conversational_memory=dict(conversational_memory or {}),
        ),
    ))
    return output, engine, sales, customer_brain


def test_attempt3_aggregate_acknowledgement_uses_deletion_first_repair():
    original = (
        "Looks like I’m on a roll with you—two for two, huh? "
        "Should I be worried or flattered? 😏"
    )
    provider_calls = []
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    output, _, _, _ = execute(
        decision,
        acknowledgement=True,
        message_text="you've been two for two so far",
        response_text=original,
        acknowledgement_generator=lambda **kwargs: (
            provider_calls.append(kwargs) or "you’re on fire"
        ),
        conversational_memory={"memoryDiagnostics": {
            "conversationStyle": {
                "manufacturedQuestionRisk": True,
                "unauthorizedRelationshipQuestion": True,
                "questionReason": "MANUFACTURED_ENGAGEMENT",
            },
        }},
    )
    diagnostics = output.diagnostic_metadata

    assert output.response_text == "Looks like I’m on a roll with you—two for two."
    assert provider_calls == []
    assert diagnostics["purchaseAcknowledgementRewriteOutcome"] == (
        "DELETION_FIRST_REPAIR_SUCCEEDED"
    )
    assert diagnostics["aggregatePurchaseReactionRequired"] is True
    assert diagnostics["aggregatePurchaseReactionSatisfied"] is True
    assert diagnostics["retrospectivePurchaseReactionSatisfied"] is True
    assert diagnostics["semanticPreservationAfterRewrite"] is True
    assert diagnostics["purchaseAcknowledgementQuestionAuthorized"] is False
    assert diagnostics["purchaseAcknowledgementRewriteRemovedSegments"] == [
        "huh?", "Should I be worried or flattered?"
    ]
    assert diagnostics["purchaseAcknowledgementCommittedResponse"] == (
        output.response_text
    )


def test_aggregate_ava_subject_candidate_passes_without_unnecessary_rewrite():
    provider_calls = []
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    output, _, _, _ = execute(
        decision, acknowledgement=True,
        message_text="you've been two for two so far",
        response_text="Guess I\u2019m on fire today.",
        acknowledgement_generator=lambda **kwargs: (
            provider_calls.append(kwargs) or "replacement"
        ),
    )
    diagnostics = output.diagnostic_metadata

    assert output.response_text == "Guess I\u2019m on fire today."
    assert provider_calls == []
    assert diagnostics["purchaseAcknowledgementRewriteOutcome"] == "NOT_REQUIRED"
    assert diagnostics["semanticFrameSubject"] == (
        "AVA_OR_PURCHASED_CONTENT_TRACK_RECORD"
    )
    assert diagnostics["finalResponseSubjectCompatible"] is True
    assert diagnostics["contradictorySemanticSegmentDetected"] is False
    assert diagnostics["semanticPreservationAfterRewrite"] is True


def test_aggregate_mixed_subject_reversal_is_deleted_before_commit():
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    output, _, _, _ = execute(
        decision, acknowledgement=True,
        message_text="you've been two for two so far",
        response_text="Look at you, on a roll! Glad they both landed.",
    )
    diagnostics = output.diagnostic_metadata

    assert output.response_text == "Glad they both landed."
    assert diagnostics["purchaseAcknowledgementRewriteOutcome"] == (
        "DELETION_FIRST_REPAIR_SUCCEEDED"
    )
    assert diagnostics["purchaseAcknowledgementRewriteRemovedSegments"] == [
        "Look at you, on a roll"
    ]
    assert diagnostics["preRewriteContradictorySemanticSegmentDetected"] is True
    assert diagnostics["finalResponseSubjectCompatible"] is True
    assert diagnostics["contradictorySemanticSegmentDetected"] is False


def test_resolved_second_purchase_referent_reaches_protected_semantic_frame():
    candidate = "Glad you liked that one more—guess I nailed the vibe just right this time."
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    reference = {
        "purchaseHistoryReferentDetected": True,
        "purchaseHistoryReferentResolved": True,
        "resolutionType": "ORDINAL",
        "resolvedOrdinal": 2,
    }
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="I liked the second set even more",
        response_text=candidate,
        conversational_memory={"memoryDiagnostics": {
            "conversationStyle": {"purchaseHistoryReference": reference},
        }},
    )
    diagnostics = output.diagnostic_metadata

    assert output.response_text == candidate
    assert sales.resolve_calls == []
    assert diagnostics["purchaseAcknowledgementRewriteOutcome"] == "NOT_REQUIRED"
    assert diagnostics["purchaseAcknowledgementReactionState"] == (
        "COMPLETED_POSITIVE_EXPERIENCE"
    )
    assert diagnostics["preRewriteSemanticFrame"] == {
        "purchaseReactionState": "COMPLETED_POSITIVE_EXPERIENCE",
        "verifiedPurchaseCount": 2,
        "aggregatePurchaseReactionRequired": False,
        "retrospectivePurchaseReactionRequired": True,
        "aggregateSubject": None,
        "singularAcknowledgementAloneSufficient": True,
        **reference,
        "comparativePurchaseReaction": True,
        "aggregatePurchaseReference": False,
        "resolvedPurchaseCount": 0,
        "resolvedPurchaseIds": [],
        "purchaseFeedbackAggregate": False,
    }
    assert diagnostics["retrospectivePurchaseReactionSatisfied"] is True
    assert diagnostics["semanticPreservationAfterRewrite"] is True


def test_resolved_comparative_safe_fallback_is_retrospective_and_comparative():
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    output, _, _, _ = execute(
        decision, acknowledgement=True,
        message_text="I liked the second set even more",
        response_text="Unlock it when you're ready.",
        acknowledgement_generator=lambda **_: "Still deciding?",
        conversational_memory={"memoryDiagnostics": {"conversationStyle": {
            "purchaseHistoryReference": {
                "purchaseHistoryReferentDetected": True,
                "purchaseHistoryReferentResolved": True,
                "resolutionType": "ORDINAL",
                "resolvedOrdinal": 2,
            },
        }}},
    )

    assert output.response_text == "I'm glad that one landed even better for you."
    assert "hope you enjoy" not in output.response_text.lower()
    assert output.diagnostic_metadata["purchaseAcknowledgementSatisfied"] is True


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
        "active_purchase_intent_id": None,
        "active_offering_id": None,
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
    output, engine, sales, _ = execute(
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
    runtime_context = engine.calls[0]["runtime_injection"]["commerce_decision"]
    assert runtime_context["active_purchase_intent_id"] == str(intent_id)
    assert runtime_context["active_offering_id"] == str(selected.offering_id)
    assert len(sales.resolve_calls) == 1


def test_wait_projects_active_structured_ids_into_generation_context():
    selected = offering()
    intent_id = uuid4()
    decision = replace(
        sales_decision(CustomerSalesDecisionType.WAIT),
        active_purchase_intent_id=intent_id,
        active_offering_id=selected.offering_id,
        active_offer_status="PRESENTED",
        decision_metadata=MappingProxyType({
            "objectionRecovery": {
                "originalPrice": 900,
                "recoverySuppressionReason": "RECOVERY_LIMIT_REACHED",
            },
        }),
    )
    _, engine, _, _ = execute(
        decision, selected,
        message_text="do you have something smaller in that range?",
    )
    context = engine.calls[0]["runtime_injection"]["commerce_decision"]
    assert context["decision"] == "WAIT"
    assert context["active_purchase_intent_id"] == str(intent_id)
    assert context["active_offering_id"] == str(selected.offering_id)
    assert context["current_offer_status"] == "PRESENTED"
    assert context["objection_recovery"]["originalPrice"] == 900


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


def test_low_cost_nurture_budget_suppresses_before_provider_generation():
    decision = replace(
        sales_decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION),
        decision_metadata=MappingProxyType({
            "customerValueAttention": {
                "timeWasterScore": 6,
                "timeWasterRisk": "HIGH",
                "attentionTier": "LOW",
                "effortMode": "MINIMAL",
                "lowCostNurtureActive": True,
                "nurtureResponsesUsed": 1,
                "nurtureResponseBudget": 1,
                "optionalOrdinaryReplySuppressed": True,
                "suppressionReason": "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED",
            },
            "outboundSuppression": {
                "suppressed": True,
                "outcome": "NO_RESPONSE",
                "reason": "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED",
                "inboundProcessingRequired": True,
                "futureCommercialReentryAllowed": True,
                "freshCommercialIntentDetected": False,
                "nurtureBypassedForCommercialIntent": False,
            },
        }),
    )
    output, engine, sales, customer_brain = execute(
        decision, message_text="no, I'm not paying; I'm just looking",
    )

    assert len(customer_brain.calls) == 1
    assert engine.calls == []
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []
    assert output.blocked is True
    assert output.response_text == ""
    assert output.delivery_payload == {}
    assert output.diagnostic_metadata["ai_generation_count"] == 0
    assert output.diagnostic_metadata["outbound_suppression"]["reason"] == (
        "LOW_COST_NURTURE_DAILY_BUDGET_CONSUMED"
    )


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


def test_completed_positive_purchase_reaction_commits_generated_copy_and_final_truth():
    candidate = (
        "I'm glad you're loving it! Feels good to find a set that hits just right, "
        "doesn't it?"
    )
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="that set I bought was really good",
        response_text=candidate,
    )
    diagnostics = output.diagnostic_metadata
    style = diagnostics["conversationStyle"]
    assert output.blocked is False
    assert output.response_text == candidate
    assert "hope you enjoy" not in output.response_text.lower()
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []
    assert diagnostics["purchaseAcknowledgementReactionState"] == (
        "COMPLETED_POSITIVE_EXPERIENCE"
    )
    assert diagnostics["purchaseAcknowledgementRewriteAttempted"] is False
    assert diagnostics["purchaseAcknowledgementFinalCandidate"] == output.response_text
    assert style["finalValidationFinalCandidate"] == output.response_text
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["purchaseAcknowledged"] is True
    assert style["turnObligationsSatisfied"] is True


def test_completed_positive_purchase_reaction_with_known_purchase_noun_uses_retrospective_fallback():
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="hey, I liked the last set",
        response_text="I saw you grabbed it - hope you enjoy this one.",
        acknowledgement_generator=lambda **_: "Still scrolling?",
    )
    diagnostics = output.diagnostic_metadata
    style = diagnostics["conversationStyle"]
    assert output.response_text.startswith("I'm glad you liked it")
    assert "hope you enjoy" not in output.response_text.lower()
    assert diagnostics["purchaseAcknowledgementReactionState"] == (
        "COMPLETED_POSITIVE_EXPERIENCE"
    )
    assert diagnostics["purchaseAcknowledgementFinalCandidate"] == output.response_text
    assert style["finalValidationFinalCandidate"] == output.response_text
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []


def test_repeat_buyer_aggregate_positive_reaction_uses_plural_retrospective_fallback():
    decision = replace(
        sales_decision(
            CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
            reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
            congratulate=True,
        ),
        buyer_stage=CustomerBuyerStage.REPEAT_BUYER,
        decision_metadata=MappingProxyType({
            "customerValueAttention": {"purchaseCount": 2},
        }),
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="you've been two for two so far",
        response_text="I saw you grabbed it - hope you enjoy this one.",
        acknowledgement_generator=lambda **_: "What do you want next?",
    )
    diagnostics = output.diagnostic_metadata
    style = diagnostics["conversationStyle"]
    assert "streak" in output.response_text.lower()
    assert "they've landed" in output.response_text.lower()
    assert "hope you enjoy" not in output.response_text.lower()
    assert diagnostics["purchaseAcknowledgementReactionState"] == (
        "COMPLETED_POSITIVE_EXPERIENCE"
    )
    assert diagnostics["purchaseAcknowledgementFinalCandidate"] == output.response_text
    assert style["finalValidationFinalCandidate"] == output.response_text
    assert style["currentTopicCoverageSatisfied"] is True
    assert style["foregroundSemanticRelevanceSatisfied"] is True
    assert style["turnObligationsSatisfied"] is True
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []


def test_just_purchased_retains_prospective_acknowledgement():
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="I just bought the set",
        response_text="I saw you grabbed it — hope you enjoy this one.",
    )
    assert output.response_text == "I saw you grabbed it — hope you enjoy this one."
    assert output.diagnostic_metadata["purchaseAcknowledgementReactionState"] == (
        "JUST_PURCHASED"
    )
    assert sales.resolve_calls == []


def test_completed_negative_purchase_reaction_uses_grounded_safe_fallback():
    decision = sales_decision(
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE,
        reason=CustomerSalesReasonCode.PURCHASE_VERIFIED,
        congratulate=True,
    )
    output, _, sales, _ = execute(
        decision, acknowledgement=True,
        message_text="I bought it but didn't like it",
        response_text="Congrats — hope you enjoy it!",
        acknowledgement_generator=lambda **_: "So glad you loved it!",
    )
    diagnostics = output.diagnostic_metadata
    assert output.blocked is False
    assert output.response_text == (
        "I'm sorry that one didn't land for you — I appreciate you telling me."
    )
    assert diagnostics["purchaseAcknowledgementReactionState"] == (
        "COMPLETED_NEGATIVE_EXPERIENCE"
    )
    assert diagnostics["purchaseAcknowledgementFinalCandidate"] == output.response_text
    assert diagnostics["conversationStyle"]["finalValidationFinalCandidate"] == (
        output.response_text
    )
    assert sales.resolve_calls == []
    assert sales.recommend_calls == []


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
