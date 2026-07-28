"""Editable account-scoped Creator World Model document."""

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class CreatorWorldModel:
    id: int | None
    creator_profile_id: int
    fanvue_account_id: str
    internal_home_base: str
    public_location_description: str
    home_and_indoor_environments: str
    coastal_environments: str
    mountains_lakes_and_small_town_escapes: str
    climate_and_seasonal_behavior: str
    seasonal_activities: str
    holiday_rhythm: str
    travel_and_variety_guidance: str
    created_at: datetime | None = None
    updated_at: datetime | None = None
