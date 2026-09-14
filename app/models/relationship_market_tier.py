"""Closed, operator-assigned relationship Market Tier contracts."""
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class RelationshipMarketTier(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class EffectiveProspectInvestment(str, Enum):
    MAXIMUM = "MAXIMUM"
    HIGH = "HIGH"
    STANDARD = "STANDARD"
    LOW = "LOW"
    BUYER_AUTHORITY = "BUYER_AUTHORITY"


@dataclass(frozen=True)
class RelationshipMarketTierRecord:
    market_tier_id: UUID
    creator_profile_id: int
    fanvue_account_id: int
    telegram_user_id: int
    telegram_chat_id: int
    market_tier: RelationshipMarketTier
    version: int
    changed_by: str
    changed_at: datetime
    reason: str | None = None
    removed_by: str | None = None
    removed_at: datetime | None = None
    replaced_by: UUID | None = None
