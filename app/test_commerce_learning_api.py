from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import commerce_learning as api
from app.models.commerce_learning import (
    CommerceRecommendationOutcome,
    CommerceRecommendationOutcomeType,
    CustomerCommerceLearningProfile,
)


NOW = datetime(2026, 7, 25, 12, tzinfo=timezone.utc)
BUYER = UUID("10000000-0000-0000-0000-000000000001")
OFFERING = UUID("20000000-0000-0000-0000-000000000001")
PROFILE_ID = UUID("30000000-0000-0000-0000-000000000001")
OUTCOME_ID = UUID("40000000-0000-0000-0000-000000000001")


def profile():
    return CustomerCommerceLearningProfile(
        learning_profile_id=PROFILE_ID,
        creator_profile_id=2,
        fanvue_account_id=7,
        external_fanvue_user_uuid=BUYER,
        telegram_user_id=22,
        preferences={"themes": {"beach": {"score": 1.0}}},
        outcome_counts={"PURCHASED": 1},
        preferred_offering_type="PHOTOSET",
        favorite_media_type="PHOTOSET",
        average_price_minor=999,
        preferred_price_min_minor=999,
        preferred_price_max_minor=999,
        repeat_purchase_frequency=0,
        average_purchase_interval_days=None,
        confidence=0.1,
        evidence_count=1,
        last_observed_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class Repository:
    def list_profiles(self, **_kwargs):
        return (profile(),)

    def list_outcomes(self, **_kwargs):
        return (CommerceRecommendationOutcome(
            outcome_id=OUTCOME_ID,
            creator_profile_id=2,
            fanvue_account_id=7,
            external_fanvue_user_uuid=BUYER,
            telegram_user_id=22,
            commercial_offering_id=OFFERING,
            purchase_intent_id=None,
            outcome_type=CommerceRecommendationOutcomeType.PURCHASED,
            observed_at=NOW,
            source_event_key="purchase:1",
            evidence={"themes": ["beach"]},
            recommendation_trace={"engineVersion": "v2"},
        ),)


def test_read_only_learning_diagnostics_are_developer_protected(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    monkeypatch.setattr(api, "CommerceLearningRepository", Repository)
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)

    assert client.get("/api/v1/developer/commerce-learning").status_code == 403
    headers = {"X-Creator-OS-Developer": "true"}
    listing = client.get(
        "/api/v1/developer/commerce-learning", headers=headers
    )
    detail = client.get(
        f"/api/v1/developer/commerce-learning/{BUYER}", headers=headers
    )

    assert listing.status_code == 200
    assert listing.json()["items"][0]["preferredOfferingType"] == "PHOTOSET"
    assert detail.status_code == 200
    assert detail.json()["recentOutcomes"][0]["outcomeType"] == "PURCHASED"
    assert detail.json()["recentOutcomes"][0]["recommendationTrace"] == {
        "engineVersion": "v2",
    }
