from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.ava_availability_session import AvaAvailabilityState
from app.models.relationship_market_tier import (
    RelationshipMarketTier, RelationshipMarketTierRecord,
)
from app.services.ava_human_availability_service import AvaHumanAvailabilityService
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.relationship_market_tier_service import RelationshipMarketTierService
from app.services.relationship_value_override_service import RelationshipValueOverrideService


NOW = datetime(2026, 9, 13, 20, tzinfo=timezone.utc)
SCOPE = dict(creator_profile_id=1, fanvue_account_id=2,
             telegram_user_id=3, telegram_chat_id=3)


class SessionRepository:
    def __init__(self, state, remaining=1000):
        self.session = SimpleNamespace(session_id="session", state=state,
            started_at=NOW-timedelta(minutes=1),
            transition_at=NOW+timedelta(seconds=remaining))

    def current_or_transition(self, **_):
        return self.session


def availability(state, *, sample=200, remaining=1000, quiet=8):
    service = AvaHumanAvailabilityService(now=lambda: NOW,
        uniform=lambda *_: sample,
        repository=SessionRepository(state, remaining))
    return service


@pytest.mark.parametrize(("state", "expected"), [
    (AvaAvailabilityState.AVAILABLE, 150),
    (AvaAvailabilityState.ACTIVE, 150),
    (AvaAvailabilityState.INTERMITTENT, 150),
    (AvaAvailabilityState.BUSY, 650),
    (AvaAvailabilityState.AWAY, 650),
    (AvaAvailabilityState.SLEEPING, 1000),
])
def test_high_timing_profile(state, expected):
    assert availability(state).calculate(market_tier="HIGH").delay_seconds == expected


@pytest.mark.parametrize(("state", "expected"), [
    (AvaAvailabilityState.AVAILABLE, 70),
    (AvaAvailabilityState.ACTIVE, 70),
    (AvaAvailabilityState.INTERMITTENT, 70),
    (AvaAvailabilityState.BUSY, 250),
    (AvaAvailabilityState.AWAY, 250),
    (AvaAvailabilityState.SLEEPING, 1000),
])
def test_high_hvp_timing_profile(state, expected):
    assert availability(state).calculate(
        market_tier="HIGH", high_value_prospect=True).delay_seconds == expected


def test_high_preserves_quiet_floor(monkeypatch):
    monkeypatch.setenv("AVA_AVAILABILITY_QUIET_PERIOD_SECONDS", "12")
    assert availability(AvaAvailabilityState.ACTIVE, sample=4).calculate(
        market_tier="HIGH", high_value_prospect=True).delay_seconds == 12


@pytest.mark.parametrize(("tier", "hvp", "expected"), [
    ("MEDIUM", False, 200), ("UNCLASSIFIED", False, 200),
    ("LOW", False, 200), ("MEDIUM", True, 100),
    ("UNCLASSIFIED", True, 100), ("LOW", True, 100),
])
def test_non_high_profiles_preserve_baseline_and_existing_hvp(tier, hvp, expected):
    assert availability(AvaAvailabilityState.ACTIVE).calculate(
        market_tier=tier, high_value_prospect=hvp).delay_seconds == expected


class DueRepository:
    def __init__(self, operations, buckets):
        self.operations = operations
        self.buckets = buckets

    def release_due_availability(self, **_): return list(self.operations)
    def market_tier_priority_buckets(self, operations, **_): return self.buckets
    def coalesced_burst_messages(self, *_args, **_kwargs): return []
    def buyer_attention_context(self, **_): return {}
    def recent_attention_messages(self, *_args, **_kwargs): return ["hello"]
    def record_attention(self, *_args, **_kwargs): pass


class RespondAttention:
    def evaluate(self, *_args, **_kwargs):
        return SimpleNamespace(outcome="RESPOND", diagnostics=lambda: {})


class NoopPostNudgeObservation:
    def observe(self, *_args, **_kwargs):
        return ()


@dataclass(frozen=True)
class QueueItem:
    inbound_sender_telegram_user_id: int
    telegram_chat_id: int
    inbound_telegram_message_id: int
    inbound_received_at: datetime
    operation_id: str
    inbound_message_text: str = "hello"
    chat_history: list | None = None


def operation(user, chat, message, received):
    return QueueItem(user, chat, message, received, f"op-{user}")


def test_due_queue_prefers_all_five_buckets_without_starvation(monkeypatch):
    rows = [operation(index, index, index, NOW+timedelta(seconds=index))
            for index in range(1, 6)]
    keys = {(row.inbound_sender_telegram_user_id, row.telegram_chat_id): rank
            for row, rank in zip(rows, (4, 3, 2, 1, 0))}
    repository = DueRepository(rows, keys)
    service = OrdinaryChatReplyService(repository=repository,
        attention_service=RespondAttention(), creator_profile_id=1,
        fanvue_account_id=2,
        post_nudge_nonconversion=NoopPostNudgeObservation())
    monkeypatch.setattr(service, "retry_payload", lambda item: item)
    result = service.due_availability_payloads(now=NOW)
    assert [item.inbound_sender_telegram_user_id for item in result] == [5, 4, 3, 2, 1]
    assert len(result) == 5


class TierRepository:
    def __init__(self): self.current = None; self.advances = []
    def active(self, **_): return self.current
    def set(self, *, market_tier, changed_by, reason=None, **scope):
        if self.current and self.current.market_tier.value == market_tier:
            return self.current, False
        self.current = RelationshipMarketTierRecord(
            market_tier_id=uuid4(), market_tier=RelationshipMarketTier(market_tier),
            version=1, changed_by=changed_by, changed_at=NOW, reason=reason,
            **scope)
        return self.current, True
    def remove(self, **_): prior=self.current; self.current=None; return prior
    def advance_eligible(self, **kwargs): self.advances.append(kwargs); return {"operation_id":"op"}


class Allowed:
    def read(self, **_): return {"effective":{"chatAllowed": True}}


class RecordingAvailability:
    def __init__(self): self.calls=[]
    def calculate(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(available_at=NOW+timedelta(seconds=70))


def test_high_assignment_advances_and_demotion_removal_never_delay():
    repository=TierRepository(); clock=RecordingAvailability()
    service=RelationshipMarketTierService(repository, availability=clock,
                                           effective_permissions=Allowed())
    result=service.set(**SCOPE, market_tier="HIGH", changed_by="operator")
    assert result["scheduleAdvanced"] and clock.calls == [
        {"market_tier":"HIGH", "high_value_prospect":False}]
    service.set(**SCOPE, market_tier="MEDIUM", changed_by="operator")
    service.remove(**SCOPE, removed_by="operator")
    assert len(repository.advances) == 1


def test_high_hvp_assignment_uses_combined_advancement_profile():
    repository=TierRepository(); clock=RecordingAvailability()
    service=RelationshipMarketTierService(repository, availability=clock,
                                           effective_permissions=Allowed())
    service.set(**SCOPE, market_tier="HIGH", changed_by="operator",
                high_value_prospect=True)
    assert clock.calls == [{"market_tier":"HIGH", "high_value_prospect":True}]
    assert repository.advances[0]["high_value_prospect"] is True


class HvpRepository:
    def set_high_value(self, **scope): return scope, True
    def advance_eligible(self, **values): return values
    def active(self, **_): return None


class HighTierReader:
    def active(self, **_): return SimpleNamespace(market_tier=RelationshipMarketTier.HIGH)


def test_hvp_activation_on_high_uses_combined_profile():
    clock=RecordingAvailability()
    service=RelationshipValueOverrideService(repository=HvpRepository(),
        availability=clock, effective_permissions=Allowed(),
        market_tiers=HighTierReader())
    result=service.set(**SCOPE, classification="HIGH_VALUE_PROSPECT",
                       changed_by="operator")
    assert result["scheduleAdvanced"]
    assert clock.calls == [{"high_value_prospect":True, "market_tier":"HIGH"}]
