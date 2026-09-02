"""Read-only Photoshoot Gallery projection for completed commerce sets."""

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field

from app.api.asset_library import _creator_profile
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.repositories.photoshoot_bundle_teaser_repository import PhotoshootBundleTeaserRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService
from app.services.photoshoot_member_curation_service import PhotoshootMemberCurationService
from app.services.photoshoot_session_teaser_service import PhotoshootSessionTeaserService


router = APIRouter(prefix="/api/v1/photoshoot-gallery", tags=["photoshoot-gallery"])


class MovePhotoshootMembersRequest(BaseModel):
    assetIds: list[int] = Field(min_length=1)


class UseSessionTeaserRequest(BaseModel):
    candidateImageId: str = Field(min_length=1)


def _repository():
    return PhotoshootCommerceRepository()


def _service():
    return PhotoshootCommerceDeliverableService(repository=_repository())


def _teaser_repository():
    return PhotoshootBundleTeaserRepository()


def _payload(row):
    source_kind = str(row.get("source_kind") or "PHOTOSHOOT_STUDIO")
    bundle_channel = row.get("bundle_sales_channel")
    if source_kind != "GENERATION_LIBRARY_IMPORT" and not bundle_channel:
        bundle_channel = "CHAT"
    return {
        "deliverableId": str(row["deliverable_id"]),
        "sessionId": row["photoshoot_session_id"],
        "name": row.get("display_title") or row["display_name"],
        "description": row.get("display_description"),
        "completedAt": row["completed_at"],
        "shotCount": int(row["shot_count"]),
        "heroAssetId": row["hero_asset_id"],
        "imageUrl": f'/api/v1/assets/{row["hero_asset_id"]}/thumbnail' if row["hero_asset_id"] else None,
        "intelligenceStatus": row["intelligence_status"],
        "registrationState": row["registration_state"],
        "sellingMode": row.get("selling_mode") or "SESSION",
        "bundleSalesChannel": bundle_channel if str(row.get("selling_mode") or "SESSION") == "BUNDLE" else None,
        "sourceKind": source_kind,
    }


@router.get("")
def list_photoshoots(page: int = Query(1, ge=1), page_size: int = Query(24, ge=1, le=60)):
    page = int(page) if isinstance(page, int) else 1
    page_size = int(page_size) if isinstance(page_size, int) else 24
    creator_id = int(_creator_profile()["id"])
    repository = _repository()
    if hasattr(repository, "list_gallery_page"):
        rows, total = repository.list_gallery_page(creator_id, page=page, page_size=page_size)
    else:  # Compatibility for injected legacy repository test doubles.
        all_rows = repository.list_gallery(creator_id)
        total = len(all_rows)
        rows = all_rows[(page - 1) * page_size:page * page_size]
    return {
        "items": jsonable_encoder([_payload(row) for row in rows]),
        "total": total, "page": page, "pageSize": page_size,
        "totalPages": max(1, (total + page_size - 1) // page_size),
    }


@router.get("/{deliverable_id}")
def photoshoot_details(deliverable_id: str):
    creator_id = int(_creator_profile()["id"])
    repo = _repository()
    row = repo.get(deliverable_id)
    if row is None or int(row["creator_profile_id"]) != creator_id or not row["is_active"]:
        raise HTTPException(status_code=404, detail="Photoshoot not found.")
    item = _payload(row)
    canonical = repo.get_intelligence(row["photoshoot_session_id"]) or {}
    profile = canonical.get("profile_data") or row.get("intelligence_profile") or {}
    production = canonical.get("production_analysis") or profile.get("production_analysis") or profile
    cross_validation = canonical.get("cross_validation") or profile.get("cross_validation") or {}
    item["intelligence"] = profile
    item["productionIntelligence"] = {
        **production,
        "hero_shot": cross_validation.get("hero_asset_id"),
        "cover_shot": cross_validation.get("cover_asset_id"),
        "thumbnail_shot": cross_validation.get("thumbnail_asset_id"),
        "teaser_shot": cross_validation.get("teaser_asset_id"),
    }
    item["technical"] = {
        "deliverableId": str(row["deliverable_id"]),
        "sessionId": row["photoshoot_session_id"],
        "heroAssetId": row["hero_asset_id"],
        "galleryPath": row["gallery_path"],
        "sourceKind": str(row.get("source_kind") or "PHOTOSHOOT_STUDIO"),
    }
    shot_rows = repo.shot_intelligence(
        row["photoshoot_session_id"], canonical.get("intelligence_version") or "completed_photoshoot_v2"
    ) if canonical else ()
    if not shot_rows:
        shot_rows = repo.latest_shot_intelligence(row["photoshoot_session_id"])
    shots_by_asset = {int(shot["asset_id"]): shot for shot in shot_rows}
    members = repo.intelligence_members(row["photoshoot_session_id"])
    item["members"] = [
        {"assetId": member["asset_id"], "shotOrder": member["shot_order"],
         "isHero": member["is_hero"], "imageUrl": f'/api/v1/assets/{member["asset_id"]}/thumbnail',
         "intelligence": (shots_by_asset.get(int(member["asset_id"]), {}).get("profile_data")
                          or member.get("content_profile") or member.get("normalized_context") or {})}
        for member in members
    ]
    teaser = _teaser_repository().get(str(row["deliverable_id"]))
    item["commercialAssets"] = ([{
        "assetId": int(teaser["teaser_asset_id"]),
        "kind": "PROMOTIONAL_TEASER",
        "label": "Promotional Teaser",
        "status": "READY",
        "previewUrl": f'/api/v1/assets/{int(teaser["teaser_asset_id"])}/media',
    }] if teaser else [])
    try:
        item["memberCuration"] = PhotoshootMemberCurationService(repository=repo).inspect(
            deliverable_id, creator_profile_id=creator_id)
    except AttributeError:  # Compatibility for narrow repository test doubles.
        item["memberCuration"] = {"eligible": False, "reason": "Member curation unavailable.",
                                  "memberCount": len(item["members"]), "maximumExtractable": 0}
    item["sessionTeaser"] = PhotoshootSessionTeaserService().eligibility(
        deliverable_id, creator_profile_id=creator_id)
    return jsonable_encoder(item)


@router.post("/{deliverable_id}/session-teaser-intents")
def create_session_teaser_intent(deliverable_id: str):
    try:
        return PhotoshootSessionTeaserService().create_intent(
            deliverable_id, creator_profile_id=int(_creator_profile()["id"]))
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{deliverable_id}/members/move-to-images")
def move_photoshoot_members_to_images(deliverable_id: str,
                                      request: MovePhotoshootMembersRequest):
    creator_id = int(_creator_profile()["id"])
    try:
        result = PhotoshootMemberCurationService().move_to_images(
            deliverable_id, creator_profile_id=creator_id, asset_ids=request.assetIds)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error))
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error))
    return jsonable_encoder(result)


@router.post("/{deliverable_id}/add-to-asset-library")
def add_photoshoot_to_asset_library(deliverable_id: str):
    creator_id = int(_creator_profile()["id"])
    try:
        row = _service().add_to_asset_library(deliverable_id, creator_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Completed Photoshoot not found.")
    except (ValueError, RuntimeError) as error:
        raise HTTPException(status_code=409, detail=str(error))
    return jsonable_encoder(_payload(row))
