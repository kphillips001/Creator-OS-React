"""Developer-only read diagnostics for observed Commerce learning."""

from uuid import UUID
from hashlib import sha256
from fastapi import APIRouter, Depends, HTTPException

from app.api.asset_library import _creator_profile
from app.api.developer_authorization import require_developer_authorization
from app.repositories.commerce_learning_repository import CommerceLearningRepository


router = APIRouter(
    prefix="/api/v1/developer/commerce-learning",
    tags=["developer-commerce-learning"],
    dependencies=[Depends(require_developer_authorization)],
)


def _profile(item):
    return {
        "learningProfileId": str(item.learning_profile_id),
        "buyerUuid": str(item.external_fanvue_user_uuid),
        "buyerSafeId": (
            "buyer-"
            + sha256(str(item.external_fanvue_user_uuid).encode()).hexdigest()[:10]
        ),
        "telegramUserId": item.telegram_user_id,
        "preferences": dict(item.preferences),
        "outcomeCounts": dict(item.outcome_counts),
        "preferredOfferingType": item.preferred_offering_type,
        "favoriteMediaType": item.favorite_media_type,
        "averagePriceMinor": item.average_price_minor,
        "preferredPriceMinMinor": item.preferred_price_min_minor,
        "preferredPriceMaxMinor": item.preferred_price_max_minor,
        "repeatPurchaseFrequency": item.repeat_purchase_frequency,
        "averagePurchaseIntervalDays": item.average_purchase_interval_days,
        "confidence": item.confidence,
        "evidenceCount": item.evidence_count,
        "lastObservedAt": (
            item.last_observed_at.isoformat() if item.last_observed_at else None
        ),
        "updatedAt": item.updated_at.isoformat(),
    }


@router.get("")
def list_learning_profiles(limit: int = 100):
    items = CommerceLearningRepository().list_profiles(
        creator_profile_id=int(_creator_profile()["id"]),
        limit=min(500, max(1, limit)),
    )
    return {"items": [_profile(item) for item in items], "total": len(items)}


@router.get("/outcomes")
def list_learning_outcomes(
    page: int = 1, page_size: int = 25, outcome: str | None = None,
):
    items, total = CommerceLearningRepository().list_recommendation_outcomes(
        creator_profile_id=int(_creator_profile()["id"]),
        limit=min(100, max(1, page_size)),
        offset=(max(1, page) - 1) * min(100, max(1, page_size)),
        outcome_type=outcome,
    )
    return {
        "items": [
            {
                "outcomeId": str(item.outcome_id),
                "offeringId": str(item.commercial_offering_id),
                "purchaseIntentId": (
                    str(item.purchase_intent_id)
                    if item.purchase_intent_id else None
                ),
                "outcomeType": item.outcome_type.value,
                "observedAt": item.observed_at.isoformat(),
                "evidence": dict(item.evidence),
                "recommendationTrace": dict(item.recommendation_trace),
            }
            for item in items
        ],
        "total": total,
        "page": max(1, page),
        "pageSize": min(100, max(1, page_size)),
    }


@router.get("/outcomes/{outcome_id}")
def get_learning_outcome(outcome_id: UUID):
    item = CommerceLearningRepository().get_outcome(
        outcome_id,
        creator_profile_id=int(_creator_profile()["id"]),
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Learning outcome not found.")
    return {
        "outcomeId": str(item.outcome_id),
        "offeringId": str(item.commercial_offering_id),
        "outcomeType": item.outcome_type.value,
        "observedAt": item.observed_at.isoformat(),
        "evidence": dict(item.evidence),
        "recommendationTrace": dict(item.recommendation_trace),
    }


@router.get("/{buyer_uuid}")
def get_learning_profile(buyer_uuid: UUID):
    repository = CommerceLearningRepository()
    matches = [
        item for item in repository.list_profiles(
            creator_profile_id=int(_creator_profile()["id"]), limit=500
        )
        if item.external_fanvue_user_uuid == buyer_uuid
    ]
    if not matches:
        raise HTTPException(status_code=404, detail="Commerce learning profile not found.")
    item = matches[0]
    outcomes = repository.list_outcomes(
        creator_profile_id=item.creator_profile_id,
        fanvue_account_id=item.fanvue_account_id,
        external_fanvue_user_uuid=item.external_fanvue_user_uuid,
        limit=100,
    )
    return {
        **_profile(item),
        "recentOutcomes": [
            {
                "outcomeId": str(outcome.outcome_id),
                "offeringId": str(outcome.commercial_offering_id),
                "purchaseIntentId": (
                    str(outcome.purchase_intent_id)
                    if outcome.purchase_intent_id else None
                ),
                "outcomeType": outcome.outcome_type.value,
                "observedAt": outcome.observed_at.isoformat(),
                "evidence": dict(outcome.evidence),
                "recommendationTrace": dict(outcome.recommendation_trace),
            }
            for outcome in reversed(outcomes)
        ],
    }
