from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class AvaAvailabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    ACTIVE = "ACTIVE"
    INTERMITTENT = "INTERMITTENT"
    BUSY = "BUSY"
    AWAY = "AWAY"
    SLEEPING = "SLEEPING"


@dataclass(frozen=True)
class AvaAvailabilitySession:
    session_id: UUID
    account_scope: str
    state: AvaAvailabilityState
    started_at: datetime
    transition_at: datetime
    daypart: str
    transition_provenance: str
    transition_reason: str
    ended_at: datetime | None = None
