import pytest

from app.models.asset_intelligence import AssetIntelligenceStatus as State
from app.services.business_asset_analysis_orchestrator import BusinessAssetAnalysisOrchestrator


def test_workflow_projection_casts_jsonb_transition_value_for_postgres():
    import inspect
    from app.repositories.business_asset_analysis_workflow_repository import BusinessAssetAnalysisWorkflowRepository

    source = inspect.getsource(BusinessAssetAnalysisWorkflowRepository.transition)
    assert "jsonb_build_object('asset_intelligence_status', %s::text)" in source


class Repository:
    def __init__(self, state=State.PENDING):
        self.states = {42: state}
        self.transitions = []
        self.provider_completion = None

    def get_state(self, asset_id): return self.states[asset_id]
    def transition(self, asset_id, expected, target, **errors):
        if self.states[asset_id] != expected:
            return False
        self.states[asset_id] = target
        self.transitions.append((expected, target, errors))
        return True
    def next_asset_to_orchestrate(self):
        return next((asset_id for asset_id, state in self.states.items()
                     if state in BusinessAssetAnalysisOrchestrator.ADVANCES), None)
    def get_provider_completion(self, asset_id, provider): return self.provider_completion


class Dispatcher:
    def __init__(self): self.calls = []
    def dispatch(self, provider, asset_id): self.calls.append((provider, asset_id)); return provider == "NUDENET"


def test_orchestrator_dispatches_nudenet_then_advances_completion_to_vision_placeholder():
    repository = Repository()
    dispatcher = Dispatcher()
    workflow = BusinessAssetAnalysisOrchestrator(repository, dispatcher)
    pending = workflow.advance(42)
    assert pending.current_state == State.NUDENET_PENDING
    assert pending.next_provider == "NUDENET" and pending.dispatched is True
    assert dispatcher.calls == [("NUDENET", 42)]
    workflow.report_started(42, "NUDENET")
    complete = workflow.report_completion(42, "NUDENET", success=True)
    assert complete.current_state == State.VISION_PENDING
    assert complete.next_provider == "VISION" and complete.dispatched is False


def test_placeholder_stages_are_states_only_and_ready_cannot_occur_prematurely():
    repository = Repository(State.VISION_PENDING)
    workflow = BusinessAssetAnalysisOrchestrator(repository)
    decision = workflow.advance(42)
    assert decision.current_state == State.VISION_PENDING
    assert decision.complete is False and decision.dispatched is False
    assert all(target != State.READY for _, target, _ in repository.transitions)


def test_failure_requires_retry_and_retry_returns_same_provider_pending():
    repository = Repository(State.NUDENET_RUNNING)
    workflow = BusinessAssetAnalysisOrchestrator(repository)
    failed = workflow.report_completion(42, "NUDENET", success=False,
                                        error_code="DOWN", error_message="offline")
    assert failed.current_state == State.NUDENET_FAILED and failed.retry_required
    retried = workflow.retry(42)
    assert retried.current_state == State.NUDENET_PENDING and retried.dispatched


def test_duplicate_reports_and_orchestration_are_idempotent():
    repository = Repository(State.NUDENET_PENDING)
    first = BusinessAssetAnalysisOrchestrator(repository)
    first.report_started(42, "NUDENET")
    second = BusinessAssetAnalysisOrchestrator(repository)  # simulated restart
    duplicate = second.report_started(42, "NUDENET")
    assert duplicate.changed is False
    second.report_completion(42, "NUDENET", success=True)
    repeated = second.advance(42)
    assert repeated.current_state == State.VISION_PENDING and repeated.changed is False


def test_restart_reconciles_persisted_provider_completion():
    repository = Repository(State.NUDENET_RUNNING)
    repository.provider_completion = "READY"
    decision = BusinessAssetAnalysisOrchestrator(repository).advance(42)
    assert decision.current_state == State.VISION_PENDING
    assert repository.transitions[0][0:2] == (State.NUDENET_RUNNING, State.NUDENET_COMPLETE)


def test_unknown_states_and_providers_are_rejected():
    with pytest.raises(ValueError, match="Unknown Business Asset analysis workflow state"):
        BusinessAssetAnalysisOrchestrator(Repository(State.ANALYZING)).advance(42)
    with pytest.raises(ValueError, match="Unknown analysis provider"):
        BusinessAssetAnalysisOrchestrator(Repository()).report_started(42, "other")


def test_only_merge_completion_can_advance_to_ready():
    for state in (State.PENDING, State.NUDENET_COMPLETE, State.VISION_COMPLETE, State.GROK_COMPLETE):
        repository = Repository(state)
        decision = BusinessAssetAnalysisOrchestrator(repository).advance(42)
        assert decision.current_state != State.READY
    repository = Repository(State.CONTENT_INTELLIGENCE_COMPLETE)
    decision = BusinessAssetAnalysisOrchestrator(repository).advance(42)
    assert decision.current_state == State.READY and decision.complete


def test_vision_completion_advances_to_grok_pending():
    repository = Repository(State.VISION_COMPLETE)
    decision = BusinessAssetAnalysisOrchestrator(repository).advance(42)
    assert decision.current_state == State.GROK_PENDING
    assert decision.next_provider == "GROK"


def test_grok_completion_advances_to_content_intelligence_pending():
    repository = Repository(State.GROK_COMPLETE)
    decision = BusinessAssetAnalysisOrchestrator(repository).advance(42)
    assert decision.current_state == State.CONTENT_INTELLIGENCE_PENDING
    assert decision.next_provider == "CONTENT_INTELLIGENCE"
