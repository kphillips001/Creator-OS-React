from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.conversation_gateway import ConversationGatewayInput
from app.models.customer_sales_decision import (
    CustomerBuyerStage,
    CustomerSalesDecision,
    CustomerSalesDecisionType,
    CustomerSalesReasonCode,
    immutable_mapping,
)
from app.models.telegram_inbound import TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService


def sales_decision(*, action=CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER,
                   reason=CustomerSalesReasonCode.CONTENT_ALTERNATIVE,
                   receptiveness=None, active_intent=None):
    return CustomerSalesDecision(
        creator_profile_id=2, fanvue_account_id=2,
        external_fanvue_buyer_uuid=None, telegram_user_id=7,
        identity_resolved=False, decision=action, reason_code=reason,
        reason_summary="fixture", buyer_stage=CustomerBuyerStage.PROSPECT,
        commerce_signal=immutable_mapping({}),
        active_purchase_intent_id=active_intent, active_offering_id=None,
        active_offer_status=None, active_offer_conversion_state="NONE",
        recommended_offering_id=uuid4(), recommended_publication_id=uuid4(),
        recommended_delivery_url="https://example.test/offer",
        sell_allowed=True, nudge_allowed=False, upsell_allowed=False,
        cross_sell_allowed=False, congratulate_allowed=False,
        cooldown_until=None, evaluated_at=datetime.now(timezone.utc),
        decision_metadata=immutable_mapping({
            "commercialReceptiveness": receptiveness or {
                "currentCommercialInterest": False,
                "freshDirectIntentDetected": False,
                "commercialInterestType": "NONE",
            },
        }),
    )


def inbound(text):
    return ConversationGatewayInput(
        engine_user_id="fixture", message_text=text, chat_history=[],
        correlation_id="fixture-correlation",
    )


def test_ordinary_direct_question_blocks_unsupported_alternative_offer():
    result = ConversationGateway._apply_direct_question_precedence(
        sales_decision(), gateway_input=inbound("What do you usually do for fun?"),
    )

    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert result.sell_allowed is False
    assert result.recommended_offering_id is None
    evidence = result.decision_metadata["directQuestionPrecedence"]
    assert evidence["turnObligations"] == ["ANSWER_DIRECT_QUESTION"]
    assert evidence["commercialActionBlockedByObligationPrecedence"] is True


def test_multiple_questions_preserve_authoritative_direct_obligation():
    result = ConversationGateway._apply_direct_question_precedence(
        sales_decision(),
        gateway_input=inbound(
            "What's usual for you? How can I help you find something different?"
        ),
    )

    evidence = result.decision_metadata["directQuestionPrecedence"]
    assert "ANSWER_DIRECT_QUESTION" in evidence["turnObligations"]
    assert result.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION


def test_direct_commercial_question_preserves_authorized_offer():
    result = ConversationGateway._apply_direct_question_precedence(
        sales_decision(
            action=CustomerSalesDecisionType.PRESENT_OFFER,
            reason=CustomerSalesReasonCode.PRICE_REQUEST,
            receptiveness={
                "currentCommercialInterest": True,
                "freshDirectIntentDetected": True,
                "commercialInterestType": "PRICE_REQUEST",
            },
        ),
        gateway_input=inbound("What's in the bundle and how much is it?"),
    )

    assert result.decision is CustomerSalesDecisionType.PRESENT_OFFER
    assert result.sell_allowed is True
    assert result.decision_metadata["directQuestionPrecedence"][
        "commercialActionAllowed"
    ] is True


def test_active_offer_and_active_session_remain_authoritative():
    question = inbound("Would I get all five pictures if I buy it?")
    active_offer = ConversationGateway._apply_direct_question_precedence(
        sales_decision(active_intent=uuid4()), gateway_input=question,
    )
    active_session = ConversationGateway._apply_direct_question_precedence(
        sales_decision(), gateway_input=question, sales_session=SimpleNamespace(),
    )

    assert active_offer.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER
    assert active_session.decision is CustomerSalesDecisionType.PRESENT_ALTERNATIVE_OFFER


def test_no_direct_question_leaves_existing_commercial_behavior_unchanged():
    original = sales_decision()
    result = ConversationGateway._apply_direct_question_precedence(
        original, gateway_input=inbound("I'd like something different"),
    )
    assert result is original


class CorrectionRepository:
    def __init__(self):
        self.corrective = None
        self.suppressed = None

    def record_generation_attempt(self, *_args, **_kwargs): return None

    def schedule_quality_correction(self, operation_id, **kwargs):
        self.corrective = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="RETRYABLE"))

    def store_suppressed_generation(self, operation_id, **kwargs):
        self.suppressed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="SUPPRESSED"))


def generated_result(*, extra_reasons=()):
    return TelegramInboundResult(
        correlation_id="c", telegram_chat_id=1, telegram_user_id=1,
        message_id=1, engine_user_id="e", response_text="wrong answer",
        offer_authorized=False, offer_link=None, blocked=False,
        error_code=None, delivery_payload={},
        diagnostic_metadata={
            "conversationQualityReasons": list(extra_reasons),
            "conversationStyle": {
                "customerQuestionAnswered": False,
                "turnObligationsSatisfied": False,
                "turnObligations": ["ANSWER_DIRECT_QUESTION"],
                "satisfiedTurnObligations": [],
                "unsatisfiedTurnObligations": ["ANSWER_DIRECT_QUESTION"],
            },
        },
    )


def operation(attempt=1):
    return SimpleNamespace(
        operation_id=uuid4(), inbound_message_text="What do you do?",
        delivery_payload={}, generation_attempt_count=attempt,
        send_attempt_count=0, outbound_telegram_message_id=None,
    )


def test_jim_reason_family_gets_exactly_one_corrective_attempt():
    repository = CorrectionRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")

    first = service.generated(
        operation(1), generated_result(
            extra_reasons=("FINAL_TURN_OBLIGATION_FAILURE",),
        ),
    )

    assert first.state.value == "RETRYABLE"
    assert set(repository.corrective["reasons"]) == {
        "CUSTOMER_QUESTION_UNANSWERED",
        "FINAL_TURN_OBLIGATION_FAILURE",
        "TURN_OBLIGATIONS_UNSATISFIED",
    }


def test_failed_corrective_attempt_is_terminal_without_third_generation():
    repository = CorrectionRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")

    final = service.generated(
        operation(2), generated_result(
            extra_reasons=("FINAL_TURN_OBLIGATION_FAILURE",),
        ),
    )

    assert final.state.value == "SUPPRESSED"
    assert repository.corrective is None
    assert repository.suppressed["reason"].startswith(
        "quality_corrective_retry_exhausted:"
    )


def test_noncorrectable_quality_failure_never_authorizes_correction():
    repository = CorrectionRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")

    final = service.generated(
        operation(1), generated_result(
            extra_reasons=(
                "FINAL_TURN_OBLIGATION_FAILURE",
                "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",
            ),
        ),
    )

    assert final.state.value == "SUPPRESSED"
    assert repository.corrective is None
