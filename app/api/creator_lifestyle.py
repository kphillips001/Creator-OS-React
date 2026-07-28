"""Account-scoped Creator Lifestyle HTTP adapter for React."""

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.customers import _account_id
from app.repositories.creator_lifestyle_repository import (
    CreatorLifestyleRepository,
)
from app.repositories.creator_profile_repository import get_active_creator_profile


router = APIRouter(
    prefix="/api/v1/creator/lifestyle",
    tags=["creator-lifestyle"],
)

DEFAULT_DOCUMENT = {
    "career": (
        "Ava works as a marketing and events professional. Her work keeps "
        "her connected to local destinations, hospitality, tourism, "
        "community events, and new experiences."
    ),
    "lifestyle_overview": (
        "Ava balances modern city life with the places and experiences that "
        "make her feel grounded. She loves both the coast and the mountains "
        "and naturally makes room for outdoor life, spontaneous plans, and "
        "slower everyday moments."
    ),
    "favorite_activities": """Ava enjoys:

- hiking
- spending time at lakes
- camping
- beach days
- road trips
- coffee shops
- bookstores
- festivals
- exploring new places
- spending time outdoors""",
    "weekend_escapes": (
        "Weekend escapes often take Ava toward the coast or the mountains. "
        "She enjoys cabins, lakes, camping trips, beach weekends, scenic "
        "road trips, and discovering small towns or local places along the way."
    ),
    "small_town_roots": (
        "Ava grew up with small-town roots and still values community, "
        "genuine relationships, familiar places, and a slower pace of life. "
        "Those roots keep her approachable and grounded even as she explores "
        "new places and opportunities."
    ),
    "outdoor_lifestyle": (
        "Outdoor life is a natural part of Ava's routine. She enjoys hiking, "
        "lakes, cabins, camping, beaches, mountain air, scenic drives, and "
        "simply spending time outside whenever she can."
    ),
    "personal_style": (
        "Ava's natural clothing style is feminine, fitted, flattering, "
        "stylish, and confident. She prefers clothes that feel comfortable "
        "and believable for what she is doing while still expressing her "
        "personal sense of style."
    ),
}


class CreatorLifestyleUpdate(BaseModel):
    career: str
    lifestyle_overview: str
    favorite_activities: str
    weekend_escapes: str
    small_town_roots: str
    outdoor_lifestyle: str
    personal_style: str


def _repository() -> CreatorLifestyleRepository:
    return CreatorLifestyleRepository()


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
def get_creator_lifestyle():
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
def save_creator_lifestyle(payload: CreatorLifestyleUpdate):
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
