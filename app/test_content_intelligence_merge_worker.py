from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.asset_intelligence import AssetIntelligenceProviderResult, AssetIntelligenceStatus
from app.models.content_intelligence_profile import ContentIntelligenceProfileStatus
from app.repositories.content_intelligence_merge_job_repository import ContentIntelligenceMergeJob
from app.services.content_intelligence_merge_service import (
    CONTENT_INTELLIGENCE_MERGE_VERSION, ContentIntelligenceMergeService,
    MissingRequiredProviderResults,
)
from app.services.content_intelligence_merge_worker_service import ContentIntelligenceMergeWorkerService
from app.services.content_intelligence_service import ContentIntelligenceService


NOW = datetime(2026, 7, 20, 18, tzinfo=timezone.utc)


class Intelligence:
    def __init__(self, results): self.results = list(results)
    def list_provider_results(self, asset_id): return tuple(self.results)


class Profiles:
    def __init__(self): self.profile, self.saved = None, []
    def get_by_asset_id(self, asset_id): return self.profile
    def upsert_profile(self, profile): self.profile = profile; self.saved.append(profile); return profile


class Assets:
    def __init__(self):
        self.asset = SimpleNamespace(
            id=42, classification="LEGACY", file_name="portrait.jpg",
            media_metadata={"runtime_exists": True, "width": 1024, "height": 1536,
                            "creator_approval": {"source_workflow": "staged_asset_library_registration",
                                                 "source_item_id": "generation-1"}},
        )
    def get_by_id(self, asset_id): return self.asset if asset_id == 42 else None


def provider(name, normalized, raw, *, result_id, moment=NOW, status=AssetIntelligenceStatus.READY,
             version="v1", confidence=None, stage=None):
    return AssetIntelligenceProviderResult(
        asset_id=42, creator_profile_id=7, provider=name, provider_version=version,
        result_id=result_id, raw_response=raw, normalized_fields=normalized,
        field_confidence=confidence or {key: .8 for key in normalized}, status=status,
        analyzed_at=moment, metadata={"stage": stage} if stage else {},
    )


def results():
    return [
        provider("nudenet", {"safety_classification": "EXPLICIT",
                 "keywords": ("FEMALE_BREAST_EXPOSED",)},
                 [{"class": "FEMALE_BREAST_EXPOSED", "score": .98},
                  {"class": "FEMALE_BREAST_EXPOSED", "score": .97}], result_id="nude-1"),
        provider("gpt-vision", {"tags": ("Portrait", "studio"), "keywords": ("Editorial",)},
                 {"classification": "PREMIUM", "setting": "Photo Studio", "environment": "Indoor",
                  "activity": "Posing", "activities": ["Posing", "posing"],
                  "outfit": "Black Dress", "clothing": ["Black Dress"], "pose": "Standing",
                  "objects": ["Chair", "chair"], "suggested_tags": ["portrait", "Studio"]},
                 result_id="vision-old", moment=NOW - timedelta(minutes=2)),
        provider("gpt-vision", {"tags": ("Portrait", "Editorial"), "keywords": ("Luxury",)},
                 {"classification": "TEASE", "setting": "Rooftop", "environment": "Urban",
                  "activity": "Walking", "outfit": "Red Dress", "pose": "Mid-stride",
                  "objects": ["Skyline", "skyline"]}, result_id="vision-new", moment=NOW),
        provider("grok-vision", {"short_description": "Confident city energy",
                 "content_summary": "Confident city energy", "title": "Rooftop Confidence",
                 "themes": ("Modern Luxury", "modern luxury"),
                 "tags": ("Aspirational", "editorial"), "mood": "Confident",
                 "atmosphere": "Aspirational", "emotional_tone": "Empowered",
                 "visual_style": "Editorial Lifestyle", "suggested_collections": ("City Muse",),
                 "search_phrases": ("luxury city confidence",), "keywords": ("city confidence",),
                 "lifestyle_context": "Fashion-forward urban life"},
                 {"title": "Rooftop Confidence", "descriptive_summary": "Confident city energy"}, result_id="grok-1"),
    ]


def merger(provider_results=None):
    profiles = Profiles()
    service = ContentIntelligenceMergeService(
        intelligence=Intelligence(provider_results if provider_results is not None else results()),
        profiles=profiles, assets=Assets(), now=lambda: NOW,
    )
    return service, profiles


def test_deterministic_merge_uses_latest_successes_and_respects_field_ownership():
    source = results(); raw_before = deepcopy([item.raw_response for item in source])
    service, profiles = merger(source)
    profile = service.merge(42)
    assert profile.status == ContentIntelligenceProfileStatus.COMPLETE
    assert profile.analysis_version == CONTENT_INTELLIGENCE_MERGE_VERSION
    content, context = profile.content_profile, profile.normalized_context
    assert content["classification"] == "TEASE"
    assert content["setting"] == "Rooftop" and content["outfit"] == "Red Dress"
    assert content["objects"] == ("Skyline",)
    assert content["summary"] == "Confident city energy"
    assert content["title"] == "Rooftop Confidence"
    assert context["title"] == "Rooftop Confidence"
    assert content["themes"] == ("Modern Luxury",) and content["mood"] == "Confident"
    assert context["safety_classification"] == "EXPLICIT"
    assert context["nudity_level"] == "explicit" and context["explicit_content"] is True
    assert content["tags"] == ("Portrait", "Editorial", "Aspirational")
    assert [item.raw_response for item in source] == raw_before
    assert profiles.saved[-1] is profile


def test_merge_provenance_confidence_and_search_document_are_preserved():
    service, _ = merger()
    profile = service.merge(42)
    provenance = profile.provenance
    assert provenance["field_ownership"]["outfit"]["provider"] == "gpt-vision"
    assert provenance["field_ownership"]["safety"]["provider"] == "nudenet"
    assert provenance["field_ownership"]["mood"]["provider"] == "grok-vision"
    assert provenance["providers"]["gpt-vision"]["provider_result_id"] == "vision-new"
    assert provenance["merge"]["schema_version"] == CONTENT_INTELLIGENCE_MERGE_VERSION
    assert 0 < profile.content_profile["confidence"] <= 1
    for term in ("TEASE", "Rooftop", "Red Dress", "Walking", "Skyline",
                 "Modern Luxury", "Confident", "Editorial Lifestyle",
                 "luxury city confidence", "EXPLICIT"):
        assert term in profile.search_document


def test_missing_required_provider_persists_failed_profile_without_partial_complete():
    service, profiles = merger(results()[:-1])
    with pytest.raises(MissingRequiredProviderResults, match="grok-vision"):
        service.merge(42)
    assert profiles.profile.status == ContentIntelligenceProfileStatus.FAILED
    assert profiles.profile.missing_components == ("grok-vision",)
    assert profiles.profile.error_code == "MISSING_REQUIRED_PROVIDER_RESULT"


class Jobs:
    def __init__(self): self.job, self.ready, self.released = ContentIntelligenceMergeJob(42, 7, 1), [], []
    def claim_next(self, worker): job, self.job = self.job, None; return job
    def mark_business_ready(self, asset_id): self.ready.append(asset_id); return True
    def release_claim(self, asset_id, worker): self.released.append((asset_id, worker)); return True


class Workflow:
    def __init__(self): self.started, self.completed, self.retried = [], [], []
    def report_started(self, asset_id, provider): self.started.append((asset_id, provider))
    def report_completion(self, asset_id, provider, *, success, **errors):
        self.completed.append((asset_id, provider, success, errors))
        state = AssetIntelligenceStatus.READY if success else AssetIntelligenceStatus.CONTENT_INTELLIGENCE_FAILED
        return SimpleNamespace(current_state=state)
    def retry(self, asset_id): self.retried.append(asset_id); return SimpleNamespace(changed=True)


class CanonicalIntelligence:
    def __init__(self, error=None): self.calls, self.error = [], error
    def merge_provider_results(self, asset_id, *, preserve_analysis_status=False):
        self.calls.append((asset_id, preserve_analysis_status))
        if self.error: raise self.error
        return SimpleNamespace(title="Rooftop Confidence")


def test_worker_runs_application_merge_only_and_reports_ready():
    merge_service, _ = merger()
    jobs, workflow = Jobs(), Workflow()
    canonical = CanonicalIntelligence()
    worker = ContentIntelligenceMergeWorkerService(
        worker_instance_id="merge-1", jobs=jobs, merger=merge_service, workflow=workflow,
        canonical_intelligence=canonical,
    )
    result = worker.process_one()
    assert result["status"] == "READY"
    assert workflow.started == [(42, "CONTENT_INTELLIGENCE")]
    assert workflow.completed[0][1:3] == ("CONTENT_INTELLIGENCE", True)
    assert canonical.calls == [(42, True)]
    assert jobs.ready == [42] and jobs.released == [(42, "merge-1")]
    assert worker.retry_failed(42) is True and workflow.retried == [42]


def test_restart_reuses_completed_merge_without_rebuilding():
    merge_service, profiles = merger(); completed = merge_service.merge(42)
    class NeverMerge(ContentIntelligenceMergeService):
        def merge(self, *args, **kwargs): raise AssertionError("completed merge must be reused")
    reusable = NeverMerge(intelligence=merge_service.intelligence, profiles=profiles,
                          assets=merge_service.assets, now=lambda: NOW)
    jobs, workflow = Jobs(), Workflow()
    canonical = CanonicalIntelligence()
    result = ContentIntelligenceMergeWorkerService(worker_instance_id="merge-2", jobs=jobs,
        merger=reusable, workflow=workflow, canonical_intelligence=canonical).process_one()
    assert result["reused"] is True and result["status"] == "READY"
    assert profiles.profile is completed
    assert canonical.calls == [(42, True)]


def test_missing_provider_worker_reports_failed_and_does_not_mark_business_ready():
    merge_service, _ = merger(results()[:-1])
    jobs, workflow = Jobs(), Workflow()
    result = ContentIntelligenceMergeWorkerService(worker_instance_id="merge-3", jobs=jobs,
        merger=merge_service, workflow=workflow,
        canonical_intelligence=CanonicalIntelligence()).process_one()
    assert result["status"] == "CONTENT_INTELLIGENCE_FAILED"
    assert "grok-vision" in result["error"]
    assert jobs.ready == []
    assert workflow.completed[0][2] is False
    assert workflow.completed[0][3]["error_code"] == "MISSING_REQUIRED_PROVIDER_RESULT"


def test_worker_does_not_report_ready_when_canonical_promotion_fails():
    merge_service, _ = merger()
    jobs, workflow = Jobs(), Workflow()
    result = ContentIntelligenceMergeWorkerService(
        worker_instance_id="merge-4", jobs=jobs, merger=merge_service,
        workflow=workflow,
        canonical_intelligence=CanonicalIntelligence(RuntimeError("canonical persistence failed")),
    ).process_one()
    assert result["status"] == "CONTENT_INTELLIGENCE_FAILED"
    assert jobs.ready == []
    assert workflow.completed == [(42, "CONTENT_INTELLIGENCE", False, {
        "error_code": "RuntimeError", "error_message": "canonical persistence failed",
    })]


def test_canonical_profile_is_hydrated_for_existing_recommendation_consumers():
    merge_service, profiles = merger(); merge_service.merge(42)
    class ProviderMustNotRun:
        def get_understanding(self, asset_id):
            raise AssertionError("completed canonical profile must be consumed first")
    content = ContentIntelligenceService(
        profile_repository=profiles, asset_understanding_service=ProviderMustNotRun()
    ).get_asset_intelligence(42)
    assert content.summary == "Confident city energy"
    assert content.themes == ("Modern Luxury",)
    assert content.setting == "Rooftop" and content.outfit == "Red Dress"
    assert content.technical_quality["runtime_exists"] is True


def test_claim_is_atomic_leased_and_no_downstream_records_are_created():
    import inspect
    from app.repositories.content_intelligence_merge_job_repository import ContentIntelligenceMergeJobRepository
    claim = inspect.getsource(ContentIntelligenceMergeJobRepository.claim_next)
    readiness = inspect.getsource(ContentIntelligenceMergeJobRepository.mark_business_ready)
    assert "CONTENT_INTELLIGENCE_PENDING" in claim and "CONTENT_INTELLIGENCE_RUNNING" in claim
    assert "FOR UPDATE OF p SKIP LOCKED" in claim and "LIMIT 1" in claim
    assert "content_merge_lease_expires_at IS NULL" in claim
    assert "content_merge_lease_expires_at <= now()" in claim
    assert "INSERT" not in readiness.upper()
    for table in ("products", "fulfillment_registrations", "chat_commerce_registrations", "publishing"):
        assert table not in readiness.lower()


def test_merge_service_has_no_provider_execution_dependency():
    import inspect
    source = inspect.getsource(ContentIntelligenceMergeService)
    for forbidden in ("Adapter", "run_nudenet", "run_gpt_vision", "GROK_API_KEY", ".analyze("):
        assert forbidden not in source
