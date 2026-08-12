from datetime import datetime, timezone

import pytest

from app.models.asset_intelligence import (
    ASSET_INTELLIGENCE_SCHEMA_VERSION,
    AssetIntelligenceProfile,
    AssetIntelligenceProviderResult,
    AssetIntelligenceStatus,
)
from app.services.asset_intelligence_merger import AssetIntelligenceMerger
from app.services.asset_intelligence_service import AssetIntelligenceService


class FakeRepository:
    def __init__(self):
        self.profiles = {}
        self.results = {}

    def get_profile(self, asset_id):
        return self.profiles.get(asset_id)

    def upsert_profile(self, profile):
        self.profiles[profile.asset_id] = profile
        return profile

    def save_provider_result(self, result):
        self.results[result.result_id] = result
        return result

    def list_provider_results(self, asset_id):
        return tuple(
            result for result in self.results.values()
            if result.asset_id == asset_id
        )


def test_initialize_pending_is_one_profile_per_asset_and_idempotent():
    repository = FakeRepository()
    service = AssetIntelligenceService(repository=repository)

    first = service.initialize_pending(asset_id=10, creator_profile_id=2)
    second = service.initialize_pending(asset_id=10, creator_profile_id=2)

    assert first is second
    assert first.analysis_status == AssetIntelligenceStatus.PENDING
    assert first.schema_version == ASSET_INTELLIGENCE_SCHEMA_VERSION
    assert len(repository.profiles) == 1


def test_initialize_pending_rejects_creator_ownership_mismatch():
    service = AssetIntelligenceService(repository=FakeRepository())
    service.initialize_pending(asset_id=10, creator_profile_id=2)

    with pytest.raises(ValueError, match="ownership mismatch"):
        service.initialize_pending(asset_id=10, creator_profile_id=3)


def test_merger_selects_highest_confidence_normalized_fields_only():
    profile = AssetIntelligenceProfile(asset_id=10, creator_profile_id=2)
    analyzed_at = datetime.now(timezone.utc)
    results = (
        AssetIntelligenceProviderResult(
            asset_id=10,
            creator_profile_id=2,
            provider="provider-a",
            raw_response={"private": "raw-a"},
            normalized_fields={"title": "First", "tags": ["portrait"]},
            field_confidence={"title": 0.7, "tags": 0.8},
            analyzed_at=analyzed_at,
        ),
        AssetIntelligenceProviderResult(
            asset_id=10,
            creator_profile_id=2,
            provider="provider-b",
            raw_response={"private": "raw-b"},
            normalized_fields={"title": "Second", "unknown_field": "ignored"},
            field_confidence={"title": 0.95, "unknown_field": 1.0},
            analyzed_at=analyzed_at,
        ),
    )

    merged = AssetIntelligenceMerger().merge(profile, results)

    assert merged.analysis_status == AssetIntelligenceStatus.READY
    assert merged.title == "Second"
    assert merged.tags == ("portrait",)
    assert not hasattr(merged, "unknown_field")
    assert "private" not in merged.to_payload()
    assert merged.provider_agreement["title"]["selected_provider"] == "provider-b"


def test_service_records_provider_output_separately_then_merges():
    repository = FakeRepository()
    service = AssetIntelligenceService(repository=repository)
    service.initialize_pending(asset_id=10, creator_profile_id=2)
    service.begin_analysis(10)
    raw = {"provider_specific": [1, 2, 3]}
    result = AssetIntelligenceProviderResult(
        asset_id=10,
        creator_profile_id=2,
        provider="future-provider",
        raw_response=raw,
        normalized_fields={"content_summary": "Normalized summary"},
        field_confidence={"content_summary": 0.9},
    )

    service.record_provider_result(result)
    profile = service.merge_provider_results(10)

    assert repository.results[result.result_id].raw_response == raw
    assert profile.content_summary == "Normalized summary"
    assert "provider_specific" not in profile.to_payload()


def test_service_can_promote_provider_fields_without_marking_workflow_ready():
    repository = FakeRepository()
    service = AssetIntelligenceService(repository=repository)
    repository.upsert_profile(AssetIntelligenceProfile(
        asset_id=10, creator_profile_id=2,
        analysis_status=AssetIntelligenceStatus.CONTENT_INTELLIGENCE_RUNNING,
    ))
    repository.save_provider_result(AssetIntelligenceProviderResult(
        asset_id=10, creator_profile_id=2, provider="grok-vision",
        raw_response={"title": "Golden Hour Balcony Gaze"},
        normalized_fields={"title": "Golden Hour Balcony Gaze"},
        field_confidence={"title": 0.8},
    ))

    profile = service.merge_provider_results(10, preserve_analysis_status=True)

    assert profile.title == "Golden Hour Balcony Gaze"
    assert profile.analysis_status == AssetIntelligenceStatus.CONTENT_INTELLIGENCE_RUNNING


def test_phase_one_service_has_no_provider_execution_dependencies():
    import app.services.asset_intelligence_service as module

    source = open(module.__file__, encoding="utf-8").read()
    for forbidden in (
        "gpt", "grok", "nudenet", "embedding", "commerce",
        "recommendation", "publishing", "product",
    ):
        assert forbidden not in source.lower()
