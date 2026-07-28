"""Account-scoped Social Creative Direction HTTP adapter for React."""

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel

from app.api.customers import _account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.social_creative_direction_repository import (
    SocialCreativeDirectionRepository,
)


router = APIRouter(
    prefix="/api/v1/creator/social-creative-direction",
    tags=["social-creative-direction"],
)

DEFAULT_DOCUMENT = {
    "purpose": (
        "Create visually engaging content for public social platforms that "
        "attracts attention, encourages conversation, and naturally guides "
        "followers toward premium experiences."
    ),
    "wardrobe": """Ava should generally wear flattering, form-fitting clothing that highlights her figure while remaining believable for everyday life.

Preferred wardrobe may include:

- leggings
- yoga pants
- crop tops
- tank tops
- fitted jeans
- athletic shorts
- swimsuits
- fitted dresses
- casual athletic wear""",
    "visual_style": """Images should generally portray Ava as naturally beautiful, confident, approachable, playful, and feminine.

Social content may emphasize:

- cleavage
- midriff
- curves
- toned legs
- confident posture

while maintaining an authentic girl-next-door lifestyle feel.""",
    "seasonal_guidance": """Creator_OS should automatically adapt clothing, scenery, and activities to the current season.

Avoid obviously out-of-season clothing or environments unless specifically requested.

Maintain believable seasonal consistency.""",
    "things_to_avoid": """Avoid:

- repetitive outfits
- unrealistic fashion-editorial posing
- plastic-looking skin
- awkward posing
- overly artificial glamour
- clothing that hides Ava's figure without creative purpose""",
}


class SocialCreativeDirectionUpdate(BaseModel):
    purpose: str
    wardrobe: str
    visual_style: str
    seasonal_guidance: str
    things_to_avoid: str


def _repository() -> SocialCreativeDirectionRepository:
    return SocialCreativeDirectionRepository()


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
def get_social_creative_direction():
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
def save_social_creative_direction(payload: SocialCreativeDirectionUpdate):
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
