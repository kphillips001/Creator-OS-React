"""Persistent Ava-owned activity sessions, independent of customer activity."""
from __future__ import annotations

import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo

from app.models.ava_availability_session import AvaAvailabilitySession, AvaAvailabilityState


@dataclass(frozen=True)
class AvaAvailabilityDecision:
    state: AvaAvailabilityState
    delay_seconds: float
    quiet_period_seconds: float
    available_at: datetime
    session_id: str = ""
    session_started_at: datetime | None = None
    transition_at: datetime | None = None
    high_value_prospect: bool = False
    market_tier: str = "UNCLASSIFIED"

    @property
    def category(self): return self.state.value

    def diagnostics(self):
        return {"policy": "AVA_PERSISTENT_ACTIVITY_SESSION_V1", "availabilityState": self.state.value,
            "delaySeconds": round(self.delay_seconds, 3), "quietPeriodSeconds": round(self.quiet_period_seconds, 3),
            "availableAt": self.available_at.isoformat(), "sessionId": self.session_id,
            "sessionStartedAt": self.session_started_at.isoformat() if self.session_started_at else None,
            "transitionAt": self.transition_at.isoformat() if self.transition_at else None,
            "persistentSession": True,
            "messagePriorityAffectsAvailability": self.high_value_prospect,
            "operatorClassification": "HIGH_VALUE_PROSPECT" if self.high_value_prospect else None,
            "marketTier": self.market_tier,
            "effectiveProspectInvestment": self._investment(),
            "typingSeparate": True, "timezone": "America/New_York"}

    def _investment(self):
        if self.market_tier == "HIGH" and self.high_value_prospect: return "MAXIMUM"
        if self.market_tier == "HIGH" or self.high_value_prospect: return "HIGH"
        return "STANDARD"


class _MemorySessionRepository:
    """Deterministic test authority; production uses PostgreSQL."""
    def __init__(self): self.current = {}

    def current_or_transition(self, *, account_scope, now, initial_state, next_state, duration, daypart):
        prior = self.current.get(account_scope)
        if prior is not None and prior.transition_at > now: return prior
        previous = prior.state if prior is not None else None
        state = initial_state(now) if previous is None else next_state(previous, now)
        session = AvaAvailabilitySession(
            session_id=uuid4(), account_scope=account_scope, state=state, started_at=now,
            transition_at=duration(state, now), daypart=daypart(now),
            transition_provenance="AVA_AVAILABILITY_SESSION_POLICY_V1",
            transition_reason="INITIAL_STATE" if previous is None else "SESSION_EXPIRED")
        self.current[account_scope] = session
        return session


class AvaHumanAvailabilityService:
    DEFAULT_RANGES = {
        AvaAvailabilityState.AVAILABLE: (20.0, 90.0), AvaAvailabilityState.ACTIVE: (60.0, 240.0),
        AvaAvailabilityState.INTERMITTENT: (180.0, 720.0), AvaAvailabilityState.BUSY: (600.0, 2100.0),
        AvaAvailabilityState.AWAY: (1800.0, 7200.0), AvaAvailabilityState.SLEEPING: (3600.0, 14400.0)}
    SESSION_DURATION_RANGES = {
        AvaAvailabilityState.AVAILABLE: (300.0, 1200.0), AvaAvailabilityState.ACTIVE: (900.0, 2700.0),
        AvaAvailabilityState.INTERMITTENT: (600.0, 2100.0), AvaAvailabilityState.BUSY: (600.0, 2100.0),
        AvaAvailabilityState.AWAY: (1800.0, 7200.0)}
    TRANSITIONS = {
        AvaAvailabilityState.AVAILABLE: ((AvaAvailabilityState.ACTIVE, .65), (AvaAvailabilityState.INTERMITTENT, .35)),
        AvaAvailabilityState.ACTIVE: ((AvaAvailabilityState.ACTIVE, .20), (AvaAvailabilityState.INTERMITTENT, .50), (AvaAvailabilityState.BUSY, .30)),
        AvaAvailabilityState.INTERMITTENT: ((AvaAvailabilityState.ACTIVE, .35), (AvaAvailabilityState.BUSY, .40), (AvaAvailabilityState.AWAY, .25)),
        AvaAvailabilityState.BUSY: ((AvaAvailabilityState.INTERMITTENT, .45), (AvaAvailabilityState.AWAY, .35), (AvaAvailabilityState.ACTIVE, .20)),
        AvaAvailabilityState.AWAY: ((AvaAvailabilityState.INTERMITTENT, .65), (AvaAvailabilityState.ACTIVE, .35)),
        AvaAvailabilityState.SLEEPING: ((AvaAvailabilityState.AVAILABLE, .55), (AvaAvailabilityState.ACTIVE, .45))}

    def __init__(self, *, uniform=None, random_value=None, now=None, state_selector=None,
                 repository=None, account_scope="AVA_TELETHON_PRIVATE"):
        self._uniform = uniform or random.uniform; self._random = random_value or random.random
        self._now = now or (lambda: datetime.now(timezone.utc)); self._state_selector = state_selector
        self._account_scope = account_scope
        if repository is None:
            injected = any(value is not None for value in (uniform, random_value, now, state_selector))
            if injected: repository = _MemorySessionRepository()
            else:
                from app.repositories.ava_availability_session_repository import AvaAvailabilitySessionRepository
                repository = AvaAvailabilitySessionRepository()
        self._repository = repository

    @classmethod
    def _range(cls, state):
        default = cls.DEFAULT_RANGES[state]; raw = os.getenv(f"AVA_CHAT_CHECK_{state.value}_SECONDS", "").strip()
        if not raw: return default
        try:
            low, high = (float(item.strip()) for item in raw.split(",", 1))
            return max(0.0, low), max(max(0.0, low), high)
        except (TypeError, ValueError): return default

    @staticmethod
    def _daypart(at):
        hour = at.astimezone(ZoneInfo("America/New_York")).hour
        if 2 <= hour < 8: return "SLEEP"
        if hour < 12: return "MORNING"
        if hour < 17: return "AFTERNOON"
        if hour < 22: return "EVENING"
        return "LATE_NIGHT"

    def _initial_state(self, at):
        if self._daypart(at) == "SLEEP": return AvaAvailabilityState.SLEEPING
        if self._state_selector is not None: return AvaAvailabilityState(self._state_selector(at))
        value = float(self._random())
        for state, ceiling in ((AvaAvailabilityState.AVAILABLE, .12), (AvaAvailabilityState.ACTIVE, .36),
                               (AvaAvailabilityState.INTERMITTENT, .70), (AvaAvailabilityState.BUSY, .92)):
            if value < ceiling: return state
        return AvaAvailabilityState.AWAY

    def _next_state(self, previous, at):
        if self._daypart(at) == "SLEEP": return AvaAvailabilityState.SLEEPING
        value = float(self._random()); cumulative = 0.0
        for state, weight in self.TRANSITIONS[previous]:
            cumulative += weight
            if value <= cumulative: return state
        return self.TRANSITIONS[previous][-1][0]

    def _transition_at(self, state, at):
        local = at.astimezone(ZoneInfo("America/New_York"))
        if state == AvaAvailabilityState.SLEEPING:
            wake = local.replace(hour=8, minute=0, second=0, microsecond=0)
            if wake <= local: wake += timedelta(days=1)
            return wake.astimezone(timezone.utc)
        low, high = self.SESSION_DURATION_RANGES[state]
        return at + timedelta(seconds=float(self._uniform(low, high)))

    def current_session(self, *, at=None):
        instant = at or self._now()
        return self._repository.current_or_transition(account_scope=self._account_scope, now=instant,
            initial_state=self._initial_state, next_state=self._next_state,
            duration=self._transition_at, daypart=self._daypart)

    def state(self, *, at=None): return self.current_session(at=at).state

    def calculate(self, *, inbound_text: str = "", received_at=None,
                  high_value_prospect: bool = False,
                  market_tier: str | None = None):
        now = self._now(); session = self.current_session(at=now)
        tier = str(market_tier or "UNCLASSIFIED")
        if tier not in {"HIGH", "MEDIUM", "LOW", "UNCLASSIFIED"}:
            raise ValueError("Unsupported Market Tier scheduling profile.")
        quiet = max(8.0, float(os.getenv("AVA_AVAILABILITY_QUIET_PERIOD_SECONDS", "8")))
        if session.state == AvaAvailabilityState.SLEEPING:
            available_at = session.transition_at
        elif session.state in {AvaAvailabilityState.BUSY, AvaAvailabilityState.AWAY}:
            remaining = max(quiet, (session.transition_at - now).total_seconds())
            multiplier = (.25 if tier == "HIGH" and high_value_prospect else
                          .65 if tier == "HIGH" else
                          .35 if high_value_prospect else None)
            available_at = (now + timedelta(seconds=max(quiet, remaining * multiplier))
                            if multiplier is not None else session.transition_at)
        else:
            delay = float(self._uniform(*self._range(session.state)))
            delay *= (.35 if tier == "HIGH" and high_value_prospect else
                      .75 if tier == "HIGH" else
                      .5 if high_value_prospect else 1.0)
            available_at = min(now + timedelta(seconds=max(delay, quiet)), session.transition_at)
        delay = max(0.0, (available_at - now).total_seconds())
        return AvaAvailabilityDecision(session.state, delay, quiet, available_at, str(session.session_id),
            session.started_at, session.transition_at, high_value_prospect, tier)
