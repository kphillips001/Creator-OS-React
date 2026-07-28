"""Editable account-scoped social creative direction document."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class SocialCreativeDirection:
    id: int | None
    creator_profile_id: int
    fanvue_account_id: str
    purpose: str
    wardrobe: str
    visual_style: str
    seasonal_guidance: str
    things_to_avoid: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
