"""Isolated PostgreSQL certification for Ava sleep/wake reply durability."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.telegram_inbound import TelegramInboundResult
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.telegram_response_pacing_service import (
    TelegramResponsePacingDecision,
)
from app.test_ordinary_chat_reply_idempotency_postgres import (
    Adapter, Delivery, execution, payload, result, runtime, service,
)
from app.test_private_chat_settlement_postgres import connection_factory, fixture


pytestmark = pytest.mark.skipif(
    not os.getenv("TEST_DATABASE_URL"), reason="TEST_DATABASE_URL required"
)


@pytest.fixture(autouse=True)
def clean_sleep_state():
    with connection_factory() as connection:
        connection.execute("DELETE FROM ordinary_chat_reply_operations")


def _defer(item, *, wake, cycle="cycle-1", worker="sleep"):
    replies = service(worker)
    operation, created = replies.begin(item)
    assert created is True
    decision = SimpleNamespace(wake_time=wake, cycle_id=cycle)
    deferred = replies.defer_for_sleep(operation, decision)
    return replies, deferred


def _signoff_result(item, *, cycle="cycle-1"):
    return result(item, diagnostics={
        "sleep_context": {
            "cycleId": cycle,
            "signoffRequired": True,
            "signoffPending": True,
        }
    })


def test_sleep_deferral_persists_wake_time_and_survives_service_restart():
    item = payload()
    wake = datetime.now(timezone.utc) + timedelta(hours=8)
    replies, deferred = _defer(item, wake=wake)
    assert deferred.state.value == "RETRYABLE"
    assert deferred.next_retry_at == wake
    assert deferred.last_error == "sleep_deferred:cycle-1"
    assert deferred.response_payload is None and deferred.send_attempt_count == 0
    restarted = service("restart").repository.get(deferred.operation_id)
    assert restarted.state.value == "RETRYABLE"
    assert restarted.next_retry_at == wake
    assert replies.claim_generation(restarted) is None


def test_due_sleep_operation_reenters_once_without_duplication():
    item = payload()
    _, deferred = _defer(
        item, wake=datetime.now(timezone.utc) - timedelta(seconds=1)
    )
    restarted = service("wake")
    due = restarted.due_sleep_payloads(now=datetime.now(timezone.utc))
    assert [(value.message_id, value.message_text) for value in due] == [
        (item.message_id, item.message_text)
    ]
    operation = restarted.repository.get(deferred.operation_id)
    assert restarted.claim_generation(operation) is not None
    assert restarted.due_sleep_payloads(now=datetime.now(timezone.utc)) == []
    with connection_factory() as connection:
        assert connection.execute(
            "SELECT count(*) n FROM ordinary_chat_reply_operations"
        ).fetchone()["n"] == 1


def test_multiple_overnight_messages_are_recorded_and_consolidated_at_wake():
    wake = datetime.now(timezone.utc) - timedelta(seconds=1)
    first = payload(message_id=610001)
    second = payload(message_id=610002)
    third = payload(message_id=610003)
    for item in (first, second, third):
        _defer(item, wake=wake, worker=f"sleep-{item.message_id}")
    due = service("wake").due_sleep_payloads(now=datetime.now(timezone.utc))
    assert [item.message_id for item in due] == [third.message_id]
    with connection_factory() as connection:
        rows = connection.execute(
            "SELECT inbound_telegram_message_id,state,last_error "
            "FROM ordinary_chat_reply_operations "
            "ORDER BY inbound_telegram_message_id"
        ).fetchall()
    assert len(rows) == 3
    assert [row["state"] for row in rows] == [
        "SUPPRESSED", "SUPPRESSED", "RETRYABLE"
    ]
    assert all(
        row["last_error"] == "sleep_deferred_consolidated_at_wake"
        for row in rows[:2]
    )


def test_pending_signoff_survives_restart_without_false_sleep_confirmation():
    item = payload()
    replies = service("signoff-generate")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation), _signoff_result(item)
    )
    restarted = service("signoff-restart")
    persisted = restarted.repository.get(generated.operation_id)
    assert persisted.state.value == "GENERATED"
    assert persisted.send_attempt_count == 0
    assert restarted.repository.has_confirmed_sleep_signoff(
        account_scope=restarted.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        cycle_id="cycle-1",
    ) is False
    assert restarted.claim_send(persisted) is not None


def test_ambiguous_signoff_send_is_never_reclaimed_or_duplicated():
    item = payload()
    replies = service("signoff-send")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation), _signoff_result(item)
    )
    sending = replies.claim_send(generated)
    uncertain = replies.uncertain(sending, TimeoutError("ambiguous provider result"))
    assert uncertain.state.value == "SEND_UNCERTAIN"
    restarted = service("after-crash")
    assert restarted.claim_send(uncertain) is None
    assert restarted.recover_startup() == []
    assert restarted.repository.has_confirmed_sleep_signoff(
        account_scope=restarted.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        cycle_id="cycle-1",
    ) is False


def test_confirmed_signoff_is_exactly_once_and_restart_safe():
    item = payload()
    replies = service("signoff-confirm")
    operation, _ = replies.begin(item)
    generated = replies.generated(
        replies.claim_generation(operation), _signoff_result(item)
    )
    confirmed = replies.confirmed(replies.claim_send(generated), 770001)
    assert confirmed.state.value == "SENT_CONFIRMED"
    restarted = service("confirmed-restart")
    assert restarted.repository.has_confirmed_sleep_signoff(
        account_scope=restarted.ACCOUNT_SCOPE,
        chat_id=item.telegram_chat_id,
        cycle_id="cycle-1",
    ) is True
    duplicate, created = restarted.begin(item)
    assert created is False and duplicate.operation_id == confirmed.operation_id
    assert restarted.claim_send(duplicate) is None
    with connection_factory() as connection:
        row = connection.execute(
            "SELECT count(*) n,max(send_attempt_count) attempts "
            "FROM ordinary_chat_reply_operations"
        ).fetchone()
    assert row == {"n": 1, "attempts": 1}


def test_wake_response_pacing_precedes_durable_send_claim():
    item = payload()
    events = []

    class TrackingReplies:
        def __init__(self, delegate): self.delegate = delegate
        def __getattr__(self, name): return getattr(self.delegate, name)
        def claim_send(self, operation):
            events.append("claim")
            return self.delegate.claim_send(operation)

    class Pacing:
        def calculate(self, **_kwargs):
            return TelegramResponsePacingDecision(
                mode="APPLIED", policy="test", calculated_delay_ms=1,
                applied_delay_ms=1, reason="ordering certification",
            )
        async def wait(self, _decision): events.append("pacing")

    generated = result(item)
    replies = TrackingReplies(service("wake-runtime"))
    worker = runtime(Adapter(generated), Delivery([execution(770002)]), replies)
    worker._response_pacing = Pacing()
    asyncio.run(worker.handle_payload(item))
    assert events == ["pacing", "claim"]
    persisted = replies.repository.get(
        replies.begin(item)[0].operation_id
    )
    assert persisted.state.value == "SENT_CONFIRMED"


def test_sleep_deferral_does_not_complete_purchase_acknowledgement_and_ack_is_once():
    values = fixture()
    purchased_at = datetime.now(timezone.utc) - timedelta(minutes=2)
    with connection_factory() as connection:
        connection.execute(
            "UPDATE purchase_intents SET status='PURCHASED',"
            "attribution_result='ATTRIBUTED',purchased_at=%s "
            "WHERE purchase_intent_id=%s",
            (purchased_at, values["intent_id"]),
        )
    item = payload()
    _defer(item, wake=datetime.now(timezone.utc) + timedelta(hours=8))
    repository = PurchaseIntentRepository(connection_factory=connection_factory)
    pending = repository.get_unacknowledged_purchase(
        creator_profile_id=values["creator"],
        fanvue_account_id=values["account"],
        telegram_user_id=values["telegram"],
    )
    assert pending.purchase_acknowledged_at is None
    first_at = datetime.now(timezone.utc)
    first = repository.mark_purchase_acknowledged(values["intent_id"], at=first_at)
    second = repository.mark_purchase_acknowledged(
        values["intent_id"], at=first_at + timedelta(minutes=1)
    )
    assert first.purchase_acknowledged_at == first_at
    assert second.purchase_acknowledged_at == first_at
