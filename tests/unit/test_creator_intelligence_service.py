from datetime import datetime, timezone
from types import SimpleNamespace

from app.services.creator_intelligence_service import CreatorIntelligenceService


class Repository:
    def snapshot(self, **_kwargs):
        return {
            "active_conversations": 3, "waiting_intents": 2, "offers_today": 4,
            "purchases_today": 1, "revenue_today_minor": 999,
            "learning_events_today": 2, "learning_profiles": 1,
            "average_learning_confidence": 0.75, "top_media_type": "IMAGE",
            "top_offering_type": "PHOTOSET",
            "repeat_buyers": 1, "high_value_buyers": 0, "expired_intents": 1,
            "ignored_offers": 2, "canonical_assets": 10, "ready_assets": 8,
            "available_inventory": 5, "offerings": 1, "ready_offerings": 0,
            "ready_to_publish": 0, "live_publications": 1,
            "failed_publications": 0, "never_offered_photosets": 0,
        }


class Operations:
    def overview(self, **_kwargs):
        return {
            "overallHealth": "healthy", "healthScore": 98,
            "database": {"status": "healthy", "summary": "Connection passed"},
            "workerCounts": {"healthy": 3, "stale": 0, "failed": 0},
            "providerWarnings": [], "publishingAttention": 0,
        }


class Library:
    def list_records(self):
        return (
            SimpleNamespace(status="active"),
            SimpleNamespace(status="staged_asset_library"),
        )


def test_dashboard_is_evidence_based_and_recommends_inventory_packaging():
    service = CreatorIntelligenceService(
        repository=Repository(), operations=Operations(),
        generation_library=Library(),
        schema_manager=SimpleNamespace(certify=lambda: SimpleNamespace(
            status="PASS", missing_migrations=(),
        )),
        now=lambda: datetime(2026, 7, 25, 12, tzinfo=timezone.utc),
    )
    result = service.dashboard(creator_profile_id=1, fanvue_account_id=1)
    assert result["today"]["conversionRate"] == 25.0
    assert result["today"]["revenueMinor"] == 999
    assert result["contentPipeline"]["generationLibrary"] == 1
    assert result["recommendations"][0]["title"] == "Package available inventory"
    assert all("evidence" in item for item in result["systemHealth"])
