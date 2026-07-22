"""Read-only Photoshoot Gallery projection for completed commerce sets."""

from fastapi import APIRouter, HTTPException
from fastapi.encoders import jsonable_encoder

from app.api.asset_library import _creator_profile
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


router = APIRouter(prefix="/api/v1/photoshoot-gallery", tags=["photoshoot-gallery"])


def _repository():
    return PhotoshootCommerceRepository()


def _service():
    return PhotoshootCommerceDeliverableService(repository=_repository())


def _payload(row):
    return {
        "deliverableId": str(row["deliverable_id"]),
        "sessionId": row["photoshoot_session_id"],
        "name": row.get("display_title") or row["display_name"],
        "description": row.get("display_description"),
        "completedAt": row["completed_at"],
        "shotCount": int(row["shot_count"]),
        "heroAssetId": row["hero_asset_id"],
        "imageUrl": f'/api/v1/assets/{row["hero_asset_id"]}/media' if row["hero_asset_id"] else None,
        "intelligenceStatus": row["intelligence_status"],
        "registrationState": row["registration_state"],
    }


@router.get("")
def list_photoshoots():
    creator_id = int(_creator_profile()["id"])
    return {"items": jsonable_encoder([_payload(row) for row in _repository().list_gallery(creator_id)])}


@router.get("/{deliverable_id}")
def photoshoot_details(deliverable_id: str):
    creator_id = int(_creator_profile()["id"])
    repo = _repository()
    row = repo.get(deliverable_id)
    if row is None or int(row["creator_profile_id"]) != creator_id or not row["is_active"]:
        raise HTTPException(status_code=404, detail="Photoshoot not found.")
    item = _payload(row)
    item["intelligence"] = row.get("intelligence_profile") or {}
    item["technical"] = {
        "deliverableId": str(row["deliverable_id"]),
        "sessionId": row["photoshoot_session_id"],
        "heroAssetId": row["hero_asset_id"],
        "galleryPath": row["gallery_path"],
    }
    item["members"] = [
        {"assetId": member["asset_id"], "shotOrder": member["shot_order"],
         "isHero": member["is_hero"], "imageUrl": f'/api/v1/assets/{member["asset_id"]}/media'}
        for member in repo.members(row["photoshoot_session_id"])
    ]
    return jsonable_encoder(item)


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
