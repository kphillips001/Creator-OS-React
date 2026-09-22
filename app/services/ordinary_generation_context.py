"""Operation-bound response generation. Nested rewrites cannot grant calls."""
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy

from app.repositories.ordinary_generation_budget_repository import GenerationBudgetClosed

_current = ContextVar('ordinary_generation_budget', default=None)


def current_generation():
    return _current.get()


@contextmanager
def generation_scope(session):
    token = _current.set(session)
    try:
        yield session
    finally:
        _current.reset(token)


def analysis_completion(client, *, purpose="ANALYSIS", **kwargs):
    session = current_generation()
    if session is not None:
        return session.analysis(client, provider='OPENAI', purpose=purpose, **kwargs)
    return client.chat.completions.create(**kwargs)


class OrdinaryGenerationSession:
    def __init__(self, repository, operation, owner, *, correction=False):
        self.repository, self.operation, self.owner = repository, operation, owner
        self.correction = correction
        self.completion = None

    def snapshot(self, value):
        self.repository.save(self.operation.operation_id, self.owner, context=value)

    def analysis(self, client, *, provider, purpose="ANALYSIS", **kwargs):
        attempt = self.repository.reserve_analysis(self.operation.operation_id, self.owner, provider, purpose)
        try:
            result = client.with_options(max_retries=0).chat.completions.create(**kwargs)
        except Exception as error:
            self.repository.save(self.operation.operation_id, self.owner, event={
                'kind': 'ANALYSIS_FINISHED', 'attempt': attempt, 'errorType': type(error).__name__})
            raise
        usage = getattr(result, 'usage', None)
        self.repository.save(self.operation.operation_id, self.owner, event={
            'kind': 'ANALYSIS_FINISHED', 'attempt': attempt, 'outcome': 'RETURNED',
            'usage': usage.model_dump() if hasattr(usage, 'model_dump') else None})
        return result

    def complete(self, client, *, provider, **kwargs):
        # Existing validators may ask for independent rewrites. Re-evaluate the
        # same candidate instead; only the final consolidated gate owns correction.
        if self.completion is not None:
            self.repository.save(self.operation.operation_id, self.owner, event={
                'kind': 'REWRITE_DEFERRED', 'reason': 'CONSOLIDATED_FINAL_GATE_OWNS_CORRECTION'})
            return deepcopy(self.completion)
        attempt = self.repository.reserve_provider(self.operation.operation_id, self.owner,
            provider=provider, correction=self.correction)
        try:
            result = client.with_options(max_retries=0).chat.completions.create(**kwargs)
            text = str(result.choices[0].message.content or '').strip()
        except Exception as error:
            self.repository.finish_provider(self.operation.operation_id, self.owner, attempt,
                error=type(error).__name__)
            raise
        usage = getattr(result, 'usage', None)
        usage = usage.model_dump() if hasattr(usage, 'model_dump') else None
        self.repository.finish_provider(self.operation.operation_id, self.owner, attempt,
            text=text, usage=usage)
        if text:
            self.completion = deepcopy(result)
            row = self.repository.read(self.operation.operation_id)
            snapshot = dict(row['context_snapshot'])
            if snapshot:
                snapshot.update(provider=provider, model=kwargs.get('model', snapshot.get('model')))
                self.repository.save(self.operation.operation_id, self.owner, context=snapshot)
        else:
            raise EmptyProviderResponse('Provider returned no response candidate')
        return result


class EmptyProviderResponse(RuntimeError):
    pass
