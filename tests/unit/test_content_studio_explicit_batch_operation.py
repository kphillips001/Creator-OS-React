from types import SimpleNamespace
from uuid import uuid4

from app.api import content_studio


def test_explicit_batch_exists_and_is_active_before_first_enhancement(monkeypatch):
    captured = {}
    operation = SimpleNamespace(operation_id=uuid4())

    class Repository:
        def transition(self, operation_id, status, **values):
            captured["transition"] = (operation_id, status, values)
            return operation

    class Service:
        repository = Repository()

        def create(self, **values):
            captured["create"] = values
            return operation, True

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService", Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.start_explicit_batch(content_studio.ExplicitBatchStartRequest(
        batchId="batch-click-1",
        provider="seedream_5_0_pro",
        concepts=[{"id": "hardcore-0", "tier": "hardcore", "concept": "concept one"}],
    ))

    assert result["operationId"] == str(operation.operation_id)
    assert captured["create"]["operation_type"] == "content_studio_explicit_batch"
    assert captured["create"]["current_stage"] == "PREPARING"
    assert captured["create"]["progress_total"] == 1
    assert captured["create"]["metadata"]["currentIdeaIndex"] == 1
    assert captured["transition"][1] == "RUNNING"
    assert captured["transition"][2]["message"] == "Preparing idea 1 of 1..."
