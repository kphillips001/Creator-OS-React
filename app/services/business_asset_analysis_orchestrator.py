"""Single workflow authority for provider-neutral Business Asset analysis."""

from __future__ import annotations

from app.models.asset_intelligence import AssetIntelligenceStatus as State
from app.models.business_asset_analysis_workflow import (
    IMPLEMENTED_PROVIDERS, AnalysisWorkflowDecision,
)
from app.repositories.business_asset_analysis_workflow_repository import (
    BusinessAssetAnalysisWorkflowRepository,
)


class DurableAnalysisProviderDispatcher:
    """Dispatch boundary: provider workers discover durable *_PENDING state."""

    def dispatch(self, provider: str, asset_id: int) -> bool:
        return provider in IMPLEMENTED_PROVIDERS


class BusinessAssetAnalysisOrchestrator:
    """Advances workflow state; it never imports or executes provider adapters."""

    ADVANCES = {
        State.REGISTERED: State.PENDING,
        State.PENDING: State.NUDENET_PENDING,
        State.NUDENET_COMPLETE: State.VISION_PENDING,
        State.VISION_COMPLETE: State.GROK_PENDING,
        State.GROK_COMPLETE: State.CONTENT_INTELLIGENCE_PENDING,
        State.CONTENT_INTELLIGENCE_COMPLETE: State.READY,
    }
    PROVIDER_FOR_PENDING = {
        State.NUDENET_PENDING: "NUDENET",
        State.VISION_PENDING: "VISION",
        State.GROK_PENDING: "GROK",
        State.CONTENT_INTELLIGENCE_PENDING: "CONTENT_INTELLIGENCE",
    }
    RUNNING = {
        "NUDENET": State.NUDENET_RUNNING, "VISION": State.VISION_RUNNING,
        "GROK": State.GROK_RUNNING, "CONTENT_INTELLIGENCE": State.CONTENT_INTELLIGENCE_RUNNING,
    }
    COMPLETE = {
        "NUDENET": State.NUDENET_COMPLETE, "VISION": State.VISION_COMPLETE,
        "GROK": State.GROK_COMPLETE, "CONTENT_INTELLIGENCE": State.CONTENT_INTELLIGENCE_COMPLETE,
    }
    FAILED = {
        "NUDENET": State.NUDENET_FAILED, "VISION": State.VISION_FAILED,
        "GROK": State.GROK_FAILED, "CONTENT_INTELLIGENCE": State.CONTENT_INTELLIGENCE_FAILED,
    }
    WORKFLOW_STATES = frozenset(
        {State.REGISTERED, State.PENDING, State.READY}
        | set(PROVIDER_FOR_PENDING) | set(RUNNING.values())
        | set(COMPLETE.values()) | set(FAILED.values())
    )

    def __init__(self, repository=None, dispatcher=None) -> None:
        self.repository = repository or BusinessAssetAnalysisWorkflowRepository()
        self.dispatcher = dispatcher or DurableAnalysisProviderDispatcher()

    def advance(self, asset_id: int) -> AnalysisWorkflowDecision:
        state = self.repository.get_state(asset_id)
        self._validate_state(state)
        running_provider = next((name for name, running in self.RUNNING.items() if running == state), None)
        if running_provider is not None:
            completion = self.repository.get_provider_completion(asset_id, running_provider)
            if completion in {"READY", "SUCCEEDED"}:
                return self.report_completion(asset_id, running_provider, success=True)
            if completion in {"FAILED", "TIMED_OUT"}:
                return self.report_completion(asset_id, running_provider, success=False,
                                              error_code="PROVIDER_FAILED",
                                              error_message=f"{running_provider} provider result failed.")
            return self._decision(asset_id, state, state, provider=running_provider)
        target = self.ADVANCES.get(state)
        if target is None:
            return self._decision(asset_id, state, state)
        if target == State.READY and state != State.CONTENT_INTELLIGENCE_COMPLETE:
            raise ValueError("READY cannot occur before Content Intelligence completes.")
        changed = self.repository.transition(asset_id, state, target)
        current = target if changed else self.repository.get_state(asset_id)
        provider = self.PROVIDER_FOR_PENDING.get(current)
        dispatched = bool(changed and provider and self.dispatcher.dispatch(provider, asset_id))
        return self._decision(asset_id, state, current, provider=provider, changed=changed,
                              dispatched=dispatched)

    def orchestrate_next(self) -> AnalysisWorkflowDecision | None:
        asset_id = self.repository.next_asset_to_orchestrate()
        return self.advance(asset_id) if asset_id is not None else None

    def report_started(self, asset_id: int, provider: str) -> AnalysisWorkflowDecision:
        provider = self._provider(provider)
        state = self.repository.get_state(asset_id)
        self._validate_state(state)
        expected = next(item for item, name in self.PROVIDER_FOR_PENDING.items() if name == provider)
        if state == self.RUNNING[provider]:
            return self._decision(asset_id, state, state, provider=provider)
        if state != expected:
            raise ValueError(f"{provider} cannot start from {state.value}.")
        changed = self.repository.transition(asset_id, expected, self.RUNNING[provider])
        return self._decision(asset_id, state, self.RUNNING[provider], provider=provider, changed=changed)

    def report_completion(self, asset_id: int, provider: str, *, success: bool,
                          error_code: str | None = None, error_message: str | None = None) -> AnalysisWorkflowDecision:
        provider = self._provider(provider)
        state = self.repository.get_state(asset_id)
        self._validate_state(state)
        target = self.COMPLETE[provider] if success else self.FAILED[provider]
        if state == target:
            return self._decision(asset_id, state, state, retry=not success)
        if state != self.RUNNING[provider]:
            raise ValueError(f"{provider} cannot complete from {state.value}.")
        changed = self.repository.transition(asset_id, state, target,
                                             error_code=error_code, error_message=error_message)
        if success and changed:
            return self.advance(asset_id)
        return self._decision(asset_id, state, target, retry=not success, changed=changed)

    def retry(self, asset_id: int) -> AnalysisWorkflowDecision:
        state = self.repository.get_state(asset_id)
        self._validate_state(state)
        provider = next((name for name, failed in self.FAILED.items() if failed == state), None)
        if provider is None:
            raise ValueError(f"Analysis retry is not valid from {state.value}.")
        pending = next(item for item, name in self.PROVIDER_FOR_PENDING.items() if name == provider)
        changed = self.repository.transition(asset_id, state, pending)
        dispatched = bool(changed and self.dispatcher.dispatch(provider, asset_id))
        return self._decision(asset_id, state, pending, provider=provider, changed=changed,
                              dispatched=dispatched)

    def _decision(self, asset_id, previous, current, *, provider=None, retry=False,
                  changed=False, dispatched=None):
        return AnalysisWorkflowDecision(
            asset_id=asset_id, previous_state=previous, current_state=current,
            next_provider=provider,
            dispatched=(bool(provider in IMPLEMENTED_PROVIDERS and current.value.endswith("_PENDING"))
                        if dispatched is None else dispatched),
            complete=current == State.READY, retry_required=retry, changed=changed,
        )

    @classmethod
    def _provider(cls, provider: str) -> str:
        value = str(provider).strip().upper()
        if value not in cls.RUNNING:
            raise ValueError(f"Unknown analysis provider: {provider}")
        return value

    @classmethod
    def _validate_state(cls, state: State) -> None:
        if state not in cls.WORKFLOW_STATES:
            raise ValueError(f"Unknown Business Asset analysis workflow state: {state.value}")
