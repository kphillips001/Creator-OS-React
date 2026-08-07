from types import SimpleNamespace

import pytest

from app.services.photoshoot_commerce_deliverable_service import PhotoshootCommerceDeliverableService


class Repository:
    def __init__(self):
        self.production = None; self.shots = (); self.running = []; self.failures = []; self.persisted = []
    def intelligence_members(self, _session):
        return ({"asset_id": 10, "shot_order": 1, "is_hero": True, "file_path": "seed.png", "content_profile": {}, "normalized_context": {}},
                {"asset_id": 20, "shot_order": 2, "is_hero": False, "file_path": "approved.png", "content_profile": {}, "normalized_context": {}})
    def get_intelligence(self, _session): return self.production
    def shot_intelligence(self, _session, _version): return self.shots
    def mark_intelligence_running(self, session, version): self.running.append((session, version))
    def mark_intelligence_failure(self, session, version, stage, error): self.failures.append((session, version, stage, str(error)))
    def persist_canonical_intelligence(self, session, version, profile):
        self.persisted.append((session, version, profile)); self.shots = tuple(profile["shot_intelligence"])


def session():
    return SimpleNamespace(session_id="session-1", creator_notes="notes", creative_mode="premium",
                           creative_continuity={"session_plan": ({"title": "Opening"},)})


def request(status="approved"):
    return SimpleNamespace(status=status, sequence_index=2, imported_asset_ids=(20,), prompt_text="approved prompt",
                           review_notes=None, metadata={"generated_image_ids": ("approved-image",)})


def profile(version):
    return {"intelligence_version": version,
        "commercial_title": "Complete set", "subtitle": "An ordered story",
        "commercial_summary": "A complete commercial sequence.",
        "buyer_profile": {"audience": "collector"},
        "sales_strategy": {"positioning": "complete sequence"},
        "sales_brain_brief": "Sell the complete sequence.",
        "shot_intelligence": (
        {"asset_id": 10, "shot_order": 1, "sequence_role": "seed"},
        {"asset_id": 20, "shot_order": 2, "sequence_role": "closing"}),
        "production_analysis": {"story": "progression"}, "cross_validation": {"hero_asset_id": 20}}


def service(repo, generator):
    queue = SimpleNamespace(requests_for_session=lambda _id: (request(), request("rejected")))
    intelligence = SimpleNamespace(generate=generator)
    return PhotoshootCommerceDeliverableService(
        queue=queue, library=SimpleNamespace(), repository=repo,
        intelligence=SimpleNamespace(), commercial_intelligence=intelligence,
        workflows=SimpleNamespace())


def test_only_approved_members_are_ordered_and_persisted_once():
    repo = Repository(); calls = []
    value = service(repo, lambda **kwargs: calls.append(kwargs) or profile(kwargs["intelligence_version"]))
    value.run_canonical_intelligence(session(), intelligence_version="v1")
    assert [chapter["asset_id"] for chapter in calls[0]["chapters"]] == [10, 20]
    assert [chapter["shot_order"] for chapter in calls[0]["chapters"]] == [1, 2]
    assert "rejected" not in str(calls[0]["chapters"])
    assert len(repo.persisted) == 1 and len(repo.shots) == 2


def test_current_complete_version_is_not_regenerated_but_new_version_is():
    repo = Repository(); repo.production = {"status": "READY", "pipeline_stage": "COMPLETE",
        "intelligence_version": "v1", "profile_data": {"cached": True}}
    repo.shots = ({"asset_id": 10}, {"asset_id": 20})
    calls = []
    value = service(repo, lambda **kwargs: calls.append(kwargs) or profile(kwargs["intelligence_version"]))
    assert value.run_canonical_intelligence(session(), intelligence_version="v1") == {"cached": True}
    value.run_canonical_intelligence(session(), intelligence_version="v2")
    assert len(calls) == 1 and repo.persisted[0][1] == "v2"


def test_failure_is_staged_and_never_persisted_complete():
    repo = Repository()
    value = service(repo, lambda **_: (_ for _ in ()).throw(RuntimeError("shot failed")))
    with pytest.raises(RuntimeError, match="shot failed"):
        value.run_canonical_intelligence(session(), intelligence_version="v1")
    assert repo.persisted == []
    assert repo.failures[0][2] == "PERSISTENCE_FAILED"


def test_legacy_backfill_preserves_commercial_intelligence_fields():
    repo = Repository()
    repo.production = {
        "status": "READY", "pipeline_stage": "PENDING", "intelligence_version": "completed_photoshoot_v1",
        "commercial_title": "Legacy title", "profile_data": {
            "commercial_title": "Legacy title", "subtitle": "Legacy subtitle",
            "commercial_summary": "Legacy summary",
            "buyer_profile": {"audience": "legacy"}, "input_snapshot": {"legacy": True},
            "sales_strategy": {"positioning": "legacy"},
            "sales_brain_brief": "Legacy sales brief.",
            "model": "legacy-model", "generated_at": "2026-01-01T00:00:00+00:00",
        },
    }
    generated = profile("completed_photoshoot_v2") | {
        "commercial_title": "Replacement title", "commercial_summary": "Replacement summary",
        "buyer_profile": {"audience": "replacement"}, "input_snapshot": {"canonical": True},
        "model": "canonical-model", "generated_at": "2026-02-01T00:00:00+00:00",
    }
    value = service(repo, lambda **_: generated)
    result = value.run_canonical_intelligence(
        session(), intelligence_version="completed_photoshoot_v2", force=True,
        preserve_commercial_intelligence=True,
    )
    assert result["commercial_title"] == "Legacy title"
    assert result["commercial_summary"] == "Legacy summary"
    assert result["buyer_profile"] == {"audience": "legacy"}
    assert result["input_snapshot"] == {"legacy": True}
    assert result["model"] == "legacy-model"
    assert result["production_analysis"] == {"story": "progression"}
