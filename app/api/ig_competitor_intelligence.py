from datetime import date, datetime
import re

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.api.background_operations import _context
from app.repositories.ig_competitor_intelligence_repository import IgCompetitorIntelligenceRepository

router = APIRouter(prefix="/api/v1/ig-intelligence", tags=["ig-competitor-intelligence"])
USERNAME = re.compile(r"^[a-z0-9._]{1,30}$")


class CompetitorCreate(BaseModel):
    username: str
    followers: int = Field(ge=0)


class FollowersPatch(BaseModel):
    followers: int = Field(ge=0)


def _payload(row):
    iso = lambda value: value.isoformat() if isinstance(value, (date, datetime)) else value
    return {"id": str(row["id"]), "username": row["username"],
            "followers": int(row["followers_count"]), "profileImageUrl": row.get("profile_image_url"),
            "archivedAt": iso(row.get("archived_at")), "createdAt": iso(row["created_at"]), "updatedAt": iso(row["updated_at"])}


@router.get("/competitors")
def list_competitors(archived: bool = False):
    creator_profile_id, _ = _context()
    return {"items": [_payload(row) for row in IgCompetitorIntelligenceRepository().list(creator_profile_id, archived=archived)]}


@router.post("/competitors", status_code=201)
def create_competitor(body: CompetitorCreate):
    creator_profile_id, _ = _context(); repo = IgCompetitorIntelligenceRepository()
    username = body.username.strip().lstrip("@").lower()
    if not USERNAME.fullmatch(username): raise HTTPException(422, "Enter a valid IG username.")
    if repo.get_by_username(creator_profile_id, username): raise HTTPException(409, "This IG competitor already exists.")
    return _payload(repo.create(creator_profile_id, username=username, followers_count=body.followers))


@router.patch("/competitors/{competitor_id}/followers")
def update_followers(competitor_id: str, body: FollowersPatch):
    creator_profile_id, _ = _context(); row = IgCompetitorIntelligenceRepository().update_followers(creator_profile_id, competitor_id, body.followers)
    if not row: raise HTTPException(404, "IG competitor not found.")
    return _payload(row)


@router.post("/competitors/{competitor_id}/archive")
def archive_competitor(competitor_id: str):
    creator_profile_id, _ = _context(); row = IgCompetitorIntelligenceRepository().archive(creator_profile_id, competitor_id)
    if not row: raise HTTPException(404, "IG competitor not found.")
    return _payload(row)


@router.post("/competitors/{competitor_id}/restore")
def restore_competitor(competitor_id: str):
    creator_profile_id, _ = _context(); row = IgCompetitorIntelligenceRepository().restore(creator_profile_id, competitor_id)
    if not row: raise HTTPException(404, "IG competitor not found.")
    return _payload(row)
