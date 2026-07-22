from types import SimpleNamespace

from app.models.asset_intelligence import AssetIntelligenceStatus as State
from app.repositories.photoshoot_analysis_workflow_repository import PhotoshootAnalysisJob
from app.services.photoshoot_analysis_orchestrator_service import PhotoshootAnalysisOrchestratorService


class Workflows:
    def __init__(self, stage): self.job = PhotoshootAnalysisJob("set-1", stage, 1); self.transitions = []
    def claim_next(self, _worker): job, self.job = self.job, None; return job
    def transition(self, deliverable, worker, stage, **kwargs): self.transitions.append((deliverable, worker, stage, kwargs)); return {"current_stage": stage}


class Photoshoots:
    def __init__(self): self.pending = self.failed = self.ready = False
    def get(self, _id): return {"deliverable_id": "set-1", "photoshoot_session_id": "session-1", "creator_profile_id": 7, "registration_state": "REGISTERED", "is_archived": False, "shot_count": 2, "ai_title": "Morning Light", "ai_description": "A calm outdoor set.", "intelligence_profile": {"mood": ["calm"]}}
    def members(self, _session): return ({"asset_id": 42},)
    def set_analysis_pending(self, _id): self.pending = True
    def set_analysis_failure(self, _id, _error): self.failed = True
    def set_naming_failure(self, _id, _error): self.failed = True
    def set_ready(self, _id): self.ready = True
    def upsert_intelligence(self, *_args, **_kwargs): return {}


def service(stage, profile_state, results=()):
    workflows, photoshoots = Workflows(stage), Photoshoots()
    profile = SimpleNamespace(analysis_status=profile_state, error_message=None)
    intelligence = SimpleNamespace(get_profile=lambda _id: profile, list_provider_results=lambda _id: results)
    intelligence_service = SimpleNamespace(initialize_pending=lambda **_kwargs: profile)
    content = SimpleNamespace(get_by_asset_id=lambda _id: SimpleNamespace(ready=True))
    business = SimpleNamespace(get_by_asset_id=lambda _id: SimpleNamespace(content_intelligence_ready=True))
    deliverables = SimpleNamespace(
        aggregate_members=lambda _ids: ("READY", {"mood": ["calm"]}, None),
        ensure_naming_or_raise=lambda row, data: row,
    )
    value = PhotoshootAnalysisOrchestratorService(
        worker_instance_id="worker-1", workflows=workflows, photoshoots=photoshoots,
        intelligence=intelligence, intelligence_service=intelligence_service,
        content=content, business=business, deliverables=deliverables)
    return value, workflows, photoshoots


def test_missing_member_enters_canonical_image_pipeline_and_remains_pending():
    value, workflows, photoshoots = service("MEMBER_ANALYSIS_RUNNING", State.PENDING)
    result = value.process_one()
    assert result["status"] == "MEMBER_ANALYSIS_PENDING"
    assert workflows.transitions[-1][2] == "MEMBER_ANALYSIS_PENDING"
    assert photoshoots.pending


def test_member_failure_is_terminal_and_identifies_member():
    value, workflows, photoshoots = service("MEMBER_ANALYSIS_RUNNING", State.GROK_FAILED)
    result = value.process_one()
    assert result["status"] == "MEMBER_ANALYSIS_FAILED"
    assert workflows.transitions[-1][3]["member_id"] == 42
    assert photoshoots.failed


def test_canonical_evidence_advances_then_aggregation_and_naming_reach_ready():
    results = tuple(SimpleNamespace(status=State.READY, metadata={"stage": stage}) for stage in ("NUDENET", "VISION", "GROK"))
    member, member_workflows, _ = service("MEMBER_ANALYSIS_RUNNING", State.READY, results)
    assert member.process_one()["status"] == "PHOTOSHOOT_INTELLIGENCE_PENDING"
    assert member_workflows.transitions[-1][2] == "PHOTOSHOOT_INTELLIGENCE_PENDING"

    aggregate, aggregate_workflows, _ = service("PHOTOSHOOT_INTELLIGENCE_RUNNING", State.READY, results)
    assert aggregate.process_one()["status"] == "NAMING_PENDING"
    assert aggregate_workflows.transitions[-1][2] == "NAMING_PENDING"

    naming, naming_workflows, photoshoots = service("NAMING_RUNNING", State.READY, results)
    assert naming.process_one()["status"] == "READY"
    assert naming_workflows.transitions[-1][2] == "READY"
    assert photoshoots.ready


def test_claim_repository_uses_skip_locked_and_expired_running_leases():
    import inspect
    from app.repositories.photoshoot_analysis_workflow_repository import PhotoshootAnalysisWorkflowRepository
    source = inspect.getsource(PhotoshootAnalysisWorkflowRepository.claim_next)
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "lease_expires_at<=now()" in source
