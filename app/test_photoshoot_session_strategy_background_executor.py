from types import SimpleNamespace

import pytest

from app.services.photoshoot_session_strategy_background_executor import (
    PhotoshootSessionStrategyBackgroundExecutor,
)


class Operations:
    def __init__(self):
        self.progress_calls = []; self.successes = []
        self.repository = SimpleNamespace(renew_lease=lambda *args, **kwargs: True)
    def progress(self, *args, **kwargs): self.progress_calls.append((args, kwargs))
    def succeed(self, *args, **kwargs): self.successes.append((args, kwargs))


def operation():
    return SimpleNamespace(
        operation_id="operation-1", creator_profile_id=7,
        subject_id="deliverable-1", metadata={
            "deliverableId": "deliverable-1",
            "strategyVersion": "photoshoot_session_sales_v1",
        },
    )


def test_executor_generates_only_strategy_and_completes_operation():
    calls = []
    strategy = SimpleNamespace(
        deliverable_id="deliverable-1", strategy_version="photoshoot_session_sales_v1",
    )
    generator = SimpleNamespace(generate=lambda *args, **kwargs: calls.append((args, kwargs)) or strategy)
    operations = Operations()
    PhotoshootSessionStrategyBackgroundExecutor(strategy=generator).execute(
        operation(), operations, worker_id="worker-1",
    )
    assert calls == [(('deliverable-1',), {
        'creator_profile_id': 7, 'strategy_version': 'photoshoot_session_sales_v1',
    })]
    assert operations.successes
    assert operations.successes[0][1]["result_reference"] == "deliverable-1"


def test_executor_revalidates_session_mode_before_provider_through_canonical_service():
    generator = SimpleNamespace(generate=lambda *_args, **_kwargs: (_ for _ in ()).throw(
        ValueError("Session Sales Strategy requires SESSION selling mode.")))
    operations = Operations()
    with pytest.raises(ValueError, match="SESSION selling mode"):
        PhotoshootSessionStrategyBackgroundExecutor(strategy=generator).execute(
            operation(), operations, worker_id="worker-1",
        )
    assert not operations.successes
