"""Editable account-scoped creator lifestyle document."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CreatorLifestyle:
    id: int | None
    creator_profile_id: int
    fanvue_account_id: str
    career: str
    lifestyle_overview: str
    favorite_activities: str
    weekend_escapes: str
    small_town_roots: str
    outdoor_lifestyle: str
    personal_style: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
