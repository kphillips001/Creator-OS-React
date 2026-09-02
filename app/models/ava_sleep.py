"""Canonical Ava persona availability state for private conversation."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any


class AvaSleepState(str, Enum):
    AWAKE = "AWAKE"
    WINDING_DOWN = "WINDING_DOWN"
    SLEEP_PENDING_SIGNOFF = "SLEEP_PENDING_SIGNOFF"
    ASLEEP = "ASLEEP"
    OVERRIDE_HOT_COMMERCIAL = "OVERRIDE_HOT_COMMERCIAL"


@dataclass(frozen=True)
class AvaSleepDecision:
    state: AvaSleepState
    cycle_id: str
    timezone: str
    bedtime: datetime
    wake_time: datetime
    bedtime_reached: bool
    active_conversation: bool
    signoff_required: bool
    signoff_pending: bool
    signoff_delivered: bool
    commercial_override_active: bool
    override_reason: str | None
    response_deferred: bool
    transition_reason: str

    def diagnostics(self, *, deferred_inbound_count: int = 0) -> dict[str, Any]:
        return {
            "state": self.state.value,
            "canonicalTimezone": self.timezone,
            "cycleId": self.cycle_id,
            "scheduledBedtime": self.bedtime.isoformat(),
            "scheduledWakeTime": self.wake_time.isoformat(),
            "bedtimeReached": self.bedtime_reached,
            "activeConversation": self.active_conversation,
            "signoffRequired": self.signoff_required,
            "signoffPending": self.signoff_pending,
            "signoffDelivered": self.signoff_delivered,
            "commercialOverrideActive": self.commercial_override_active,
            "overrideReason": self.override_reason,
            "deferredInboundCount": int(deferred_inbound_count),
            "nextWakeTime": self.wake_time.isoformat(),
            "responseDeferredDueToSleep": self.response_deferred,
            "transitionReason": self.transition_reason,
        }
