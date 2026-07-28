from datetime import datetime, timezone
from uuid import UUID

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import recommendation_diagnostics as api
from app.models.commerce_learning import (
    CommerceRecommendationOutcome,
    CommerceRecommendationOutcomeType,
)


NOW = datetime(2026, 7, 25, tzinfo=timezone.utc)
OUTCOME = UUID("10000000-0000-0000-0000-000000000001")


def item():
    return CommerceRecommendationOutcome(
        outcome_id=OUTCOME, creator_profile_id=2, fanvue_account_id=7,
        external_fanvue_user_uuid=UUID(
            "20000000-0000-0000-0000-000000000001"
        ),
        telegram_user_id=22,
        commercial_offering_id=UUID(
            "30000000-0000-0000-0000-000000000001"
        ),
        purchase_intent_id=None,
        outcome_type=CommerceRecommendationOutcomeType.PURCHASED,
        observed_at=NOW, source_event_key="purchase:1",
        evidence={"themes": ["beach"], "access_token": "never"},
        recommendation_trace={
            "recommendationEngineVersion":
                "commerce_recommendation_v2_intelligent",
            "candidateCount": 2, "eligibleCount": 2, "rejectedCount": 1,
            "activeIntentApplied": False,
            "authorization": "never",
            "rankedCandidates": [{
                "rank": 1, "offeringId": "offering-1",
                "title": "Beach Set", "selected": True,
                "finalScore": 0.843, "reason": "Best deterministic score.",
                "components": [],
            }],
        },
    )


class Repository:
    def list_recommendation_outcomes(self, **kwargs):
        assert kwargs["limit"] <= 100
        return (item(),), 1

    def diagnostics_statistics(self, **_kwargs):
        return {
            "outcomes": 1, "purchases": 1, "ignoredExpired": 0,
            "profiles": 1, "latest": NOW,
        }

    def get_outcome(self, outcome_id, **_kwargs):
        return item() if outcome_id == OUTCOME else None

    def get_diagnostic_context(self, *_args, **_kwargs):
        return {
            "purchase_intent_status": "PURCHASED",
            "attribution_result": "ATTRIBUTED",
            "preferences": {"themes": {"beach": {"score": 1.0}}},
            "outcome_counts": {"PURCHASED": 1},
            "confidence": 0.5, "evidence_count": 1,
            "profile_updated_at": NOW,
        }


def test_diagnostics_are_bounded_redacted_scoped_and_protected(monkeypatch):
    monkeypatch.setattr(api, "_creator_profile", lambda: {"id": 2})
    monkeypatch.setattr(api, "CommerceLearningRepository", Repository)
    application = FastAPI()
    application.include_router(api.router)
    client = TestClient(application)

    assert client.get("/api/v1/developer/recommendations").status_code == 403
    headers = {"X-Creator-OS-Developer": "true"}
    response = client.get(
        "/api/v1/developer/recommendations?page_size=500",
        headers=headers,
    )
    assert response.status_code == 422
    response = client.get(
        "/api/v1/developer/recommendations?page_size=50",
        headers=headers,
    )
    body = response.json()
    assert body["items"][0]["buyer"].startswith("buyer-")
    assert "20000000-" not in str(body)
    assert "access_token" not in str(body)
    assert "authorization" not in str(body)
    assert body["items"][0]["selectedScore"] == 0.843
    assert client.get(
        f"/api/v1/developer/recommendations/{OUTCOME}", headers=headers
    ).json()["currentLearningProfile"]["snapshotType"] == "CURRENT_PROFILE"
    assert client.get(
        "/api/v1/developer/recommendations/"
        "90000000-0000-0000-0000-000000000001",
        headers=headers,
    ).status_code == 404
