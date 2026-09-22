from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.telegram_inbound import TelegramInboundResult
from app.services.ava_offline_access_policy import AvaOfflineAccessPolicy
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.ordinary_reply_delivery_quality_gate import OrdinaryReplyDeliveryQualityGate


REASON = "MISLEADING_OFFLINE_ENCOUNTER_EXPECTATION"


def result(customer, candidate, *, extra_reasons=(), authority=None):
    authority = authority or AvaOfflineAccessPolicy().classify(customer)
    return TelegramInboundResult(
        correlation_id="fixture", telegram_chat_id=2, telegram_user_id=1,
        message_id=3, engine_user_id="telegram:1", response_text=candidate,
        offer_authorized=False, offer_link=None, blocked=False, error_code=None,
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": candidate},
        diagnostic_metadata={
            "offlineAccessAuthority": authority.diagnostics(),
            "conversationQualityReasons": list(extra_reasons),
            "conversationStyle": {
                "turnObligations": ["ANSWER_DIRECT_QUESTION"] if "?" in customer else [],
                "customerQuestionAnswered": True,
                "turnObligationsSatisfied": True,
            },
        },
    )


def gate(customer, candidate, **kwargs):
    item = result(customer, candidate, **kwargs)
    decision = OrdinaryReplyDeliveryQualityGate().evaluate(
        item, customer_text=customer)
    return decision, item


@pytest.mark.parametrize(("customer", "candidate"), [
    ("You're missing some amazing sunsets", "Maybe I'm saving the best moments for when we finally meet."),
    ("It's all about pleasuring you when we meet", "Maybe one day you'll get to show me just how much."),
    ("I don't know what's keeping you so far away", "Maybe I'm waiting for you to close that gap a little."),
    ("I could drive there this weekend", "Maybe I'll make it worth the drive."),
    ("Can I take you out?", "Keep me guessing for now."),
    ("Will you visit?", "One day we'll have to make that happen."),
    ("Come visit me", "I'd love to come spend the weekend there with you."),
])
def test_final_gate_blocks_explicit_and_implied_offline_access(customer, candidate):
    decision, item = gate(customer, candidate)
    assert decision.allowed is False
    assert REASON in decision.reasons
    validation = item.diagnostic_metadata["offlineAccessValidation"]
    assert validation["offlineExpectationViolation"] is True
    assert validation["finalOfflineAccessDisposition"] == "BLOCKED_BEFORE_DELIVERY"


def test_preferred_boundary_is_allowed_and_answers_direct_question():
    decision, _ = gate(
        "When can we meet?",
        "Let's keep things online for now 😊 I like what we've got going right here.")
    assert decision.allowed


def test_boundary_followed_by_future_eligibility_is_blocked():
    decision, _ = gate(
        "When can we meet?",
        "Let's keep things online for now 😊 maybe someday though.")
    assert not decision.allowed
    assert decision.reasons == (REASON,)


@pytest.mark.parametrize(("customer", "candidate"), [
    ("I wish you were curled up next to me", "You make that sound pretty tempting 😏"),
    ("I dreamed we had a date", "Okay, that scenario would definitely be trouble."),
    ("Nice to meet you", "Nice to meet you too."),
    ("See you later", "Talk later 😊"),
    ("Will I see the photos someday?", "Maybe someday you'll see the photos."),
    ("You should meet my dog", "Your dog sounds adorable."),
])
def test_fantasy_and_false_positives_remain_allowed(customer, candidate):
    assert gate(customer, candidate)[0].allowed


class Repository:
    def __init__(self):
        self.corrective = None
        self.suppressed = None
        self.failed = None

    def recent_ava_responses(self, operation): return []
    def record_generation_attempt(self, *args, **kwargs): pass
    def schedule_quality_correction(self, operation_id, **kwargs):
        self.corrective = kwargs
        return SimpleNamespace(
            operation_id=operation_id, state=SimpleNamespace(value="RETRYABLE"),
            generation_attempt_count=1, send_attempt_count=0,
            outbound_telegram_message_id=None,
            delivery_payload={"qualityCorrectiveRetry": {
                "required": True, "attempt": 2,
                "blockingReasons": list(kwargs["reasons"]),
            }},
        )
    def store_suppressed_generation(self, operation_id, **kwargs):
        self.suppressed = kwargs
        return SimpleNamespace(
            operation_id=operation_id, state=SimpleNamespace(value="SUPPRESSED"),
            generation_attempt_count=2, send_attempt_count=0,
            outbound_telegram_message_id=None, **kwargs)
    def store_generated(self, operation_id, **kwargs):
        return SimpleNamespace(operation_id=operation_id,
            state=SimpleNamespace(value="GENERATED"), **kwargs)
    def fail_generated_before_send(self, operation_id, **kwargs): self.failed = kwargs


def operation(attempt=1):
    return SimpleNamespace(
        operation_id=uuid4(), inbound_message_text="When can we meet?",
        inbound_telegram_message_id=3, inbound_received_at=datetime.now(timezone.utc),
        inbound_sender_telegram_user_id=1, telegram_chat_id=2,
        delivery_payload={}, generation_attempt_count=attempt,
        send_attempt_count=0, outbound_telegram_message_id=None,
    )


def test_first_violation_authorizes_exactly_one_correction_and_no_send():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    stored = service.generated(operation(), result(
        "When can we meet?", "I can't wait until we finally meet."))
    assert stored.state.value == "RETRYABLE"
    assert repo.corrective["reasons"] == (REASON,)
    assert stored.send_attempt_count == 0


def test_second_violation_is_terminal_without_third_generation_or_fallback():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    stored = service.generated(operation(2), result(
        "When can we meet?", "Maybe someday we'll make it happen."))
    assert stored.state.value == "SUPPRESSED"
    assert repo.corrective is None
    assert stored.send_attempt_count == 0
    assert "hit a snag" not in stored.response_text.lower()


def test_mixed_correctable_reasons_receive_one_correction():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    stored = service.generated(operation(), result(
        "When can we meet?", "When we finally meet...",
        extra_reasons=("CUSTOMER_QUESTION_UNANSWERED",)))
    assert stored.state.value == "RETRYABLE"
    assert set(repo.corrective["reasons"]) == {REASON, "CUSTOMER_QUESTION_UNANSWERED"}


def test_noncorrectable_mixed_reason_fails_closed_without_correction():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    stored = service.generated(operation(), result(
        "When can we meet?", "When we finally meet...",
        extra_reasons=("INTERNAL_FAILURE_PAYLOAD",)))
    assert stored.state.value == "SUPPRESSED"
    assert repo.corrective is None


def test_compliant_second_attempt_becomes_generated_with_zero_send_attempts():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    stored = service.generated(operation(2), result(
        "When can we meet?",
        "Let's keep things online for now 😊 I like what we've got going right here."))
    assert stored.state.value == "GENERATED"
    assert repo.corrective is None


def test_pre_send_revalidation_blocks_late_payload_rewrite():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="test")
    safe = result("When can we meet?", "Let's keep things online for now 😊")
    unsafe = "Maybe someday we'll finally meet."
    item = SimpleNamespace(
        operation_id=uuid4(), inbound_message_text="When can we meet?",
        response_text=unsafe,
        response_payload={"error_code": None, "diagnostic_metadata": {
            **safe.diagnostic_metadata,
            "delivery_quality_gate": {"disposition": "ALLOWED"},
        }},
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": unsafe},
    )
    assert service.authorize_customer_visible_delivery(item) is False
    assert repo.failed is not None


def test_valid_persisted_payload_survives_restart_revalidation():
    repo = Repository(); service = OrdinaryChatReplyService(repository=repo, worker_id="restarted")
    candidate = "Let's keep things online for now 😊"
    safe = result("When can we meet?", candidate)
    OrdinaryReplyDeliveryQualityGate().evaluate(safe, customer_text="When can we meet?")
    item = SimpleNamespace(
        operation_id=uuid4(), inbound_message_text="When can we meet?",
        response_text=candidate,
        response_payload={"error_code": None, "diagnostic_metadata": {
            **safe.diagnostic_metadata,
            "delivery_quality_gate": {"disposition": "ALLOWED"},
        }},
        delivery_payload={"type": "MESSAGE_TEXT", "message_text": candidate},
    )
    assert service.authorize_customer_visible_delivery(item) is True
