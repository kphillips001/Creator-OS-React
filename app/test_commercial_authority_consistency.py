from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.customer_sales_decision import CustomerSalesDecisionType
from app.models.telegram_inbound import TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.corrective_generation_evidence_service import (
    CorrectiveGenerationEvidenceService,
)
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.test_global_selling_permissions import decision


def gateway_input(authority):
    return SimpleNamespace(quality_correction_context={
        "preGenerationCommercialDecision": authority,
    })


def cold_authority():
    return {
        "current_commercial_interest": False,
        "commercial_interest_type": "NONE",
        "customer_heat": "COLD",
        "fresh_direct_intent": False,
        "commercial_bypass_eligible": False,
        "active_offer_reservation_authorized": False,
        "historical_commercial_signals": ["PAST_PPVS"],
    }


@pytest.mark.parametrize("action", [
    CustomerSalesDecisionType.TEASE,
    CustomerSalesDecisionType.BUILD_INTEREST,
    CustomerSalesDecisionType.PRESENT_OFFER,
    CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER,
    CustomerSalesDecisionType.UPSELL,
])
def test_cold_current_turn_normalizes_sales_progression_to_ordinary_chat(action):
    original = decision(action)
    normalized = ConversationGateway._apply_current_turn_commercial_authority(
        original, gateway_input=gateway_input(cold_authority()),
    )
    assert normalized.decision is CustomerSalesDecisionType.CONTINUE_CONVERSATION
    assert normalized.recommended_offering_id is None
    assert normalized.sell_allowed is False
    consistency = normalized.decision_metadata["commercialAuthorityConsistency"]
    assert consistency["requestedDecision"] == action.value
    assert consistency["historicalSignalsPreservedAsContext"] is True


def test_ordinary_answer_is_unchanged_without_commercial_authority():
    ordinary = decision(CustomerSalesDecisionType.CONTINUE_CONVERSATION)
    assert ConversationGateway._apply_current_turn_commercial_authority(
        ordinary, gateway_input=gateway_input(cold_authority()),
    ) is ordinary


@pytest.mark.parametrize("authority_key", [
    "commercial_bypass_eligible",
    "active_offer_reservation_authorized",
])
def test_fresh_intent_or_active_offer_authority_preserves_commercial_action(
    authority_key,
):
    authority = cold_authority()
    authority[authority_key] = True
    commercial = decision(CustomerSalesDecisionType.PRESENT_OFFER)
    assert ConversationGateway._apply_current_turn_commercial_authority(
        commercial, gateway_input=gateway_input(authority),
    ) is commercial


class Repository:
    def __init__(self):
        self.corrective = None
        self.suppressed = None

    def recent_ava_responses(self, _operation):
        return ["An older exact Ava reply"]

    def schedule_quality_correction(self, operation_id, **kwargs):
        evidence = CorrectiveGenerationEvidenceService.build(
            response_payload=kwargs["response_payload"],
            reasons=kwargs["reasons"],
            recent_ava_responses=kwargs["recent_ava_responses"],
        )
        self.corrective = evidence
        return SimpleNamespace(
            operation_id=operation_id,
            state=SimpleNamespace(value="RETRYABLE"),
            generation_attempt_count=1,
            send_attempt_count=0,
            delivery_payload={
                "qualityCorrectiveRetry": evidence,
                "preGenerationCommercialDecision": cold_authority(),
            },
        )

    def store_suppressed_generation(self, operation_id, **kwargs):
        self.suppressed = kwargs
        return SimpleNamespace(
            operation_id=operation_id,
            state=SimpleNamespace(value="SUPPRESSED"),
            **kwargs,
        )


def operation(*, attempt=1, obligations=("ACKNOWLEDGE_COMPLIMENT",)):
    return SimpleNamespace(
        operation_id=uuid4(),
        inbound_sender_telegram_user_id=7,
        telegram_chat_id=8,
        inbound_message_text="You are really beautiful",
        inbound_telegram_message_id=9,
        inbound_received_at=datetime.now(timezone.utc),
        delivery_payload={
            "preGenerationCommercialDecision": cold_authority(),
        },
        burst_obligations=obligations,
        burst_member_obligations=(),
        generation_attempt_count=attempt,
        send_attempt_count=0,
        outbound_telegram_message_id=None,
        conversation_burst_id=None,
    )


def candidate(*reasons):
    return TelegramInboundResult(
        correlation_id="c",
        telegram_chat_id=8,
        telegram_user_id=7,
        message_id=9,
        engine_user_id="telegram:7",
        response_text="Unlock this paid set",
        offer_authorized=True,
        offer_link="https://example.invalid",
        blocked=False,
        error_code=None,
        delivery_type="PRIVATE_CHAT_UNLOCK",
        delivery_mode="PAID",
        delivery_requires_payment=True,
        delivery_payload={
            "type": "PRIVATE_CHAT_UNLOCK",
            "message_text": "Unlock this paid set",
        },
        diagnostic_metadata={
            "conversationQualityReasons": list(reasons),
            "conversationStyle": {
                "turnObligations": ["ACKNOWLEDGE_COMPLIMENT"],
            },
        },
    )


def test_unauthorized_commercial_candidate_gets_one_text_only_correction():
    repository = Repository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    scheduled = service.generated(
        operation(), candidate("COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY"),
    )
    assert scheduled.state.value == "RETRYABLE"
    correction = repository.corrective
    assert correction["previousCandidateText"] == "Unlock this paid set"
    assert correction["commercialAuthorityCorrection"] == {
        "required": True,
        "authority": "PRE_GENERATION_COMMERCIAL_DECISION",
        "conversationOnly": True,
        "textOnly": True,
        "preserveOrdinaryTurnObligations": True,
        "excludeRejectedCandidate": True,
        "maximumGenerationAttempts": 2,
    }
    assert "Unlock this paid set" in correction["excludedExactResponses"]


def test_no_surviving_ordinary_obligation_fails_closed_without_correction():
    repository = Repository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    optional = operation(obligations=())
    optional.inbound_message_text = "lol"
    rejected = candidate("COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY")
    rejected.diagnostic_metadata["conversationStyle"]["turnObligations"] = []
    terminal = service.generated(optional, rejected)
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None


def test_second_commercial_authority_failure_cannot_recurse():
    repository = Repository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    terminal = service.generated(
        operation(attempt=2),
        candidate("COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY"),
    )
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None
    assert repository.suppressed["reason"].startswith(
        "quality_corrective_retry_exhausted:"
    )


def test_repetition_and_commercial_failure_share_one_bounded_correction():
    repository = Repository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    scheduled = service.generated(
        operation(),
        candidate(
            "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY",
            "FINAL_REPETITION_FAILURE",
        ),
    )
    assert scheduled.state.value == "RETRYABLE"
    assert set(repository.corrective["blockingReasons"]) == {
        "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY",
        "FINAL_REPETITION_FAILURE",
    }


def test_unrelated_safety_failure_is_not_made_correctable():
    repository = Repository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    terminal = service.generated(
        operation(),
        candidate(
            "COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY",
            "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",
        ),
    )
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None


def test_retry_payload_propagates_durable_authority_and_correction_evidence():
    item = operation()
    item.delivery_payload["qualityCorrectiveRetry"] = {
        "required": True,
        "blockingReasons": ["COMMERCIAL_MEDIA_WITHOUT_CURRENT_AUTHORITY"],
    }
    payload = OrdinaryChatReplyService(
        repository=Repository(), worker_id="test",
    ).retry_payload(item)
    assert payload.quality_correction_context[
        "preGenerationCommercialDecision"
    ] == cold_authority()
    assert payload.quality_correction_context["required"] is True
