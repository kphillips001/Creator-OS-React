"""Read-only Creator Intelligence Center API."""

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder

from app.api.customers import _account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.services.creator_intelligence_service import CreatorIntelligenceService


router = APIRouter(prefix="/api/v1/creator-intelligence", tags=["creator-intelligence"])


def _service() -> CreatorIntelligenceService:
    return CreatorIntelligenceService()


@router.get("")
def creator_intelligence():
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id)) or {}
    creator_profile_id = int(profile.get("id") or 0)
    if not creator_profile_id:
        creator_profile_id = account_id
    return jsonable_encoder(
        _service().dashboard(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=account_id,
        )
    )
