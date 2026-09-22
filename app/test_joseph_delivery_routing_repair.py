import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.services.telegram_sales_delivery_service import TelegramSalesDeliveryService


def result(*, identity="UNMAPPED", decision="NUDGE_ACTIVE_OFFER",
           requires_payment=False, diagnostics=None, metadata=None):
    return TelegramInboundResult(
        correlation_id="ordinary_reply:AVA_TELETHON_PRIVATE:91:6408",
        telegram_chat_id=91, telegram_user_id=91, message_id=6408,
        engine_user_id="telegram:91", response_text="persisted reply",
        offer_authorized=False, offer_link=None, blocked=False, error_code=None,
        delivery_requires_payment=requires_payment,
        delivery_payload={"delivery_type": "text", "metadata": metadata or {}},
        diagnostic_metadata={
            "telegram_identity_eligibility": identity,
            "customer_sales_decision": decision,
            **(diagnostics or {}),
        },
    )


def intent():
    return SimpleNamespace(
        purchase_intent_id="intent-1", creator_profile_id=2,
        commercial_offering_id="offering-1",
        commercial_publication_id="publication-1",
    )


def payload(message_id=6408):
    return TelegramInboundPayload(
        telegram_user_id=91, telegram_chat_id=91,
        message_text="customer inbound", message_id=message_id,
    )


def test_unmapped_active_offer_text_nudge_stays_in_ordinary_namespace():
    repository = Mock()
    service = TelegramSalesDeliveryService(repository=repository)

    operation, created = service.prepare(
        intent=intent(), result=result(), payload=payload(),
    )

    assert operation is None and created is False
    repository.get_or_create.assert_not_called()
    assert TelethonRuntime._ordinary_send_presents_intent(result()) is False


def test_mapped_canonical_commercial_delivery_is_unchanged():
    repository = Mock()
    repository.get_or_create.return_value = ("commercial-operation", True)
    service = TelegramSalesDeliveryService(repository=repository)
    commercial = result(identity="MAPPED_VERIFIED", requires_payment=True,
        diagnostics={
            "conversation_thread_id": 11,
            "conversation_fanvue_account_id": 2,
            "conversation_fanvue_user_id": 22,
            "paid_presentation_validated": True,
        })

    assert service.prepare(
        intent=intent(), result=commercial, payload=payload(),
    ) == ("commercial-operation", True)
    repository.get_or_create.assert_called_once()


def test_unmapped_ordinary_response_without_intent_is_unchanged():
    repository = Mock()
    service = TelegramSalesDeliveryService(repository=repository)

    assert service.prepare(
        intent=None,
        result=result(decision="CONTINUE_CONVERSATION"), payload=payload(),
    ) == (None, False)
    repository.get_or_create.assert_not_called()


def test_unmapped_bootstrap_behavior_is_unchanged():
    repository = Mock()
    service = TelegramSalesDeliveryService(repository=repository)

    assert service.prepare(
        intent=intent(), result=result(identity="UNMAPPED_BOOTSTRAP"),
        payload=payload(),
    ) == (None, False)
    repository.get_or_create.assert_not_called()
    assert TelethonRuntime._ordinary_send_presents_intent(
        result(identity="UNMAPPED_BOOTSTRAP", requires_payment=True)
    ) is True


@pytest.mark.parametrize("commercial_result", [
    result(requires_payment=True),
    result(diagnostics={"final_offer_authorized": True}),
    result(diagnostics={"paid_presentation_validated": True}),
    result(metadata={"message_purpose": "PURCHASE_DELIVERY"}),
])
def test_unmapped_genuine_commercial_delivery_still_requires_canonical_metadata(
        commercial_result):
    service = TelegramSalesDeliveryService(repository=Mock())

    with pytest.raises(
            ValueError, match="Canonical commercial delivery metadata is incomplete"):
        service.prepare(
            intent=intent(), result=commercial_result, payload=payload(),
        )


class Transport:
    def set_inbound_handler(self, handler):
        self.handler = handler


class Heartbeat:
    def __init__(self):
        self.at = datetime(2026, 9, 16, 19, 10, tzinfo=timezone.utc)
        self.events = []

    def now(self):
        return self.at

    def heartbeat(self, *, metadata=None, **_):
        self.events.append(dict(metadata or {}))


def test_resume_exception_is_visible_isolated_and_cooled_down():
    asyncio.run(_resume_exception_is_visible_isolated_and_cooled_down())


async def _resume_exception_is_visible_isolated_and_cooled_down():
    heartbeat = Heartbeat()
    runtime = TelethonRuntime(
        transport=Transport(), inbound_adapter=SimpleNamespace(),
        heartbeat_service=heartbeat,
        availability_failure_backoff_initial_seconds=5,
        availability_failure_backoff_max_seconds=20,
    )
    completed = []

    async def resume(item):
        if item.message_id == 6408:
            raise ValueError("injected Joseph failure")
        completed.append(item.message_id)

    runtime._resume_available_payload = resume
    bad, good = payload(6408), payload(6409)
    assert runtime._schedule_ordinary_resume(bad, now=heartbeat.now()) is True
    assert runtime._schedule_ordinary_resume(good, now=heartbeat.now()) is True
    await asyncio.gather(
        *tuple(runtime._ordinary_resume_tasks.values()), return_exceptions=True,
    )
    await asyncio.sleep(0.05)

    assert completed == [6409]
    failure = runtime._ordinary_resume_failures[(91, 6408)]
    assert failure["count"] == 1
    assert failure["retry_at"] == heartbeat.now() + timedelta(seconds=5)
    assert runtime._schedule_ordinary_resume(bad, now=heartbeat.now()) is False
    assert any(
        event.get("ordinary_reply_resume_healthy") is False
        and event.get("ordinary_reply_resume_consecutive_failures") == 1
        for event in heartbeat.events
    )

    heartbeat.at += timedelta(seconds=5)
    assert runtime._schedule_ordinary_resume(bad, now=heartbeat.now()) is True
    await asyncio.gather(
        *tuple(runtime._ordinary_resume_tasks.values()), return_exceptions=True,
    )
    await asyncio.sleep(0.05)
    assert runtime._ordinary_resume_failures[(91, 6408)]["count"] == 2
    assert runtime._ordinary_resume_failures[(91, 6408)]["retry_at"] == (
        heartbeat.now() + timedelta(seconds=10)
    )


def test_successful_resume_clears_prior_failure_health_without_regeneration():
    asyncio.run(_successful_resume_clears_prior_failure_health_without_regeneration())


async def _successful_resume_clears_prior_failure_health_without_regeneration():
    heartbeat = Heartbeat()
    runtime = TelethonRuntime(
        transport=Transport(), inbound_adapter=SimpleNamespace(),
        heartbeat_service=heartbeat,
    )
    item = payload()
    runtime._ordinary_resume_failures[(91, 6408)] = {
        "count": 2, "retry_at": heartbeat.now(), "error": "old failure",
    }
    generations = []

    async def resume(replayed):
        assert replayed.message_id == 6408
        generations.append(0)

    runtime._resume_available_payload = resume
    assert runtime._schedule_ordinary_resume(item, now=heartbeat.now()) is True
    await asyncio.gather(
        *tuple(runtime._ordinary_resume_tasks.values()), return_exceptions=True,
    )
    await asyncio.sleep(0.05)

    assert generations == [0]
    assert (91, 6408) not in runtime._ordinary_resume_failures
    assert any(
        event.get("ordinary_reply_resume_healthy") is True
        and event.get("ordinary_reply_resume_consecutive_failures") == 0
        for event in heartbeat.events
    )


def test_scheduler_replay_propagates_gateway_exception_to_resume_supervisor():
    asyncio.run(_scheduler_replay_propagates_gateway_exception_to_resume_supervisor())


async def _scheduler_replay_propagates_gateway_exception_to_resume_supervisor():
    class Replies:
        def begin(self, _payload):
            raise ValueError("injected routing failure")

    class Safety:
        def check_global_safety(self):
            return {"allowed": True}

    class Controlled:
        def decide(self, **_):
            return SimpleNamespace(allowed=False)

    runtime = TelethonRuntime(
        transport=Transport(), inbound_adapter=SimpleNamespace(),
        heartbeat_service=Heartbeat(), ordinary_reply_service=Replies(),
        global_safety_service=Safety(), controlled_autonomy_service=Controlled(),
    )

    with pytest.raises(ValueError, match="injected routing failure"):
        await runtime._resume_available_payload(payload())
