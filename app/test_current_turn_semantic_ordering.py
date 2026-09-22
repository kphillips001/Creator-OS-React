from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.conversation_gateway import (
    ConversationBrainContext,
    ConversationGatewayInput,
)
from app.models.telegram_inbound import TelegramInboundResult
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
)
from app.services.conversation_gateway import ConversationGateway
from app.services.conversation_progression_quality_service import (
    ConversationProgressionFailure,
)
from app.services.current_turn_semantic_classification_service import (
    CurrentTurnSemanticClassificationService,
)
from app.services.customer_heat_signal_service import CustomerHeatSignalService
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.engine.decision_engine import DecisionEngine


ERIC_TEXT = (
    "That depends on how naughty you would like to be with me Ava. "
    "Because I'd love to get you naked and kiss you all over your beautiful body."
)
ERIC_SEMANTICS = {
    "intent_level": "low",
    "buying_intent": False,
    "close_ready": False,
    "route": "chat",
    "sexual_engagement": True,
    "explicit_without_buying_intent": True,
    "escalation_ready": True,
    "recommended_action": "build_tension",
    "confidence": .95,
    "monetization_intent": False,
    "purchase_language_present": False,
}


class RecordingBrain:
    def __init__(self):
        self.contexts = []

    def evaluate_for_telegram_user(self, **kwargs):
        self.contexts.append(dict(kwargs["conversation_context"]))
        return CustomerSalesDecision(
            creator_profile_id=2, fanvue_account_id=2,
            external_fanvue_buyer_uuid=None, telegram_user_id=42,
            identity_resolved=False,
            decision=CustomerSalesDecisionType.CONTINUE_CONVERSATION,
            reason_code=CustomerSalesReasonCode.CURRENT_TURN_NOT_READY,
            reason_summary="test", buyer_stage=CustomerBuyerStage.PROSPECT,
            commerce_signal={}, active_purchase_intent_id=None,
            active_offering_id=None, active_offer_status=None,
            active_offer_conversion_state="NONE", recommended_offering_id=None,
            recommended_publication_id=None, recommended_delivery_url=None,
            sell_allowed=False, nudge_allowed=False, upsell_allowed=False,
            cross_sell_allowed=False, congratulate_allowed=False,
            cooldown_until=None, evaluated_at=datetime.now(timezone.utc),
            decision_metadata={},
        )


class OneShotEngine:
    def __init__(self, *, classifier_result=ERIC_SEMANTICS, error=None):
        self.classifier_result = classifier_result
        self.error = error
        self.classifier_calls = 0
        self.process_calls = 0
        self.runtime = None

    def classify_current_turn(self, *, user_id, message):
        self.classifier_calls += 1
        if isinstance(self.classifier_result, Exception):
            raise self.classifier_result
        return dict(self.classifier_result)

    def process_message(self, user_id, message, chat_history=None,
                        runtime_injection=None):
        self.process_calls += 1
        self.runtime = dict(runtime_injection or {})
        if self.error:
            raise self.error
        return {
            "response": "A bounded reply.",
            "send_offer": False,
            "offer": {"offer_type": "none", "content": None},
            "route": {"route": "chat"},
            "mode": "conversation",
        }


def gateway_request(*, historical=False):
    return ConversationGatewayInput(
        engine_user_id="telegram:42",
        message_text=ERIC_TEXT,
        chat_history=[],
        correlation_id="telegram:42:6880",
        brain_context=ConversationBrainContext(
            creator_profile_id=2,
            customer_identifier="telegram:42",
            conversation_identifier="telegram:42:6880",
            telegram_user_id=42,
            telegram_chat_id=42,
            fanvue_account_id=2,
        ),
        quality_correction_context=(
            {"approvedHistoricalCorrection": {"operationKind": "HISTORICAL_CORRECTIVE"}}
            if historical else {}
        ),
    )


@pytest.mark.parametrize("historical", [False, True])
def test_primary_and_historical_paths_compute_once_feed_sales_brain_and_reuse(historical):
    engine = OneShotEngine()
    brain = RecordingBrain()
    gateway = ConversationGateway(
        engine,
        allowed_fanvue_hostnames=["fanvue.com"],
        customer_sales_brain_service=brain,
    )

    result = gateway.execute(gateway_request(historical=historical))

    assert result.blocked is False
    assert engine.classifier_calls == 1
    assert engine.process_calls == 1
    assert brain.contexts[0]["classifier_result"] == ERIC_SEMANTICS
    assert engine.runtime["precomputed_classifier_result"] == ERIC_SEMANTICS
    durable = result.diagnostic_metadata["currentTurnSemanticClassification"]
    assert durable["status"] == "AVAILABLE"
    assert durable["result"]["sexual_engagement"] is True
    assert "reason" not in durable["result"]


def test_classifier_failure_is_fail_closed_and_does_not_fabricate_semantics():
    engine = OneShotEngine(classifier_result=RuntimeError("provider unavailable"))
    brain = RecordingBrain()
    result = ConversationGateway(
        engine,
        allowed_fanvue_hostnames=["fanvue.com"],
        customer_sales_brain_service=brain,
    ).execute(gateway_request())

    assert result.blocked is False
    assert engine.classifier_calls == 1
    assert "classifier_result" not in brain.contexts[0]
    assert "precomputed_classifier_result" not in engine.runtime
    diagnostic = result.diagnostic_metadata["currentTurnSemanticClassification"]
    assert diagnostic["status"] == "UNAVAILABLE"
    assert diagnostic["failureReason"] == "CLASSIFIER_EXCEPTION"
    assert "provider unavailable" not in str(diagnostic)


def test_eric_semantics_create_customer_led_heat_and_remove_only_warmup_blocker():
    heat = CustomerHeatSignalService().project(
        message=ERIC_TEXT,
        classifier_result=ERIC_SEMANTICS,
        contextual_tone={"sexualOrProvocative": True},
    )
    assert heat["detected"] is True
    assert heat["strength"] == "STRONG"
    assert heat["initiationSource"] == "CUSTOMER_INITIATED"
    assert heat["warmupOverrideEligible"] is True

    brain = object.__new__(CustomerSalesBrainService)
    brain.config = SimpleNamespace(sexual_receptiveness_min_engagements=4)
    context = {
        "inbound_message_count": 20,
        "sexual_engagement_count": 3,
        "sexual_engagement_only": True,
        "contextual_customer_tone": {"sexualOrProvocative": True},
        "customer_heat_signal": heat,
        "sexual_sales_opportunity": {"sexualSalesOpportunityEligible": True},
        "effective_content_selling_allowed": True,
    }
    assessment = brain._proactive_hot_opportunity_assessment(
        context, active_purchase_intent=False, active_sales_session=False,
    )
    assert assessment["warmupOverrideApplied"] is True
    assert assessment["warmupOverrideReason"] == "WARMUP_OVERRIDE_CUSTOMER_HEAT"
    assert "SUSTAINED_SEXUAL_RECEPTIVENESS_REQUIRED" not in assessment[
        "hotOpportunityBlockers"
    ]
    assert assessment["offerAuthorized"] is False


@pytest.mark.parametrize("message", [
    "You're beautiful",
    "Hey babe 😘",
    "Good morning sweetheart",
    "haha maybe",
])
def test_semantic_availability_does_not_turn_weak_affection_into_heat(message):
    weak = {
        **ERIC_SEMANTICS,
        "sexual_engagement": message == "haha maybe",
        "explicit_without_buying_intent": False,
        "escalation_ready": False,
        "recommended_action": "chat",
        "confidence": .55,
    }
    history = [{"role": "assistant", "content": "You're trouble 😉"}]
    result = CustomerHeatSignalService().project(
        message=message,
        classifier_result=weak,
        contextual_tone={"sexualOrProvocative": message == "haha maybe"},
        recent_transcript=history,
    )
    assert result["warmupOverrideEligible"] is False


def test_progression_failure_is_exposed_as_sanitized_gateway_diagnostics():
    failure = ConversationProgressionFailure(
        "Final response failed bounded conversation progression: TEST",
        {
            "authority": "ConversationProgressionQualityService",
            "rejectedCandidateText": "bounded candidate",
            "candidateDialogueFunction": "OBSERVATION",
            "recentDialogueFunctions": ["OBSERVATION", "ACKNOWLEDGEMENT_REACTION"],
            "rewriteAttempted": True,
            "rewriteResult": "NONCOMPLIANT_REWRITE",
            "finalBlockingReasons": ["SEQUENTIAL_LOW_NOVELTY_DIALOGUE_FUNCTION_LOOP"],
        },
    )
    result = ConversationGateway(
        OneShotEngine(error=failure),
        allowed_fanvue_hostnames=["fanvue.com"],
    ).execute(gateway_request())
    diagnostic = result.diagnostic_metadata["conversationProgressionFailure"]
    assert result.error_code == "decision_engine_exception"
    assert diagnostic["candidateDialogueFunction"] == "OBSERVATION"
    assert diagnostic["rewriteAttempted"] is True
    assert "Final response failed" not in str(diagnostic)


def test_generation_failure_persists_only_bounded_semantic_and_progression_evidence():
    class Repository:
        def __init__(self):
            self.kwargs = None

        def fail_generation(self, operation_id, **kwargs):
            self.kwargs = kwargs
            return "failed"

    repository = Repository()
    service = object.__new__(OrdinaryChatReplyService)
    service.repository = repository
    service.worker_id = "worker"
    operation = SimpleNamespace(operation_id="operation")
    result = TelegramInboundResult(
        correlation_id="correlation", telegram_chat_id=42,
        telegram_user_id=42, message_id=6880, engine_user_id="telegram:42",
        response_text="", offer_authorized=False, offer_link=None,
        blocked=True, error_code="decision_engine_exception",
        delivery_payload={},
        diagnostic_metadata={
            "currentTurnSemanticClassification": {
                "status": "AVAILABLE", "result": {"sexual_engagement": True},
            },
            "conversationProgressionFailure": {
                "candidateDialogueFunction": "OBSERVATION",
            },
            "unrelatedProviderInternals": {"secret": "must-not-persist"},
        },
    )

    assert service.generated(operation, result) == "failed"
    evidence = repository.kwargs["evidence"]["generationFailureDiagnostics"]
    assert set(evidence) == {
        "currentTurnSemanticClassification", "conversationProgressionFailure",
    }
    assert "unrelatedProviderInternals" not in str(evidence)


def test_sanitizer_binds_exact_message_without_persisting_provider_reason():
    diagnostic, reusable = CurrentTurnSemanticClassificationService().classify(
        message=ERIC_TEXT,
        correlation_id="operation:6880",
        classifier=lambda **_: {**ERIC_SEMANTICS, "reason": "provider explanation"},
        classified_at=datetime(2026, 9, 19, tzinfo=timezone.utc),
    )
    assert reusable["reason"] == "provider explanation"
    assert "reason" not in diagnostic["result"]
    assert diagnostic["messageSha256"]
    assert diagnostic["correlationId"] == "operation:6880"


def test_decision_engine_reuses_precomputed_classification_without_provider_call():
    class Classifier:
        def __init__(self):
            self.calls = 0

        def classify_message(self, **kwargs):
            self.calls += 1
            return {"route": "provider-result"}

    engine = object.__new__(DecisionEngine)
    engine.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    engine.gpt_intent_classifier = Classifier()

    result = engine._classify_current_turn_once(
        message=ERIC_TEXT,
        user_memory={"customer": "memory"},
        runtime_injection={"precomputed_classifier_result": ERIC_SEMANTICS},
    )

    assert result == ERIC_SEMANTICS
    assert result is not ERIC_SEMANTICS
    assert engine.gpt_intent_classifier.calls == 0


def test_decision_engine_classifier_fallback_remains_available_without_precompute():
    class Classifier:
        def __init__(self):
            self.calls = []

        def classify_message(self, **kwargs):
            self.calls.append(kwargs)
            return {"route": "provider-result"}

    engine = object.__new__(DecisionEngine)
    engine.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    engine.gpt_intent_classifier = Classifier()

    result = engine._classify_current_turn_once(
        message="hello", user_memory={"known": True}, runtime_injection={},
    )

    assert result == {"route": "provider-result"}
    assert engine.gpt_intent_classifier.calls == [{
        "message": "hello", "memory": {"known": True},
    }]
