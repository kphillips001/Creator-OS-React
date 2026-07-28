"""Account-scoped Creator Personality HTTP adapter for React."""

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.customers import _account_id
from app.repositories.creator_profile_repository import (
    get_active_creator_profile,
    update_creator_profile,
)


router = APIRouter(
    prefix="/api/v1/creator/personality",
    tags=["creator-personality"],
)


class CreatorPersonalityUpdate(BaseModel):
    persona_name: str
    age: int
    gender: str
    location: str
    is_active: bool
    archetype: str
    personality_description: str
    backstory: str
    lifestyle_context: str
    lifestyle_vibe: str
    daily_routine: str
    hobbies: str
    likes: str
    dislikes: str
    ideal_user_type: str
    turn_ons: str
    turn_offs: str
    sexual_style: str
    sexual_likes: str
    sexual_dislikes: str
    kinks: str
    fantasy_style: str
    tone_style: str
    flirt_style: str
    tease_intensity: int = Field(ge=0, le=10)
    push_pull_style: str
    mystery_level: str
    response_style: str
    pacing_style: str
    question_frequency: str
    emotional_depth: str
    affection_style: str
    jealousy_style: str
    availability_style: str
    conversation_hooks: str
    retention_hooks: str
    escalation_style: str
    escalation_triggers: str
    self_value_style: str
    persona_intensity: int = Field(ge=0, le=10)
    boundaries: str
    sexual_boundaries: str
    hard_limits: str
    response_rules: str


def _current_profile() -> tuple[int, dict]:
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id))
    if not profile:
        raise HTTPException(
            status_code=404,
            detail="No active Creator Profile exists for this creator account.",
        )
    return account_id, profile


@router.get("")
def get_creator_personality():
    _, profile = _current_profile()
    return jsonable_encoder(profile)


@router.put("")
def save_creator_personality(payload: CreatorPersonalityUpdate):
    account_id, current = _current_profile()
    updated = update_creator_profile(
        int(current["id"]),
        str(account_id),
        payload.model_dump(),
    )
    if not updated:
        raise HTTPException(
            status_code=409,
            detail="The existing Creator Profile could not be updated.",
        )
    return jsonable_encoder(updated)
