from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.ava_availability_session import AvaAvailabilitySession, AvaAvailabilityState
from app.models.telegram_private_inbound_message import TelegramPrivateInboundMessage
from app.services.ava_human_availability_service import AvaHumanAvailabilityService
from app.services.telegram_private_inbound_backlog_service import TelegramPrivateInboundBacklogService


class SessionRepo:
    def __init__(self): self.value = None; self.transitions = 0
    def current_or_transition(self, **kwargs):
        now = kwargs["now"]
        if self.value and self.value.transition_at > now: return self.value
        prior = self.value.state if self.value else None
        state = kwargs["initial_state"](now) if prior is None else kwargs["next_state"](prior, now)
        self.value = AvaAvailabilitySession(uuid4(), kwargs["account_scope"], state, now,
            kwargs["duration"](state, now), kwargs["daypart"](now), "TEST", "TEST")
        self.transitions += 1
        return self.value


def test_active_session_is_sticky_across_messages_and_chats_and_restart():
    clock = [datetime(2026, 9, 13, 16, tzinfo=timezone.utc)]; repo = SessionRepo()
    service = AvaHumanAvailabilityService(repository=repo, now=lambda: clock[0],
        state_selector=lambda _: AvaAvailabilityState.ACTIVE, uniform=lambda low, high: low,
        random_value=lambda: .1)
    first = service.calculate(inbound_text="hello")
    second = service.calculate(inbound_text="where are you?")
    restarted = AvaHumanAvailabilityService(repository=repo, now=lambda: clock[0], uniform=lambda low, high: low)
    third = restarted.calculate(inbound_text="how much?")
    assert first.session_id == second.session_id == third.session_id
    assert first.state is second.state is third.state is AvaAvailabilityState.ACTIVE
    assert repo.transitions == 1


def test_busy_session_cannot_be_summoned_and_transitions_once_at_expiry():
    clock = [datetime(2026, 9, 13, 16, tzinfo=timezone.utc)]; repo = SessionRepo()
    service = AvaHumanAvailabilityService(repository=repo, now=lambda: clock[0],
        state_selector=lambda _: AvaAvailabilityState.BUSY, uniform=lambda low, high: 1320,
        random_value=lambda: .1)
    original = service.calculate(inbound_text="hello?")
    for text in ("where are you?", "buy this", "😘", "answer me"):
        assert service.calculate(inbound_text=text).session_id == original.session_id
    clock[0] += timedelta(minutes=22)
    transitioned = service.calculate(inbound_text="where are you?")
    assert transitioned.session_id != original.session_id
    assert repo.transitions == 2


def test_sleep_session_persists_until_eight_am_new_york():
    now = datetime(2026, 9, 13, 8, tzinfo=timezone.utc)  # 04:00 ET
    service = AvaHumanAvailabilityService(now=lambda: now, uniform=lambda low, high: low)
    decision = service.calculate()
    assert decision.state is AvaAvailabilityState.SLEEPING
    assert decision.transition_at.hour == 12


def inbound(message_id, text, minute=0):
    return TelegramPrivateInboundMessage(uuid4(), "AVA", 12, 12, message_id,
        datetime(2026, 9, 13, 12, minute, tzinfo=timezone.utc), text, False)


class BacklogRepo:
    def __init__(self, messages): self.messages = messages; self.calls = []
    def pending_for_chat(self, **kwargs): return list(self.messages)
    def reconcile(self, **kwargs):
        self.calls.append(kwargs); reconciled = list(self.messages); self.messages = []
        return reconciled, uuid4() if kwargs["outcome"] == "RESPOND" else None


def test_direct_question_survives_trailing_emoji_and_creates_one_authority():
    repo = BacklogRepo([inbound(1, "Can you remember me?"), inbound(2, "😘", 1), inbound(3, "❤️", 2)])
    result = TelegramPrivateInboundBacklogService(repository=repo).reconcile_chat(account_scope="AVA", chat_id=12)
    assert result["outcome"] == "RESPOND"
    assert result["authoritative"].telegram_message_id == 1
    assert len(repo.calls) == 1 and result["response_operation_id"] is not None


def test_commercial_referent_survives_and_low_information_can_terminate_without_reply():
    commercial = BacklogRepo([inbound(1, "What private content do you have?"), inbound(2, "😘", 1)])
    result = TelegramPrivateInboundBacklogService(repository=commercial).reconcile_chat(account_scope="AVA", chat_id=12)
    assert result["authoritative"].telegram_message_id == 1
    low = BacklogRepo([inbound(i, "❤️", i) for i in range(1, 8)])
    result = TelegramPrivateInboundBacklogService(repository=low).reconcile_chat(account_scope="AVA", chat_id=12)
    assert result["outcome"] == "NO_RESPONSE_REQUIRED"
    assert result["response_operation_id"] is None


def test_twenty_message_backlog_becomes_one_current_authority():
    repo = BacklogRepo([inbound(i, f"message {i}", i) for i in range(1, 21)])
    result = TelegramPrivateInboundBacklogService(repository=repo).reconcile_chat(account_scope="AVA", chat_id=12)
    assert result["messages"] == 20
    assert len(repo.calls) == 1
    assert result["response_operation_id"] is None  # bounded terminal non-response is valid


class CaptureRepo:
    def __init__(self): self.kwargs = None
    def capture(self, **kwargs): self.kwargs = kwargs; return SimpleNamespace(), True


def test_off_media_capture_records_only_bounded_metadata():
    repo = CaptureRepo(); service = TelegramPrivateInboundBacklogService(repository=repo)
    payload = SimpleNamespace(telegram_user_id=9, telegram_chat_id=9, message_id=7,
        received_at=datetime.now(timezone.utc), message_text="", attachments=(SimpleNamespace(media_kind="photo"),))
    service.capture(payload, account_scope="AVA", automation_state="OFF")
    assert repo.kwargs["media_types"] == ("photo",)
    assert "artifact" not in repo.kwargs and "bytes" not in repo.kwargs
