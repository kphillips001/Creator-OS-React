from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import random

import pytest

from app.models.telegram_inbound import TelegramInboundResult
from app.services.ava_human_availability_service import AvaHumanAvailabilityService, AvaAvailabilityState
from app.services.ava_attention_investment_service import AvaAttentionInvestmentService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.ordinary_reply_delivery_quality_gate import OrdinaryReplyDeliveryQualityGate
from app.services.conversation_quality_watch_service import ConversationQualityWatchService


def result(*, text="ok", error=None, blocked=False, style=None, reasons=()):
    return TelegramInboundResult(
        correlation_id="c", telegram_chat_id=1, telegram_user_id=1,
        message_id=1, engine_user_id="e", response_text=text,
        offer_authorized=False, offer_link=None, blocked=blocked,
        error_code=error, delivery_payload={},
        diagnostic_metadata={"conversationStyle": style or {},
                             "conversationQualityReasons": list(reasons)},
    )


@pytest.mark.parametrize("message", ["Can you remember me?","buy this set","😘","normal update"])
def test_customer_content_cannot_change_ava_owned_availability(message):
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    service = AvaHumanAvailabilityService(uniform=lambda low, high: high, now=lambda: now,
        state_selector=lambda _: AvaAvailabilityState.BUSY)
    decision = service.calculate(inbound_text=message)
    assert decision.state is AvaAvailabilityState.BUSY
    assert decision.delay_seconds == 2100
    assert decision.available_at > now
    assert decision.diagnostics()["messagePriorityAffectsAvailability"] is False


@pytest.mark.parametrize("reason", sorted(OrdinaryReplyDeliveryQualityGate.BLOCKING_REASONS))
def test_hard_final_gate_blocks_required_quality_failures(reason):
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(result(reasons=[reason]))
    assert decision.allowed is False
    assert decision.disposition == "BLOCKED_BEFORE_DELIVERY"


def test_final_gate_allows_clean_response():
    assert OrdinaryReplyDeliveryQualityGate().evaluate(result()).allowed is True


class RecordingRepository:
    def __init__(self):
        self.stored = None
        self.suppressed = None
        self.corrective = None
        self.failed = None

    def store_generated(self, operation_id, **kwargs):
        self.stored = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="GENERATED"), **kwargs)

    def store_suppressed_generation(self, operation_id, **kwargs):
        self.suppressed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="SUPPRESSED"), **kwargs)

    def schedule_quality_correction(self, operation_id, **kwargs):
        self.corrective = kwargs
        return SimpleNamespace(
            operation_id=operation_id,
            state=SimpleNamespace(value="RETRYABLE"),
            next_retry_at=datetime.now(timezone.utc),
            generation_attempt_count=1,
            send_attempt_count=0,
            delivery_payload={"qualityCorrectiveRetry": {
                "required": True, "attempt": 2,
                "blockingReasons": list(kwargs["reasons"]),
                "excludedExactResponses": [
                    kwargs["response_payload"]["response_text"],
                    *kwargs.get("recent_ava_responses", ()),
                ],
            }},
        )

    def fail_generation(self, operation_id, **kwargs):
        self.failed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="RETRYABLE"), **kwargs)

    def fail_empty_generation(self, operation_id, **kwargs):
        self.failed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="RETRYABLE"), **kwargs)

    def fail_generated_before_send(self, operation_id, **kwargs):
        self.failed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="TERMINAL_FAILED"), **kwargs)

    def terminalize_deterministic_authorization_failure(self, operation_id, **kwargs):
        self.failed = kwargs
        return SimpleNamespace(state=SimpleNamespace(value="SUPPRESSED"), **kwargs)


def operation(*, required=False):
    return SimpleNamespace(operation_id=uuid4(), inbound_message_text="",
                           burst_member_obligations=["ANSWER_DIRECT_QUESTION"] if required else [],
                           delivery_payload={}, generation_attempt_count=1,
                           send_attempt_count=0,
                           outbound_telegram_message_id=None)


@pytest.mark.parametrize("reasons", [
    ("CUSTOMER_QUESTION_UNANSWERED",),
    ("TURN_OBLIGATIONS_UNSATISFIED",),
    ("CUSTOMER_QUESTION_UNANSWERED", "TURN_OBLIGATIONS_UNSATISFIED"),
    ("FINAL_REPETITION_FAILURE",),
])
def test_required_quality_failure_schedules_one_corrective_generation(reasons):
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    candidate = result(text="bad candidate", reasons=reasons)
    scheduled = service.generated(operation(required=True), candidate)
    assert scheduled.state.value == "RETRYABLE"
    assert repository.corrective["reasons"] == tuple(sorted(reasons))
    assert repository.suppressed is None


def test_second_required_quality_failure_is_terminal_without_third_attempt():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = operation(required=True)
    item.generation_attempt_count = 2
    terminal = service.generated(
        item, result(text="still bad", reasons=["CUSTOMER_QUESTION_UNANSWERED"]),
    )
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None
    assert repository.suppressed["reason"].startswith(
        "quality_corrective_retry_exhausted:"
    )


@pytest.mark.parametrize("reason", [
    "MANUFACTURED_ENGAGEMENT_QUESTION",
    "UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM",
])
def test_unrelated_quality_suppressions_do_not_receive_correction(reason):
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    terminal = service.generated(operation(), result(text="bad", reasons=[reason]))
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None


def test_retry_payload_carries_durable_corrective_context():
    service = OrdinaryChatReplyService(repository=RecordingRepository(), worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(),
        inbound_sender_telegram_user_id=1, telegram_chat_id=2,
        inbound_message_text="What do you mean?", inbound_telegram_message_id=3,
        inbound_received_at=datetime.now(timezone.utc),
        delivery_payload={"qualityCorrectiveRetry": {
            "required": True, "attempt": 2,
            "blockingReasons": ["CUSTOMER_QUESTION_UNANSWERED"],
        }},
    )
    payload = service.retry_payload(item)
    assert payload.quality_correction_context["required"] is True
    assert payload.quality_correction_context["attempt"] == 2


def test_repetition_correction_carries_rejected_and_recent_exact_exclusions():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    candidate = result(
        text="then don't make it too easy for me",
        reasons=["FINAL_REPETITION_FAILURE"],
    )
    candidate.diagnostic_metadata["recentAvaResponses"] = [
        "then don't make it too easy for me", "A different recent answer",
    ]
    scheduled = service.generated(operation(required=True), candidate)
    assert scheduled.state.value == "RETRYABLE"
    assert repository.corrective["response_payload"]["response_text"] == (
        "then don't make it too easy for me"
    )
    assert repository.corrective["recent_ava_responses"] == (
        "then don't make it too easy for me", "A different recent answer",
    )


def test_second_repetition_failure_is_terminal_without_third_generation():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = operation(required=True)
    item.generation_attempt_count = 2
    terminal = service.generated(item, result(
        text="same again", reasons=["FINAL_REPETITION_FAILURE"],
    ))
    assert terminal.state.value == "SUPPRESSED"
    assert repository.corrective is None
    assert repository.suppressed["reason"] == (
        "quality_corrective_retry_exhausted:FINAL_REPETITION_FAILURE"
    )


def test_repetition_corrective_candidate_failing_other_gate_is_not_deliverable():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = operation()
    item.generation_attempt_count = 2
    terminal = service.generated(item, result(
        text="fresh but unsafe",
        reasons=["UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM"],
    ))
    assert terminal.state.value == "SUPPRESSED"
    assert repository.stored is None
    assert repository.corrective is None


def test_generated_repairs_unsupported_relationship_claim_before_storage():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(), inbound_message_text="I love you",
        delivery_payload={},
    )
    service.generated(item, result(text="Love you too."))
    assert repository.stored["response_text"] == "That's really sweet of you ❤️"
    natural = repository.stored["response_payload"]["diagnostic_metadata"]["naturalConversation"]
    assert natural["repairReasons"] == ["UNSUPPORTED_RECIPROCAL_RELATIONSHIP_CLAIM"]


def test_empty_generation_is_internal_failure_and_not_sendable():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    service.generated(operation(), result(text=""))
    assert repository.stored is None
    assert repository.failed["reason"].startswith("EMPTY_GENERATION:")


def test_decision_engine_exception_is_internal_failure_and_not_sendable():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    service.generated(operation(), result(text="", error="decision_engine_exception", blocked=True))
    assert repository.stored is None
    assert repository.failed["reason"].startswith("DECISION_ENGINE_EXCEPTION:")


def test_decision_engine_exception_persists_only_sanitized_error_type():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    value = result(text="", error="decision_engine_exception", blocked=True)
    value.diagnostic_metadata["internal_generation_failure"] = {
        "errorType": "TypeError<script>", "privateMessage": "secret",
    }
    service.generated(operation(), value)
    assert repository.failed["reason"] == (
        "DECISION_ENGINE_EXCEPTION:TypeErrorscript: Automatic reply could not be completed."
    )
    assert "secret" not in repository.failed["reason"]


def test_anthony_critical_burst_bad_candidates_are_blocked_not_debted():
    gate = OrdinaryReplyDeliveryQualityGate()
    cases = [
        result(text="Is that all?", reasons=["MANUFACTURED_ENGAGEMENT_QUESTION"]),
        result(text="same answer", reasons=["FINAL_REPETITION_FAILURE"]),
        result(text="filler", style={"customerQuestionAnswered": False}),
    ]
    assert [gate.evaluate(item).disposition for item in cases] == [
        "BLOCKED_BEFORE_DELIVERY"] * 3


def test_attention_tapers_recovers_and_protects_buyers():
    attention=AvaAttentionInvestmentService()
    low=["❤️","you've gone quiet","😘","hello?","🔥","love you babe","❤️❤️"]
    assert attention.evaluate(low).outcome=="NO_RESPONSE_REQUIRED"
    assert attention.evaluate(low+["How was your actual day?"]).investment.value=="NORMAL"
    buyer=attention.evaluate(low,verified_buyer=True,repeat_buyer=True)
    assert buyer.investment.value=="NORMAL" and buyer.outcome=="RESPOND"

def test_commercial_and_direct_obligations_survive_attention_taper():
    attention=AvaAttentionInvestmentService()
    low=["❤️","hello","😘","babe","🔥","love you"]
    assert attention.evaluate(low+["Do you have a special photo?"]).outcome=="RESPOND"


def test_four_chat_attention_priority_is_bounded_after_availability():
    attention = AvaAttentionInvestmentService()
    repetitive = attention.evaluate(["❤️", "hello", "😘", "babe"])
    normal = attention.evaluate(["I finally finished my garden project"])
    buyer = attention.evaluate(["hey"], verified_buyer=True, repeat_buyer=True)
    commercial = attention.evaluate(["What does that photo set cost?"])

    assert repetitive.investment.value == "LOWER_PRIORITY"
    assert repetitive.priority < normal.priority < commercial.priority < buyer.priority
    assert all(item.outcome == "RESPOND" for item in (
        repetitive, normal, commercial, buyer,
    ))


def test_exception_result_is_structural_blocked_and_empty():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    payload = SimpleNamespace(telegram_chat_id=1, telegram_user_id=2, message_id=3)
    op = SimpleNamespace(operation_id=uuid4(), correlation_id="corr")
    fallback = service.exception_fallback(op, payload, RuntimeError("private detail"))
    assert fallback.blocked is True
    assert fallback.response_text == ""
    assert fallback.error_code == "internal_generation_failure"
    assert "private detail" not in str(fallback.diagnostic_metadata)


@pytest.mark.parametrize("diagnostics", [
    {"status": "engine_exception", "delivery_quality_gate": {"disposition": "ALLOWED"}},
    {"generation_fallback": {"applied": True}, "delivery_quality_gate": {"disposition": "ALLOWED"}},
    {"internal_generation_failure": {"customerVisible": False}, "delivery_quality_gate": {"disposition": "ALLOWED"}},
])
def test_final_delivery_authority_rejects_internal_failure_payloads(diagnostics):
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(), response_text="system apology",
        response_payload={"error_code": None, "diagnostic_metadata": diagnostics},
        delivery_payload={"message_text": "system apology"},
    )
    assert service.authorize_customer_visible_delivery(item) is False
    assert repository.failed["reason"] == "PERSISTED_INTERNAL_RESPONSE_NOT_DELIVERABLE"


def test_final_delivery_authority_allows_quality_approved_customer_content():
    service = OrdinaryChatReplyService(repository=RecordingRepository(), worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(), response_text="A real valid answer",
        response_payload={"error_code": None, "diagnostic_metadata": {
            "delivery_quality_gate": {"disposition": "ALLOWED"},
        }},
        delivery_payload={"message_text": "A real valid answer"},
    )
    assert service.authorize_customer_visible_delivery(item) is True


def test_payload_text_mismatch_is_deterministically_terminalized():
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(), response_text="Fresh authoritative reply",
        response_payload={"error_code": None, "diagnostic_metadata": {
            "delivery_quality_gate": {"disposition": "ALLOWED"},
        }},
        delivery_payload={"message_text": "Stale persisted reply"},
    )
    assert service.authorize_customer_visible_delivery(item) is False
    assert repository.failed["reason"] == "IMMUTABLE_DELIVERY_PAYLOAD_TEXT_MISMATCH"


@pytest.mark.parametrize("state", ["GENERATED", "RETRYABLE"])
def test_payload_mismatch_terminalization_is_state_independent_after_generation(state):
    repository = RecordingRepository()
    service = OrdinaryChatReplyService(repository=repository, worker_id="test")
    item = SimpleNamespace(
        operation_id=uuid4(), state=SimpleNamespace(value=state),
        response_text="Authoritative", inbound_message_text="Yes",
        response_payload={"error_code": None, "diagnostic_metadata": {
            "delivery_quality_gate": {"disposition": "ALLOWED"},
        }},
        delivery_payload={"message_text": "Stale"},
    )
    assert service.authorize_customer_visible_delivery(item) is False
    assert repository.failed == {
        "reason": "IMMUTABLE_DELIVERY_PAYLOAD_TEXT_MISMATCH",
    }


def test_monitor_labels_hard_failure_as_blocked_before_delivery():
    alerts = SimpleNamespace(authorize_and_attempt=lambda **kwargs: {
        "state": "SENT_CONFIRMED", "notification_operation_id": "notice",
        "text": kwargs["text"],
    })
    watch = ConversationQualityWatchService(
        repository=SimpleNamespace(), alert_service=alerts,
    )
    captured = {}
    def record(**kwargs):
        captured.update(kwargs)
        return {"state": "SENT_CONFIRMED", "notification_operation_id": "notice"}
    alerts.authorize_and_attempt = record
    watch.observe(
        response_text="same", customer_message="where?",
        diagnostics={"conversationQualityReasons": ["FINAL_REPETITION_FAILURE"],
                     "conversationStyle": {"finalResponseRepetitionSatisfied": False}},
        disposition="BLOCKED_BEFORE_DELIVERY",
    )
    assert "Disposition: BLOCKED_BEFORE_DELIVERY" in captured["text"]
    assert "blocked before customer delivery" in captured["text"]


def test_timing_jitter_is_seeded_bounded_and_never_sleeps():
    rng = random.Random(918)
    now = datetime(2026, 9, 12, tzinfo=timezone.utc)
    service = AvaHumanAvailabilityService(uniform=rng.uniform, now=lambda: now,
        state_selector=lambda _: AvaAvailabilityState.INTERMITTENT)
    values = [service.calculate(inbound_text="Can you help?").delay_seconds for _ in range(8)]
    assert all(180 <= value <= 720 for value in values)
    assert len(set(values)) > 1
    commercial = service.calculate(inbound_text="buy this set")
    assert 180 <= commercial.delay_seconds <= 720
    assert service.calculate(inbound_text="yeah").quiet_period_seconds >= 8
