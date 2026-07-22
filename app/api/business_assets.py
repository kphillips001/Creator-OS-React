"""Read-only Business Asset Console HTTP adapter for React."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from fastapi.encoders import jsonable_encoder

from app.api.asset_library import _creator_profile
from app.models.chat_commerce_inventory import ChatCommerceInventoryFilter
from app.repositories.commerce_destination_repository import CommerceDestinationRepository
from app.repositories.commerce_registration_repository import CommerceRegistrationRepository
from app.repositories.content_intelligence_repository import ContentIntelligenceProfileRepository
from app.repositories.asset_intelligence_repository import AssetIntelligenceRepository
from app.repositories.photoshoot_commerce_repository import PhotoshootCommerceRepository
from app.services.asset_library_service import AssetLibraryService
from app.services.chat_commerce_inventory_service import ChatCommerceInventoryService
from app.services.chat_commerce_registration_service import ChatCommerceRegistrationService
from app.services.commerce_registration_service import CommerceRegistrationService
from app.services.fulfillment_registration_service import FulfillmentRegistrationService


router = APIRouter(prefix="/api/v1/business-assets", tags=["business-assets"])

_ANALYSIS_STAGES = ("NUDENET", "VISION", "GROK", "CONTENT_INTELLIGENCE")


def _inventory_service() -> ChatCommerceInventoryService:
    return ChatCommerceInventoryService()


def _commerce_repository() -> CommerceRegistrationRepository:
    return CommerceRegistrationRepository()


def _commerce_service() -> CommerceRegistrationService:
    return CommerceRegistrationService()


def _content_intelligence_repository() -> ContentIntelligenceProfileRepository:
    return ContentIntelligenceProfileRepository()


def _asset_intelligence_repository() -> AssetIntelligenceRepository:
    return AssetIntelligenceRepository()


def _destination_repository() -> CommerceDestinationRepository:
    return CommerceDestinationRepository()


def _fulfillment_service() -> FulfillmentRegistrationService:
    return FulfillmentRegistrationService()


def _chat_service() -> ChatCommerceRegistrationService:
    return ChatCommerceRegistrationService()


def _asset_library_service() -> AssetLibraryService:
    return AssetLibraryService()


def _photoshoot_repository() -> PhotoshootCommerceRepository:
    return PhotoshootCommerceRepository()


def _photoshoot_payload(row: dict[str, Any]) -> dict[str, Any]:
    stage = str(row.get("workflow_stage") or "PENDING")
    ready = stage == "READY"
    failed = stage.endswith("_FAILED")
    return {
        "asset_id": int(row.get("hero_asset_id") or 0), "itemKind": "photoshoot",
        "deliverableId": str(row["deliverable_id"]), "asset_name": row.get("display_title") or row["display_name"],
        "description": row.get("display_description"),
        "imageUrl": f'/api/v1/assets/{row["hero_asset_id"]}/media' if row.get("hero_asset_id") else "",
        "analysisStatus": "COMPLETE" if ready else "FAILED" if failed else "ANALYZING",
        "downstreamStatus": "ANALYSIS_READY" if ready else "ANALYSIS_FAILED" if failed else "ANALYSIS_PENDING",
        "commerceStatus": "Ready" if ready else "Analysis Failed" if failed else "Analyzing",
        "current_lifecycle": "PHOTOSHOOT_READY" if ready else "ANALYSIS_FAILED" if failed else "INTELLIGENCE_PENDING",
        "shotCount": int(row["shot_count"]), "source_workflow": "photoshoot", "chat_ready": False,
        "fulfillment_ready": False, "recommendation_ready": ready, "waiting_for_media_link": False,
        "awaiting_destination": False, "blocked": failed,
    }


def _context(value: Any) -> Any:
    if value is None:
        return None
    to_context = getattr(value, "to_context", None)
    if callable(to_context):
        return jsonable_encoder(to_context())
    if is_dataclass(value):
        return jsonable_encoder(asdict(value))
    return jsonable_encoder(value)


def _owned_record(asset_id: int, creator_profile_id: int):
    record = _commerce_repository().get_by_asset_id(int(asset_id))
    if record is None or int(record.creator_profile_id or 0) != creator_profile_id:
        raise HTTPException(status_code=404, detail="Business Asset not found.")
    return record


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").strip().upper()


def _analysis_stages(status: Any) -> dict[str, str]:
    """Project the canonical sequential analysis state without dispatching work."""
    normalized = _enum_value(status) or "PENDING"
    stages = {stage: "PENDING" for stage in _ANALYSIS_STAGES}
    if normalized in {"READY", "COMPLETE"}:
        return {stage: "COMPLETE" for stage in _ANALYSIS_STAGES}
    if normalized in {"FAILED", "PARTIAL"}:
        stages["CONTENT_INTELLIGENCE"] = normalized
        return stages

    for index, stage in enumerate(_ANALYSIS_STAGES):
        if normalized.startswith(f"{stage}_"):
            state = normalized.removeprefix(f"{stage}_")
            for completed in _ANALYSIS_STAGES[:index]:
                stages[completed] = "COMPLETE"
            stages[stage] = state
            return stages
    return stages


def _populated(mapping: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in mapping.items()
        if value is not None and value != "" and value != [] and value != () and value != {}
    }


def _first(mapping: dict[str, Any], *keys: str) -> Any:
    return next((mapping[key] for key in keys if key in mapping and mapping[key] not in (None, "", [], (), {})), None)


def _analysis_results(asset_id: int, intelligence: Any | None) -> dict[str, dict[str, Any]]:
    """Whitelist normalized analysis values for the read-only Commerce panel."""
    latest: dict[str, Any] = {}
    for result in _asset_intelligence_repository().list_provider_results(asset_id):
        stage = _enum_value(getattr(result, "metadata", {}).get("stage"))
        key = (
            "NUDENET" if result.provider == "nudenet" or stage == "NUDENET"
            else "VISION" if result.provider == "gpt-vision" or stage == "VISION"
            else "GROK" if result.provider == "grok-vision" or stage == "GROK"
            else None
        )
        if key:
            latest[key] = result

    context = _context(intelligence) or {}
    content = dict(context.get("content_profile") or {})
    normalized = dict(context.get("normalized_context") or {})
    safety = dict(content.get("ai_metadata", {}).get("safety") or {})
    semantic = dict(content.get("ai_metadata", {}).get("semantic") or {})

    def provider(stage: str, fields: dict[str, Any]) -> dict[str, Any]:
        result = latest.get(stage)
        values = dict(getattr(result, "normalized_fields", {}) or {})
        confidence = dict(getattr(result, "field_confidence", {}) or {})
        return _populated({
            "status": _enum_value(getattr(result, "status", None)) or None,
            "providerVersion": getattr(result, "provider_version", None),
            **{key: value(values, confidence) if callable(value) else value for key, value in fields.items()},
        })

    nudenet = provider("NUDENET", {
        "classification": lambda values, _: _first(values, "safety_classification", "classification"),
        "confidence": lambda _, confidence: _first(safety, "confidence") or _first(confidence, "safety_classification"),
        "detectedCategories": lambda values, _: _first(values, "detected_categories", "keywords"),
        "explicitScores": lambda values, _: _first(values, "explicit_scores", "category_scores"),
    })
    vision = provider("VISION", {
        "shortDescription": lambda values, _: _first(values, "short_description"),
        "scene": lambda values, _: _first(values, "scene", "setting"),
        "objects": lambda values, _: _first(values, "objects", "detected_objects"),
        "people": lambda values, _: _first(values, "people", "subjects"),
        "environment": lambda values, _: _first(values, "environment"),
        "lighting": lambda values, _: _first(values, "lighting"),
        "composition": lambda values, _: _first(values, "composition", "camera_framing"),
        "tags": lambda values, _: _first(values, "tags"),
    })
    grok = provider("GROK", {
        "mood": lambda values, _: _first(values, "mood"),
        "theme": lambda values, _: _first(values, "themes", "theme"),
        "visualStyle": lambda values, _: _first(values, "visual_style"),
        "lifestyleContext": lambda values, _: _first(values, "lifestyle_context"),
        "suggestedCollections": lambda values, _: _first(values, "suggested_collections"),
        "searchPhrases": lambda values, _: _first(values, "search_phrases"),
        "semanticSummary": lambda values, _: _first(values, "content_summary", "short_description"),
    })
    merged = _populated({
        "status": context.get("status"),
        "commerceClassification": _first(content, "commerce_classification", "classification"),
        "assetCategory": _first(content, "asset_category", "category"),
        "suggestedCollections": _first(content, "suggested_collections") or semantic.get("suggested_collections"),
        "recommendedProducts": _first(content, "recommended_products", "product_recommendations"),
        "suggestedPricingTier": _first(content, "suggested_pricing_tier", "pricing_tier"),
        "contentRating": _first(content, "content_rating") or _first(safety, "safety_classification", "nudity_level"),
        "searchKeywords": _first(content, "search_keywords", "keywords") or normalized.get("keywords"),
        "decisionEngineSummary": _first(content, "decision_engine_summary", "summary"),
    })
    return {"NUDENET": nudenet, "VISION": vision, "GROK": grok, "CONTENT_INTELLIGENCE": merged}


def _commerce_status(item: Any, business_asset: Any | None) -> str:
    analysis_status = _enum_value(
        getattr(business_asset, "content_intelligence_status", None)
    )
    if analysis_status.endswith("_FAILED") or analysis_status == "FAILED":
        return "Analysis Failed"
    if bool(getattr(item, "chat_ready", False)):
        return "Chat Ready"
    if bool(getattr(item, "waiting_for_media_link", False)):
        return "Needs Media Link"
    lifecycle = _enum_value(getattr(item, "current_lifecycle", None))
    if lifecycle in {"AWAITING_UPLOAD", "PUBLISHING_READY"}:
        return "Needs Upload"
    if not bool(getattr(business_asset, "content_intelligence_ready", False)):
        return "Analyzing"
    return "Ready"


def _item_payload(item: Any, business_asset: Any | None = None) -> dict[str, Any]:
    payload = _context(item)
    payload["imageUrl"] = f"/api/v1/assets/{int(item.asset_id)}/media"
    if business_asset is not None:
        payload["analysisStatus"] = getattr(
            business_asset, "content_intelligence_status", "PENDING"
        )
    payload["commerceStatus"] = _commerce_status(item, business_asset)
    if _commerce_status(item, business_asset) == "Analysis Failed":
        payload["downstreamStatus"] = "ANALYSIS_FAILED"
    elif bool(getattr(item, "chat_ready", False)):
        payload["downstreamStatus"] = "CHAT_INVENTORY_READY"
    elif bool(getattr(item, "awaiting_destination", False)):
        payload["downstreamStatus"] = "AWAITING_DESTINATION"
    elif bool(getattr(item, "waiting_for_media_link", False)):
        payload["downstreamStatus"] = "AWAITING_FULFILLMENT"
    elif bool(getattr(item, "blocked", False)):
        payload["downstreamStatus"] = "CHAT_REGISTRATION_BLOCKED"
    elif getattr(business_asset, "content_intelligence_ready", False):
        payload["downstreamStatus"] = "ANALYSIS_READY"
    else:
        payload["downstreamStatus"] = "ANALYSIS_PENDING"
    return payload


@router.get("")
def list_business_assets(
    search: str | None = None,
    status: str | None = None,
    destination: str | None = None,
    source_workflow: str | None = None,
    chat_ready: bool | None = None,
    fulfillment_ready: bool | None = None,
    recommendation_ready: bool | None = None,
    awaiting_destination: bool | None = None,
    waiting_for_media_link: bool | None = None,
    blocked: bool | None = None,
    commerce_status: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
):
    creator_profile_id = int(_creator_profile()["id"])
    service = _inventory_service()
    result = service.build_inventory(
        filters=ChatCommerceInventoryFilter(
            status=str(status or "").strip() or None,
            destination=str(destination or "").strip() or None,
            source_workflow=str(source_workflow or "").strip() or None,
            chat_ready=chat_ready,
            fulfillment_ready=fulfillment_ready,
            recommendation_ready=recommendation_ready,
            awaiting_destination=awaiting_destination,
            waiting_for_media_link=waiting_for_media_link,
            blocked=blocked,
        ),
        limit=5000,
    )
    records = _commerce_repository()
    items = [
        item
        for item in result.items
        if (
            (record := records.get_by_asset_id(int(item.asset_id))) is not None
            and int(record.creator_profile_id or 0) == creator_profile_id
        )
    ]
    needle = str(search or "").strip().lower()
    if needle:
        items = [
            item for item in items
            if needle in str(item.asset_name or "").lower()
            or needle in str(item.asset_id)
        ]
    requested_commerce_status = str(commerce_status or "").strip().lower()
    if requested_commerce_status:
        items = [
            item for item in items
            if _commerce_status(
                item, records.get_by_asset_id(int(item.asset_id))
            ).lower() == requested_commerce_status
        ]
    payloads = [_item_payload(item, records.get_by_asset_id(int(item.asset_id))) for item in items]
    photoshoots = [_photoshoot_payload(row) for row in _photoshoot_repository().list_active(creator_profile_id)]
    if needle:
        photoshoots = [item for item in photoshoots if needle in str(item["asset_name"]).lower()]
    if requested_commerce_status:
        photoshoots = [item for item in photoshoots if str(item["commerceStatus"]).lower() == requested_commerce_status]
    combined = payloads + photoshoots
    summary = service.summarize_items(items)
    total = len(combined)
    total_pages = max(1, (total + page_size - 1) // page_size)
    current_page = min(page, total_pages)
    start = (current_page - 1) * page_size
    return {
        "items": [
            item for item in combined[start:start + page_size]
        ],
        "summary": _context(summary),
        "total": total,
        "page": current_page,
        "pageSize": page_size,
        "totalPages": total_pages,
        "generatedAt": result.generated_at,
    }


@router.get("/photoshoots/{deliverable_id}")
def photoshoot_business_details(deliverable_id: str):
    creator_id = int(_creator_profile()["id"])
    repo = _photoshoot_repository()
    row = repo.get(deliverable_id)
    if row is None or int(row["creator_profile_id"]) != creator_id or not row["is_active"]:
        raise HTTPException(status_code=404, detail="Photoshoot Commerce Deliverable not found.")
    return jsonable_encoder({
        "item": _photoshoot_payload(row), "photoshootIntelligence": row.get("intelligence_profile") or {},
        "members": [{"assetId": member["asset_id"], "shotOrder": member["shot_order"],
                     "imageUrl": f'/api/v1/assets/{member["asset_id"]}/media'}
                    for member in repo.members(row["photoshoot_session_id"])],
        "commerceStatus": row["commerce_status"],
        "technical": {"deliverableId": str(row["deliverable_id"]),
                      "sessionId": row["photoshoot_session_id"], "heroAssetId": row["hero_asset_id"]},
    })


@router.post("/photoshoots/{deliverable_id}/archive")
def archive_photoshoot_business_asset(deliverable_id: str):
    creator_id = int(_creator_profile()["id"])
    repo = _photoshoot_repository()
    row = repo.get(deliverable_id)
    if row is None or int(row["creator_profile_id"]) != creator_id:
        raise HTTPException(status_code=404, detail="Photoshoot Commerce Deliverable not found.")
    archived = repo.archive(deliverable_id)
    return {"deliverableId": deliverable_id, "isArchived": bool(archived["is_archived"]), "archivedAt": archived["archived_at"]}


@router.get("/{asset_id}")
def business_asset_details(asset_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    business_asset = _owned_record(asset_id, creator_profile_id)
    inventory = _inventory_service().build_inventory(limit=5000)
    item = next((candidate for candidate in inventory.items if candidate.asset_id == asset_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Business Asset not found.")

    asset = _asset_library_service().get_asset_details(asset_id)
    if asset is None or int(asset.creator_profile_id or 0) != creator_profile_id:
        raise HTTPException(status_code=404, detail="Business Asset not found.")

    intelligence = _content_intelligence_repository().get_by_asset_id(asset_id)
    destinations = _destination_repository()
    fulfillment = _fulfillment_service().get_fulfillment_by_asset_id(asset_id)
    chat = _chat_service().get_by_asset_id(asset_id)
    return {
        "item": _item_payload(item, business_asset),
        "asset": {
            "assetId": asset_id,
            "fileName": asset.item.file_name,
            "mediaType": asset.item.media_type,
            "classification": asset.item.classification,
            "status": asset.item.status,
            "createdAt": asset.item.created_at,
            "tags": list(asset.item.tags),
            "themes": list(asset.item.themes),
            "imageUrl": f"/api/v1/assets/{asset_id}/media",
        },
        "contentIntelligence": _context(intelligence),
        "analysis": _analysis_stages(
            getattr(business_asset, "content_intelligence_status", "PENDING")
        ),
        "analysisResults": _analysis_results(asset_id, intelligence),
        "commerceRegistration": _context(business_asset),
        "destination": {
            "history": [_context(entry) for entry in destinations.list_history(asset_id)],
            "routingIntents": [_context(intent) for intent in destinations.list_routing_intents(asset_id)],
        },
        "fulfillment": _context(fulfillment),
        "chatCommerce": _context(chat),
    }


@router.post("/{asset_id}/archive")
def archive_business_asset(asset_id: int):
    creator_profile_id = int(_creator_profile()["id"])
    _owned_record(asset_id, creator_profile_id)
    archived = _commerce_service().archive_asset(asset_id)
    if archived is None:
        raise HTTPException(status_code=404, detail="Business Asset not found.")
    return {
        "assetId": int(asset_id),
        "isArchived": bool(archived.is_archived),
        "archivedAt": archived.archived_at,
    }
