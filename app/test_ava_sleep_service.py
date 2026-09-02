from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.models.ava_sleep import AvaSleepState
from app.services.ava_sleep_service import AvaSleepService
from app.services.live_controlled_test_observer_service import LiveControlledTestObserverService


def at(hour, minute=0):
    # August EDT: UTC is four hours ahead of Ava.
    return datetime(2026, 8, 28 if hour < 12 else 27, (hour + 4) % 24, minute,
                    tzinfo=timezone.utc)


def decision(name="CONTINUE_CONVERSATION", reason="CONVERSATION_ONLY",
             active=False, receptiveness="COOLING"):
    return SimpleNamespace(
        decision=SimpleNamespace(value=name), reason_code=SimpleNamespace(value=reason),
        active_purchase_intent_id="intent" if active else None,
        decision_metadata={"commercialReceptiveness": {"state": receptiveness}},
    )


def test_schedule_is_bounded_stable_restart_safe_and_ava_local():
    now = datetime(2026, 8, 27, 18, tzinfo=timezone.utc)
    first = AvaSleepService(clock=lambda: now).schedule()
    second = AvaSleepService(clock=lambda: now).schedule()
    assert first == second
    cycle, bedtime, wake = first
    assert cycle == "2026-08-27"
    assert bedtime.tzinfo.key == wake.tzinfo.key == "America/New_York"
    assert datetime(2026, 8, 27, 23, 30, tzinfo=bedtime.tzinfo) <= bedtime <= datetime(2026, 8, 28, 0, 30, tzinfo=bedtime.tzinfo)
    assert datetime(2026, 8, 28, 7, 30, tzinfo=wake.tzinfo) <= wake <= datetime(2026, 8, 28, 8, 30, tzinfo=wake.tzinfo)


def test_daily_cycles_vary_but_remain_bounded():
    schedules = [AvaSleepService().schedule(datetime(2026, 8, day, 18, tzinfo=timezone.utc))[1:]
                 for day in (25, 26, 27)]
    assert len({(bed.hour, bed.minute, wake.hour, wake.minute) for bed, wake in schedules}) > 1


def test_customer_timezone_cannot_change_ava_schedule():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 27, 18, tzinfo=timezone.utc))
    assert service.evaluate().timezone == "America/New_York"


def test_bedtime_without_active_conversation_sleeps_silently():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    result = service.evaluate(active_conversation=False)
    assert result.state is AvaSleepState.ASLEEP
    assert result.signoff_required is False
    assert result.response_deferred is True


def test_active_conversation_requires_confirmed_signoff_before_sleep():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    pending = service.evaluate(active_conversation=True, signoff_delivered=False)
    complete = service.evaluate(active_conversation=True, signoff_delivered=True)
    assert pending.state is AvaSleepState.SLEEP_PENDING_SIGNOFF
    assert pending.signoff_pending is True
    assert complete.state is AvaSleepState.ASLEEP
    assert complete.transition_reason == "SIGNOFF_CONFIRMED"


@pytest.mark.parametrize(("name", "reason"), (
    ("PRESENT_OFFER", "DIRECT_PURCHASE_INTENT"),
    ("PAYMENT_PENDING", "PAYMENT_RECONCILIATION_PENDING"),
    ("UPSELL", "PURCHASE_VERIFIED"),
    ("CROSS_SELL", "SESSION_NEXT_UNLOCK_REQUEST"),
))
def test_canonical_commercial_decisions_override_bedtime(name, reason):
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    result = service.evaluate(active_conversation=True, commercial_decision=decision(name, reason))
    assert result.state is AvaSleepState.OVERRIDE_HOT_COMMERCIAL
    assert result.commercial_override_active is True


def test_generic_flirting_or_hot_without_commerce_does_not_override():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    result = service.evaluate(active_conversation=True,
                              commercial_decision=decision(receptiveness="HOT"))
    assert result.state is AvaSleepState.SLEEP_PENDING_SIGNOFF


def test_hot_active_intent_overrides_then_cooling_ends_override():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    hot = service.evaluate(active_conversation=True,
        commercial_decision=decision(active=True, receptiveness="HOT"))
    cool = service.evaluate(active_conversation=True,
        commercial_decision=decision(active=True, receptiveness="COOLING"))
    assert hot.state is AvaSleepState.OVERRIDE_HOT_COMMERCIAL
    assert cool.state is AvaSleepState.SLEEP_PENDING_SIGNOFF


def test_back_off_after_bedtime_never_overrides_sleep():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    result = service.evaluate(active_conversation=True,
        commercial_decision=decision("BACK_OFF", "BACK_OFF", active=True, receptiveness="HOT"))
    # BACK_OFF authority must terminate selling even if stale intent metadata remains.
    assert result.state is AvaSleepState.SLEEP_PENDING_SIGNOFF


def test_diagnostics_expose_minimum_certification_contract():
    service = AvaSleepService(clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc))
    values = service.evaluate(active_conversation=True).diagnostics(deferred_inbound_count=3)
    assert values.keys() >= {"state", "canonicalTimezone", "scheduledBedtime",
        "scheduledWakeTime", "bedtimeReached", "activeConversation",
        "signoffRequired", "signoffPending", "signoffDelivered",
        "commercialOverrideActive", "overrideReason", "deferredInboundCount",
        "nextWakeTime", "responseDeferredDueToSleep", "transitionReason"}


def test_runtime_architecture_reuses_pacing_and_durable_reply_namespace():
    import inspect
    from app.integrations.telegram.telethon_runtime import TelethonRuntime
    source = inspect.getsource(TelethonRuntime)
    assert "defer_for_sleep" in source
    assert "due_sleep_payloads" in source
    assert "self._response_pacing.wait" in source
    assert "shadow=True" not in inspect.getsource(TelethonRuntime._handle_authorized_payload)


def test_full_analysis_projects_signoff_confirmation_and_deferred_state():
    context = AvaSleepService(
        clock=lambda: datetime(2026, 8, 28, 6, tzinfo=timezone.utc),
    ).evaluate(active_conversation=True).diagnostics()
    confirmed = LiveControlledTestObserverService._sleep([{
        "state": "SENT_CONFIRMED", "last_error": None,
        "response_payload": {"diagnostic_metadata": {"sleep_context": context}},
    }])
    assert confirmed["signoffDelivered"] is True
    assert confirmed["signoffPending"] is False
    deferred = LiveControlledTestObserverService._sleep([{
        "state": "RETRYABLE", "last_error": "sleep_deferred:2026-08-27",
        "response_payload": None,
    }])
    assert deferred["state"] == "ASLEEP"
    assert deferred["deferredInboundCount"] == 1
