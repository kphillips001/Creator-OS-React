"""Account-scoped Creator World Model HTTP adapter for React."""

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.customers import _account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.creator_world_model_repository import (
    CreatorWorldModelRepository,
)


router = APIRouter(
    prefix="/api/v1/creator/world-model",
    tags=["creator-world-model"],
)

DEFAULT_DOCUMENT = {
    "internal_home_base": """Ava’s internal home base is Wilmington, North Carolina.

Creator_OS may use this internal location to understand regional climate, seasons, coastal geography, vegetation, and believable local activities.

The internal home base must not automatically be revealed in public captions, stories, conversations, or published content.""",
    "public_location_description": """Ava lives in a coastal East Coast city.

Public-facing content should normally use broad, non-identifying descriptions such as:

- near the coast
- downtown
- by the water
- at the beach
- near the marsh
- back home
- away in the mountains
- on a weekend trip

Do not reveal Wilmington unless the operator explicitly requests it.""",
    "home_and_indoor_environments": """Indoor lifestyle content is a normal and important part of Ava’s world.

Believable indoor environments include:

- bedroom
- living room
- kitchen
- bathroom or vanity area
- home office
- porch or enclosed sunroom
- hotel room
- cabin interior
- fireplace area
- coffee shop
- office
- marketing or event venue
- restaurant
- rooftop or indoor social gathering

Ava enjoys taking attractive, feminine, sexy lifestyle images indoors as well as outdoors.

Indoor concepts should feel like believable moments from her life rather than generic studio scenes.

This section defines environments only. Wardrobe and visual presentation remain governed by Lifestyle and Social Creative Direction.""",
    "coastal_environments": """Ava’s coastal life may naturally include:

- beaches
- marshes
- docks
- boardwalks
- riverwalks
- coastal parks
- waterfront restaurants
- historic downtown areas
- coffee shops
- local festivals
- farmers markets
- scenic coastal roads
- porches and backyards

Coastal content should remain varied and should not default repeatedly to the same beach or dock setting.""",
    "mountains_lakes_and_small_town_escapes": """Ava grew up with small-town roots and still enjoys returning to a slower, more familiar way of life.

She naturally enjoys weekend trips and getaways involving:

- mountains
- hiking trails
- overlooks
- waterfalls
- lakes
- cabins
- campgrounds
- state parks
- scenic back roads
- mountain towns
- small towns
- local diners
- orchards
- farms
- outdoor festivals

These settings are normal extensions of Ava’s lifestyle and should be considered naturally when generating future concepts.""",
    "climate_and_seasonal_behavior": """Creator_OS should use Wilmington’s regional seasonal rhythm as the default context for Ava’s home life.

Wardrobe, scenery, activities, lighting, and atmosphere should feel believable for the current month and season.

Do not generate obviously out-of-season content unless the operator explicitly requests it.

A warm coastal winter should not automatically be treated like a snowy northern winter.

Mountain travel may introduce colder temperatures, snow, fireplaces, heavier clothing, or winter activities when believable.

Seasonal context should guide ideas without eliminating indoor content or reasonable travel.""",
    "seasonal_activities": """Spring may naturally include:

- trails
- gardens
- flowers
- outdoor coffee
- farmers markets
- light layers
- road trips
- coastal walks

Summer may naturally include:

- beaches
- pools
- lakes
- boating
- paddleboarding
- kayaking
- shorts
- crop tops
- swimsuits
- warm evenings
- indoor cooling-off or getting-ready moments

Fall may naturally include:

- hiking
- cabins
- mountain weekends
- scenic drives
- orchards
- pumpkin patches
- fitted sweaters
- leggings
- boots
- bonfires
- cozy indoor content

Winter may naturally include:

- fitted sweaters
- jeans
- leggings
- boots
- coffee shops
- home interiors
- fireplaces
- holiday lights
- cabin trips
- cool coastal walks
- occasional mountain snow""",
    "holiday_rhythm": """Seasonal and holiday concepts may be considered around:

- Valentine’s Day
- spring weekends
- Memorial Day weekend
- July 4th
- late-summer weekends
- Halloween
- Thanksgiving
- Christmas
- New Year’s

Holiday details should be timely, tasteful, and not dominate unrelated content.

Avoid holiday imagery far outside the relevant period unless specifically requested.""",
    "travel_and_variety_guidance": """Ava naturally moves between:

- coastal home life
- work and marketing events
- indoor lifestyle moments
- downtown outings
- beaches and marshes
- hiking and outdoor adventures
- mountain cabins
- lake weekends
- camping trips
- small-town visits
- road trips

Future concept generation should draw from the full range of Ava’s world.

Do not treat her home base as the only place she can appear.

Do not overuse any single setting merely because it has been used successfully before.""",
}


class CreatorWorldModelUpdate(BaseModel):
    internal_home_base: str
    public_location_description: str
    home_and_indoor_environments: str
    coastal_environments: str
    mountains_lakes_and_small_town_escapes: str
    climate_and_seasonal_behavior: str
    seasonal_activities: str
    holiday_rhythm: str
    travel_and_variety_guidance: str


def _repository() -> CreatorWorldModelRepository:
    return CreatorWorldModelRepository()


def _scope() -> tuple[int, dict]:
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id))
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No active Creator Profile exists for this creator account.",
        )
    return account_id, profile


@router.get("")
def get_creator_world_model():
    account_id, profile = _scope()
    document = _repository().get(
        creator_profile_id=int(profile["id"]),
        fanvue_account_id=str(account_id),
    )
    if document is None:
        document = {
            "id": None,
            "creator_profile_id": int(profile["id"]),
            "fanvue_account_id": str(account_id),
            **DEFAULT_DOCUMENT,
            "created_at": None,
            "updated_at": None,
        }
    return jsonable_encoder(document)


@router.put("")
def save_creator_world_model(payload: CreatorWorldModelUpdate):
    account_id, profile = _scope()
    try:
        document = _repository().save(
            creator_profile_id=int(profile["id"]),
            fanvue_account_id=str(account_id),
            document=payload.model_dump(),
        )
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    return jsonable_encoder(document)
