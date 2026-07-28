"""Protected, read-only Recommendation Engine diagnostics."""

from datetime import datetime
from hashlib import sha256
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.api.asset_library import _creator_profile
from app.api.developer_authorization import require_developer_authorization
from app.repositories.commerce_learning_repository import (
    CommerceLearningRepository,
)


router = APIRouter(
    prefix="/api/v1/developer/recommendations",
    tags=["developer-recommendation-diagnostics"],
    dependencies=[Depends(require_developer_authorization)],
)

_BLOCKED_KEYS = {
    "access_token", "refresh_token", "authorization", "cookie",
    "client_secret", "telegram_session", "signature",
}


def _safe_buyer(value: UUID) -> str:
    digest = sha256(str(value).encode("utf-8")).hexdigest()[:10]
    return f"buyer-{digest}"


def _sanitize(value):
    if isinstance(value, dict):
        return {
            str(key): _sanitize(item)
            for key, item in value.items()
            if str(key).lower() not in _BLOCKED_KEYS
        }
    if isinstance(value, (list, tuple)):
        return [_sanitize(item) for item in value[:100]]
    if isinstance(value, str):
        return value[:1000]
    return value


def _outcome(item):
    trace = _sanitize(dict(item.recommendation_trace))
    ranked = trace.get("rankedCandidates", [])
    selected = next((
        candidate for candidate in ranked
        if isinstance(candidate, dict) and candidate.get("selected")
    ), None)
    return {
        "outcomeId": str(item.outcome_id),
        "timestamp": item.observed_at.isoformat(),
        "buyer": _safe_buyer(item.external_fanvue_user_uuid),
        "offeringId": str(item.commercial_offering_id),
        "purchaseIntentId": (
            str(item.purchase_intent_id) if item.purchase_intent_id else None
        ),
        "outcome": item.outcome_type.value,
        "engineVersion": trace.get("recommendationEngineVersion"),
        "activeIntentOverride": bool(trace.get("activeIntentApplied")),
        "candidateCount": trace.get("candidateCount"),
        "eligibleCount": trace.get("eligibleCount"),
        "rejectedCount": trace.get("rejectedCount"),
        "selectedScore": selected.get("finalScore") if selected else None,
        "selectedTitle": selected.get("title") if selected else None,
        "explanation": (
            selected.get("reason") if selected
            else trace.get("recommendationSummary")
        ),
        "trace": trace,
        "evidence": _sanitize(dict(item.evidence)),
    }


@router.get("")
def list_recommendations(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100),
    outcome: str | None = None,
    engine_version: str | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
):
    creator_id = int(_creator_profile()["id"])
    repository = CommerceLearningRepository()
    items, total = repository.list_recommendation_outcomes(
        creator_profile_id=creator_id,
        limit=page_size,
        offset=(page - 1) * page_size,
        outcome_type=outcome,
        engine_version=engine_version,
        date_from=date_from,
        date_to=date_to,
    )
    statistics = repository.diagnostics_statistics(
        creator_profile_id=creator_id
    )
    return {
        "items": [_outcome(item) for item in items],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "statistics": {
            **statistics,
            "latest": (
                statistics["latest"].isoformat()
                if statistics["latest"] else None
            ),
        },
    }


@router.get("/{outcome_id}")
def get_recommendation(outcome_id: UUID):
    creator_id = int(_creator_profile()["id"])
    repository = CommerceLearningRepository()
    item = repository.get_outcome(
        outcome_id, creator_profile_id=creator_id
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Recommendation not found.")
    context = repository.get_diagnostic_context(
        outcome_id, creator_profile_id=creator_id
    )
    profile_updated = context.get("profile_updated_at")
    return {
        **_outcome(item),
        "purchaseIntent": {
            "status": context.get("purchase_intent_status"),
            "attribution": context.get("attribution_result"),
        },
        "currentLearningProfile": (
            {
                "preferences": context.get("preferences") or {},
                "outcomeCounts": context.get("outcome_counts") or {},
                "preferredOfferingType": context.get(
                    "preferred_offering_type"
                ),
                "preferredPriceMinMinor": context.get(
                    "preferred_price_min_minor"
                ),
                "preferredPriceMaxMinor": context.get(
                    "preferred_price_max_minor"
                ),
                "repeatPurchaseFrequency": context.get(
                    "repeat_purchase_frequency"
                ),
                "confidence": context.get("confidence"),
                "evidenceCount": context.get("evidence_count"),
                "updatedAt": (
                    profile_updated.isoformat() if profile_updated else None
                ),
                "snapshotType": "CURRENT_PROFILE",
            }
            if context.get("preferences") is not None else None
        ),
    }
