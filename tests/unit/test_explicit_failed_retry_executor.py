from types import SimpleNamespace
from uuid import uuid4

from app.services.explicit_failed_retry_background_executor import ExplicitFailedRetryBackgroundExecutor


def operation(status="RUNNING"):
    parent_id = uuid4()
    return SimpleNamespace(
        operation_id=parent_id, operation_type="content_studio_explicit_batch",
        creator_profile_id=2, account_id=3, status=status, worker_id="worker-1",
        metadata={
            "items": [
                {"id": "item-1", "ordinal": 0, "status": "completed", "jobId": "success-child", "imageUrl": "/success", "error": ""},
                {"id": "item-2", "ordinal": 1, "status": "pending", "jobId": "failed-child", "imageUrl": "", "error": "",
                 "attempts": [{"attemptNumber": 1, "operationId": "failed-child", "status": "failed", "error": "old failure"}]},
            ],
            "retryCycle": {"cycleId": f"{parent_id}:retry:1", "cycleNumber": 1, "status": "ACTIVE",
                           "failedItemIds": ["item-2"], "failedItemCount": 1},
        },
    )


def mixed_operation(*, failed_count=8):
    parent_id = uuid4()
    successful_count = 12 - failed_count
    items = []
    failed_ids = []
    for ordinal in range(12):
        item_id = f"item-{ordinal + 1}"
        if ordinal < successful_count:
            items.append({
                "id": item_id, "ordinal": ordinal, "status": "completed",
                "jobId": f"success-child-{ordinal + 1}",
                "imageUrl": f"/success/{ordinal + 1}", "error": "",
            })
            continue
        failed_ids.append(item_id)
        items.append({
            "id": item_id, "ordinal": ordinal, "status": "pending",
            "jobId": f"failed-child-{ordinal + 1}", "imageUrl": "", "error": "",
            "attempts": [{
                "attemptNumber": 1, "operationId": f"failed-child-{ordinal + 1}",
                "status": "failed", "error": "old failure",
            }],
        })
    return SimpleNamespace(
        operation_id=parent_id, operation_type="content_studio_explicit_batch",
        creator_profile_id=2, account_id=3, status="RUNNING", worker_id="worker-1",
        metadata={
            "items": items,
            "retryCycle": {
                "cycleId": f"{parent_id}:retry:1", "cycleNumber": 1,
                "status": "ACTIVE", "failedItemIds": failed_ids,
                "failedItemCount": len(failed_ids),
            },
        },
    )


class FakeRepository:
    def __init__(self, parent, *, retry_succeeds=True):
        self.parent = parent; self.retry_succeeds = retry_succeeds; self.children = {}

    def _one_unscoped(self, operation_id):
        if str(operation_id) == str(self.parent.operation_id): return self.parent
        if str(operation_id).startswith("failed-child"):
            return SimpleNamespace(metadata={"request": {"provider": "seedream_5_0_pro", "promptBatch": ["durable prompt"]}})
        return self.children.get(str(operation_id))

    def latest_by_idempotency(self, **_): return None
    def transition(self, operation_id, status, **values):
        child = self.children[str(operation_id)]
        child.status = status
        return child
    def renew_lease(self, *_args, **_kwargs): return True


class FakeOperations:
    def __init__(self, parent, *, retry_succeeds=True):
        self.repository = FakeRepository(parent, retry_succeeds=retry_succeeds)
        self.created = []; self.completed = False; self.cancelled = False

    def create(self, **values):
        child = SimpleNamespace(
            operation_id=uuid4(), status="QUEUED", metadata=dict(values["metadata"]),
            error_message=None, result_reference=None, attempt_count=0,
        )
        self.repository.children[str(child.operation_id)] = child
        self.created.append(values)
        return child, True

    def progress(self, operation_id, **values):
        self.repository.parent.metadata = {**self.repository.parent.metadata, **dict(values.get("metadata") or {})}
        return self.repository.parent

    def succeed(self, operation_id, *, partial=False, metadata=None, **_):
        self.repository.parent.status = "PARTIAL" if partial else "SUCCEEDED"
        self.repository.parent.metadata = {**self.repository.parent.metadata, **dict(metadata or {})}
        return self.repository.parent

    def complete_explicit_batch(self, operation_id, *, metadata=None, **_):
        self.completed = True; self.repository.parent.status = "SUCCEEDED"
        self.repository.parent.metadata = {**self.repository.parent.metadata, **dict(metadata or {})}
        return self.repository.parent

    def cancel(self, operation_id, message):
        self.cancelled = True; self.repository.parent.status = "CANCELLED"
        return self.repository.parent


def fake_child_execute(self, child, operations, *, worker_id):
    child.result_reference = f"generation-job-{child.operation_id}"
    if operations.repository.retry_succeeds:
        child.status = "SUCCEEDED"
        child.metadata = {**child.metadata, "outputReferences": ["https://cdn.test/retry.png"]}
    else:
        child.status = "FAILED"; child.error_message = "retry failed"


def test_retries_only_failed_slot_and_preserves_success_and_history(monkeypatch):
    parent = operation(); operations = FakeOperations(parent)
    monkeypatch.setattr("app.services.content_studio_background_executor.ContentStudioBackgroundExecutor.execute", fake_child_execute)
    ExplicitFailedRetryBackgroundExecutor().execute(parent, operations, worker_id="worker-1")
    assert len(operations.created) == 1
    assert operations.created[0]["metadata"]["request"]["promptBatch"] == ["durable prompt"]
    items = parent.metadata["items"]
    assert items[0]["jobId"] == "success-child" and items[0]["imageUrl"] == "/success"
    assert items[1]["status"] == "completed" and items[1]["imageUrl"].endswith("/images/0")
    assert [attempt["status"] for attempt in items[1]["attempts"]] == ["failed", "completed"]
    assert parent.status == "SUCCEEDED" and operations.completed is True


def test_second_failed_attempt_remains_retryable(monkeypatch):
    parent = operation(); operations = FakeOperations(parent, retry_succeeds=False)
    monkeypatch.setattr("app.services.content_studio_background_executor.ContentStudioBackgroundExecutor.execute", fake_child_execute)
    ExplicitFailedRetryBackgroundExecutor().execute(parent, operations, worker_id="worker-1")
    item = parent.metadata["items"][1]
    assert item["status"] == "failed"
    assert [attempt["status"] for attempt in item["attempts"]] == ["failed", "failed"]
    assert parent.status == "PARTIAL"


def test_stop_before_next_retry_submission_preserves_existing_items():
    parent = operation(status="CANCEL_REQUESTED"); operations = FakeOperations(parent)
    ExplicitFailedRetryBackgroundExecutor().execute(parent, operations, worker_id="worker-1")
    assert operations.created == []
    assert operations.cancelled is True
    assert parent.metadata["items"][0]["status"] == "completed"


def test_one_cycle_attempts_all_eight_failed_slots_even_when_individual_items_fail(monkeypatch):
    parent = mixed_operation(failed_count=8)
    operations = FakeOperations(parent)
    attempted_subjects = []

    def mixed_child_execute(self, child, services, *, worker_id):
        attempted_subjects.append(child.metadata["parentExplicitItemId"])
        child.result_reference = f"generation-job-{child.operation_id}"
        # First, middle, and final item failures must not terminate the cycle.
        if len(attempted_subjects) in {1, 5, 8}:
            child.status = "FAILED"
            child.error_message = f"retry failure {len(attempted_subjects)}"
            return
        child.status = "SUCCEEDED"
        child.metadata = {
            **child.metadata,
            "outputReferences": [f"https://cdn.test/{len(attempted_subjects)}.png"],
        }

    monkeypatch.setattr(
        "app.services.content_studio_background_executor.ContentStudioBackgroundExecutor.execute",
        mixed_child_execute,
    )
    ExplicitFailedRetryBackgroundExecutor().execute(parent, operations, worker_id="worker-1")

    assert attempted_subjects == [f"item-{index}" for index in range(5, 13)]
    assert len(operations.created) == 8
    assert all(item["jobId"].startswith("success-child") for item in parent.metadata["items"][:4])
    assert [len(item.get("attempts") or ()) for item in parent.metadata["items"][4:]] == [2] * 8
    assert parent.status == "PARTIAL"
    assert parent.metadata["completedIdeas"] == 9
    assert parent.metadata["failedIdeas"] == 3
    assert parent.metadata["retryCycle"]["status"] == "COMPLETED"
