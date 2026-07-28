"""Ava Coach Phase 1 observational analysis and approval API."""
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.customers import _account_id
from app.services.ava_coach_service import AvaCoachService


router = APIRouter(prefix="/api/v1/ava-coach", tags=["ava-coach"])


class EditRecommendationRequest(BaseModel):
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=4000)


def _json(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return str(value) if isinstance(value, UUID) else value.isoformat()
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


@router.get("")
def dashboard():
    return _json(AvaCoachService().dashboard(_account_id()))


@router.post("/analyze")
def analyze():
    return _json(AvaCoachService().analyze(_account_id()))


@router.post("/recommendations/{recommendation_id}/{action}")
def transition(recommendation_id: UUID, action: str):
    try:
        return _json(AvaCoachService().transition(recommendation_id, action))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.patch("/recommendations/{recommendation_id}")
def edit_recommendation(
    recommendation_id: UUID, payload: EditRecommendationRequest,
):
    try:
        return _json(AvaCoachService().edit_recommendation(
            recommendation_id, title=payload.title,
            description=payload.description,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
