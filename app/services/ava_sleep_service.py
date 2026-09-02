"""Minimal deterministic sleep/wake policy for Ava's conversational persona."""
from __future__ import annotations

import hashlib
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Mapping
from zoneinfo import ZoneInfo

from app.models.ava_sleep import AvaSleepDecision, AvaSleepState
from app.services.ava_temporal_context_service import AvaTemporalContextService


class AvaSleepService:
    TIMEZONE = AvaTemporalContextService.AVA_TIMEZONE
    WIND_DOWN_MINUTES = 30

    def __init__(self, *, clock=lambda: datetime.now(timezone.utc), seed="AVA_SLEEP_MVP_V1"):
        self._clock = clock
        self._seed = seed

    def schedule(self, now: datetime | None = None) -> tuple[str, datetime, datetime]:
        local = self._local(now)
        # Before noon, the relevant cycle began on the preceding local date.
        cycle_date = local.date() - timedelta(days=1) if local.hour < 12 else local.date()
        bedtime_minute = self._bounded(cycle_date, "bed", 1410, 1470)
        wake_minute = self._bounded(cycle_date, "wake", 450, 510)
        bedtime = datetime.combine(cycle_date, time.min, ZoneInfo(self.TIMEZONE)) + timedelta(minutes=bedtime_minute)
        wake = datetime.combine(cycle_date + timedelta(days=1), time.min, ZoneInfo(self.TIMEZONE)) + timedelta(minutes=wake_minute)
        return cycle_date.isoformat(), bedtime, wake

    def evaluate(self, *, now: datetime | None = None, active_conversation=False,
                 signoff_delivered=False, commercial_decision: Any = None,
                 deferred_inbound_count=0) -> AvaSleepDecision:
        local = self._local(now)
        cycle, bedtime, wake = self.schedule(local)
        override, override_reason = self.commercial_override(commercial_decision)
        reached = local >= bedtime
        in_sleep_window = bedtime <= local < wake
        winding = bedtime - timedelta(minutes=self.WIND_DOWN_MINUTES) <= local < bedtime
        if in_sleep_window and override:
            state, reason = AvaSleepState.OVERRIDE_HOT_COMMERCIAL, "STRONG_COMMERCIAL_MOMENTUM"
        elif in_sleep_window and active_conversation and not signoff_delivered:
            state, reason = AvaSleepState.SLEEP_PENDING_SIGNOFF, "ACTIVE_CONVERSATION_AT_BEDTIME"
        elif in_sleep_window:
            state, reason = AvaSleepState.ASLEEP, (
                "SIGNOFF_CONFIRMED" if signoff_delivered else "BEDTIME_NO_ACTIVE_CONVERSATION"
            )
        elif winding and active_conversation:
            state, reason = AvaSleepState.WINDING_DOWN, "BEDTIME_APPROACHING"
        else:
            state, reason = AvaSleepState.AWAKE, "OUTSIDE_SLEEP_WINDOW"
        signoff_required = state is AvaSleepState.SLEEP_PENDING_SIGNOFF
        decision = AvaSleepDecision(
            state=state, cycle_id=cycle, timezone=self.TIMEZONE,
            bedtime=bedtime, wake_time=wake, bedtime_reached=reached,
            active_conversation=bool(active_conversation),
            signoff_required=signoff_required, signoff_pending=signoff_required,
            signoff_delivered=bool(signoff_delivered),
            commercial_override_active=state is AvaSleepState.OVERRIDE_HOT_COMMERCIAL,
            override_reason=override_reason if override else None,
            response_deferred=state is AvaSleepState.ASLEEP,
            transition_reason=reason,
        )
        return decision

    @staticmethod
    def commercial_override(decision: Any) -> tuple[bool, str | None]:
        if decision is None:
            return False, None
        value = getattr(getattr(decision, "decision", None), "value", None)
        reason = getattr(getattr(decision, "reason_code", None), "value", None)
        active_intent = getattr(decision, "active_purchase_intent_id", None) is not None
        metadata = dict(getattr(decision, "decision_metadata", None) or {})
        receptiveness = dict(metadata.get("commercialReceptiveness") or metadata.get("commercial_receptiveness") or {})
        state = str(receptiveness.get("state") or "").upper()
        strong_decisions = {"PRESENT_OFFER", "PRESENT_ALTERNATIVE_OFFER", "UPSELL", "CROSS_SELL", "NUDGE_ACTIVE_OFFER", "PAYMENT_PENDING"}
        strong_reasons = {"DIRECT_PURCHASE_INTENT", "PRICE_REQUEST", "SESSION_NEXT_UNLOCK_REQUEST", "ACTIVE_SESSION_PRECEDENCE"}
        if value in {"BACK_OFF", "NO_SALE", "WAIT", "MANUAL_REVIEW"}:
            return False, None
        if value in strong_decisions:
            return True, f"SALES_BRAIN_{value}"
        if reason in strong_reasons:
            return True, f"SALES_BRAIN_{reason}"
        if active_intent and state == "HOT":
            return True, "HOT_ACTIVE_PURCHASE_INTENT"
        return False, None

    def _local(self, now):
        value = now or self._clock()
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo(self.TIMEZONE))

    def _bounded(self, cycle_date: date, purpose: str, lower: int, upper: int) -> int:
        digest = hashlib.sha256(f"{self._seed}:{cycle_date.isoformat()}:{purpose}".encode()).digest()
        return lower + int.from_bytes(digest[:4], "big") % (upper - lower + 1)
