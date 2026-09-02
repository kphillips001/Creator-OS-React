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
    assert captured["create"]["cancellation_supported"] is True
    assert captured["create"]["exclusive_active_type"] is True
    assert captured["create"]["metadata"]["currentIdeaIndex"] == 1
    assert "transition" not in captured


def test_fresh_explicit_batch_rejects_a_different_active_batch(monkeypatch):
    active = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="RUNNING", idempotency_key="content-studio-explicit-batch:older",
    )

    class Service:
        def create(self, **values): return active, False

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.start_explicit_batch(content_studio.ExplicitBatchStartRequest(
        batchId="new-attempt", provider="seedream_5_0_pro",
        concepts=[{"id": "softcore-0", "tier": "softcore", "concept": "new concept"}],
    ))

    assert result.status_code == 409
    assert b"already active" in result.body


def test_duplicate_create_for_same_batch_is_idempotent(monkeypatch):
    batch_id = "same-click"
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="QUEUED", idempotency_key=f"content-studio-explicit-batch:{batch_id}",
    )

    class Service:
        def create(self, **values): return operation, False

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})
    result = content_studio.start_explicit_batch(content_studio.ExplicitBatchStartRequest(
        batchId=batch_id, provider="seedream_5_0_pro",
        concepts=[{"id": "softcore-0", "tier": "softcore", "concept": "same concept"}],
    ))

    assert result["operationId"] == str(operation.operation_id)
    assert result["reused"] is True


def test_cancelled_explicit_batch_rejects_late_client_progress(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="CANCELLED",
    )
    captured = {"progress": 0}

    class Service:
        def get(self, operation_id, **scope):
            return operation

        def progress(self, *args, **kwargs):
            captured["progress"] += 1
            raise AssertionError("late progress must not mutate a cancelled batch")

        def payload(self, value):
            return {"operationId": str(value.operation_id), "status": value.status}

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService", Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.update_explicit_batch(
        str(operation.operation_id),
        content_studio.ExplicitBatchProgressRequest(
            current=8, total=12, stage="GENERATING", message="late update",
            metadata={"currentIdeaIndex": 9},
        ),
    )

    assert result["operation"]["status"] == "CANCELLED"
    assert captured["progress"] == 0


def test_successful_explicit_batch_uses_atomic_workspace_consumption_boundary(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch", status="RUNNING",
    )
    completed = SimpleNamespace(**{**operation.__dict__, "status": "SUCCEEDED"})
    captured = {}

    class Service:
        def get(self, operation_id, **scope): return operation
        def complete_explicit_batch(self, operation_id, **values):
            captured.update(operation_id=operation_id, values=values); return completed
        def succeed(self, *args, **kwargs): raise AssertionError("generic success must not bypass workspace consumption")
        def payload(self, value): return {"operationId": str(value.operation_id), "status": value.status}

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})
    result = content_studio.update_explicit_batch(str(operation.operation_id), content_studio.ExplicitBatchProgressRequest(
        current=2, total=2, stage="COMPLETE", message="2 of 2 ideas processed.",
        metadata={"completedIdeas": 2, "failedIdeas": 0, "phase": "complete"}, terminalStatus="SUCCEEDED",
    ))
    assert result["operation"]["status"] == "SUCCEEDED"
    assert captured["values"]["metadata"]["completedIdeas"] == 2


def test_partial_explicit_batch_retains_recoverable_workspace(monkeypatch):
    operation = SimpleNamespace(operation_id=uuid4(), operation_type="content_studio_explicit_batch", status="RUNNING")
    partial = SimpleNamespace(**{**operation.__dict__, "status": "PARTIAL"});captured={}
    class Service:
        def get(self, operation_id, **scope): return operation
        def complete_explicit_batch(self, *args, **kwargs): raise AssertionError("partial workspace must not be consumed")
        def succeed(self, operation_id, **values): captured.update(values);return partial
        def payload(self, value): return {"status":value.status}
    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio,"_current_account_id",lambda:3);monkeypatch.setattr(content_studio,"get_active_creator_profile",lambda account:{"id":2})
    result=content_studio.update_explicit_batch(str(operation.operation_id),content_studio.ExplicitBatchProgressRequest(current=1,total=2,stage="COMPLETE",message="partial",metadata={"completedIdeas":1,"failedIdeas":1},terminalStatus="PARTIAL"))
    assert result["operation"]["status"]=="PARTIAL" and captured["partial"] is True


def test_cancelled_explicit_batch_workspace_can_be_durably_reset(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="CANCELLED", terminal=True, progress_current=8, progress_total=12,
        progress_percent=66.67, current_stage="CANCELLED", metadata={"items": ["preserved"]},
    )
    dismissed = SimpleNamespace(
        **{**operation.__dict__, "metadata": {**operation.metadata, "workspaceDismissed": True}},
    )
    captured = {}

    class Service:
        def get(self, operation_id, **scope):
            return operation

        def progress(self, operation_id, **values):
            captured.update(operation_id=operation_id, values=values)
            return dismissed

        def payload(self, value):
            return {"operationId": str(value.operation_id), "status": value.status, "metadata": value.metadata}

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService", Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.reset_explicit_batch_workspace(str(operation.operation_id))

    assert result["operation"]["metadata"]["workspaceDismissed"] is True
    assert captured["values"]["metadata"] == {"workspaceDismissed": True}
    assert operation.metadata["items"] == ["preserved"]


def test_explicit_batch_becomes_running_only_when_client_executor_starts(monkeypatch):
    captured = {}
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="QUEUED", stage_message="Preparing idea 1 of 1...",
    )
    running = SimpleNamespace(**{**operation.__dict__, "status": "RUNNING"})

    class Repository:
        def transition(self, operation_id, status, **values):
            captured["transition"] = (operation_id, status, values)
            return running

    class Service:
        repository = Repository()

        def get(self, operation_id, **scope):
            captured["scope"] = scope
            return operation

        def payload(self, value):
            return {"operationId": str(value.operation_id), "status": value.status}

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService", Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.activate_explicit_batch(str(operation.operation_id))

    assert result["operation"]["status"] == "RUNNING"
    assert captured["scope"] == {"creator_profile_id": 2, "account_id": 3}
    assert captured["transition"][0] == operation.operation_id
    assert captured["transition"][1] == "RUNNING"
    assert captured["transition"][2]["metadata"] == {"clientExecutionStarted": True}


def test_terminal_explicit_batch_cannot_be_reactivated(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch",
        status="FAILED", stage_message="failed before activation",
    )

    class Service:
        repository = SimpleNamespace(transition=lambda *_args, **_kwargs: None)
        def get(self, operation_id, **scope): return operation

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.activate_explicit_batch(str(operation.operation_id))
    assert result.status_code == 409


def test_handed_off_inspiration_workspace_is_dismissed_without_deleting_history(monkeypatch):
    captured = {}
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_inspiration",
        status="SUCCEEDED", current_stage="COMPLETE",
        progress_current=2, progress_total=2, progress_percent=100,
        metadata={"phase": "HANDED_OFF", "hardcore": ["one"], "softcore": ["two"]},
    )
    dismissed = SimpleNamespace(
        **{**operation.__dict__, "metadata": {**operation.metadata, "workspaceDismissed": True}},
    )

    class Service:
        def get(self, operation_id, **scope):
            return operation

        def progress(self, operation_id, **values):
            captured.update(operation_id=operation_id, values=values)
            return dismissed

        def payload(self, value):
            return {"operationId": str(value.operation_id), "status": value.status, "metadata": value.metadata}

    monkeypatch.setattr(
        "app.services.background_operation_service.BackgroundOperationService", Service,
    )
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})

    result = content_studio.dismiss_explicit_inspiration_workspace(str(operation.operation_id))

    assert result["operation"]["status"] == "SUCCEEDED"
    assert result["operation"]["metadata"]["workspaceDismissed"] is True
    assert captured["values"]["stage"] == "COMPLETE"
    assert captured["values"]["metadata"] == {"workspaceDismissed": True}
    assert operation.metadata["hardcore"] == ["one"]


def test_retry_failed_endpoint_uses_server_side_partial_batch_state(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch", status="PARTIAL",
    )
    queued = SimpleNamespace(**{**operation.__dict__, "status": "QUEUED"})
    captured = {}

    class Repository:
        def begin_explicit_failed_retry(self, operation_id, **scope):
            captured.update(operation_id=operation_id, scope=scope)
            return queued, True

    class Service:
        repository = Repository()
        def get(self, operation_id, **scope): return operation
        def payload(self, value): return {"operationId": str(value.operation_id), "status": value.status}

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})
    result = content_studio.retry_failed_explicit_batch_items(str(operation.operation_id))
    assert result["operation"]["status"] == "QUEUED"
    assert result["reused"] is False
    assert captured == {"operation_id": operation.operation_id, "scope": {"creator_profile_id": 2}}


def test_retry_failed_endpoint_returns_existing_active_cycle_on_double_click(monkeypatch):
    operation = SimpleNamespace(
        operation_id=uuid4(), operation_type="content_studio_explicit_batch", status="RUNNING",
    )

    class Repository:
        def begin_explicit_failed_retry(self, operation_id, **scope): return operation, False

    class Service:
        repository = Repository()
        def get(self, operation_id, **scope): return operation
        def payload(self, value): return {"operationId": str(value.operation_id), "status": value.status}

    monkeypatch.setattr("app.services.background_operation_service.BackgroundOperationService", Service)
    monkeypatch.setattr(content_studio, "_current_account_id", lambda: 3)
    monkeypatch.setattr(content_studio, "get_active_creator_profile", lambda account: {"id": 2})
    result = content_studio.retry_failed_explicit_batch_items(str(operation.operation_id))
    assert result["reused"] is True
