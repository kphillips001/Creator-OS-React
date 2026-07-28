import time
from pathlib import Path
from uuid import uuid4

import pytest

import app.services.developer_agent_execution_service as service_module
from app.services.codex_developer_agent_adapter import CodexExecutionResult
from app.services.developer_agent_execution_service import (
    DeveloperAgentExecutionService,
)


class FakeAdapter:
    def __init__(self, *, available=True, fail=False):
        self.available = available
        self.fail = fail
        self.calls = []

    async def health(self, repository):
        return {
            "cliDetected": self.available, "sdkDetected": self.available,
            "authenticationAvailable": self.available,
            "appServerReachable": self.available,
            "reason": "Ready" if self.available else "SDK unavailable",
        }

    async def execute(
        self, *, prompt, repository, on_session=None, on_event=None,
    ):
        self.calls.append((prompt, repository))
        if self.fail:
            raise RuntimeError("real adapter failure")
        if on_session:
            on_session("session-1")
        if on_event:
            on_event({
                "type": "commandExecution",
                "command": "pytest -q",
                "status": "completed",
                "exit_code": 0,
            })
        return CodexExecutionResult(
            session_id="session-1", status="completed",
            final_response="Verified completion.", events=(), duration_ms=15,
            error=None,
        )


class FakeRepository:
    def __init__(self, approved=False):
        self.task_id = uuid4()
        self.execution_id = uuid4()
        self.task = {
            "task_id": self.task_id, "issue_identifier": "Database",
            "investigation_package": "Evidence", "implementation_task": "Inspect repository.",
            "repository_path": "", "expected_branch": "react-migration",
            "status": "APPROVED" if approved else "AWAITING_APPROVAL",
            "approved_at": object() if approved else None,
        }
        self.execution = None
        self.events = []
        self.notifications = []

    def persistence_ready(self):
        return True

    def get_task(self, task_id):
        return self.task if task_id == self.task_id else None

    def approve_task(self, task_id):
        self.task.update(status="APPROVED", approved_at=object())
        return self.task

    def create_execution(self, **values):
        self.execution = {
            "execution_id": self.execution_id, "task_id": self.task_id,
            "status": "QUEUED", "initial_head": "head-1", **values,
        }
        return dict(self.execution)

    def update_execution(self, execution_id, **changes):
        self.execution.update(changes)
        return self.execution

    def get_execution(self, execution_id):
        return self.execution

    def add_event(self, execution_id, event_type, message, event_data=None):
        item = {"event_type": event_type, "message": message, "event_data": event_data or {}}
        self.events.append(item)
        return item

    def list_events(self, execution_id):
        return self.events

    def create_notification(self, **values):
        self.notifications.append(values)
        return values

    def create_task(self, **values):
        self.task.update(
            values,
            status="AWAITING_APPROVAL",
            approved_at=None,
        )
        self.notifications.append({
            "notification_type": "TASK_AWAITING_APPROVAL",
        })
        return dict(self.task)


@pytest.fixture
def safe_repository(tmp_path, monkeypatch):
    repository = tmp_path / "repo"
    repository.mkdir()
    (repository / ".git").mkdir()
    monkeypatch.setattr(service_module, "REPOSITORY_PATH", repository)
    return repository


def service(repository, adapter, path, monkeypatch):
    instance = DeveloperAgentExecutionService(
        repository=repository, adapter=adapter, repository_path=path,
    )
    monkeypatch.setattr(
        instance, "_git",
        lambda *args: {
            ("branch", "--show-current"): "react-migration",
            ("status", "--short"): "",
            ("rev-parse", "HEAD"): "head-1",
            ("diff", "--stat"): "",
            ("diff",): "",
        }.get(args, ""),
    )
    monkeypatch.setattr(
        instance, "_git_with_code",
        lambda *args: (
            0,
            "true" if args == ("rev-parse", "--is-inside-work-tree")
            else str(path / ".git") if args == ("rev-parse", "--git-dir")
            else "",
        ),
    )
    return instance


def test_execution_rejected_before_persisted_approval(safe_repository, monkeypatch):
    repository = FakeRepository(approved=False)
    repository.task["repository_path"] = str(safe_repository)
    instance = service(repository, FakeAdapter(), safe_repository, monkeypatch)
    with pytest.raises(PermissionError, match="approval"):
        instance.submit(repository.task_id)


def test_single_operator_dispatch_auto_approves_and_queues(
    safe_repository, monkeypatch,
):
    repository = FakeRepository()
    repository.task["repository_path"] = str(safe_repository)
    instance = service(repository, FakeAdapter(), safe_repository, monkeypatch)
    result = instance.create_and_dispatch(
        issue_identifier="Issue",
        investigation_package="Evidence",
        implementation_task="Inspect repository.",
    )
    assert result["task"]["status"] == "APPROVED"
    assert result["execution"]["status"] == "QUEUED"


def test_manual_approval_mode_persists_without_execution(
    safe_repository, monkeypatch,
):
    repository = FakeRepository()
    repository.task["repository_path"] = str(safe_repository)
    instance = service(repository, FakeAdapter(), safe_repository, monkeypatch)
    result = instance.create_and_dispatch(
        issue_identifier="Issue",
        investigation_package="Evidence",
        implementation_task="Inspect repository.",
        require_manual_approval=True,
    )
    assert result["task"]["status"] == "AWAITING_APPROVAL"
    assert result["execution"] is None


def test_repository_allowlist_and_branch_are_enforced(safe_repository, monkeypatch):
    repository = FakeRepository(approved=True)
    repository.task["repository_path"] = str(safe_repository / "substitute")
    instance = service(repository, FakeAdapter(), safe_repository, monkeypatch)
    with pytest.raises(PermissionError, match="allowlist"):
        instance.submit(repository.task_id)
    repository.task["repository_path"] = str(safe_repository)
    monkeypatch.setattr(instance, "_git", lambda *args: "wrong-branch")
    with pytest.raises(RuntimeError, match="Expected branch"):
        instance.submit(repository.task_id)


def test_unavailable_adapter_never_simulates_completion(safe_repository, monkeypatch):
    repository = FakeRepository(approved=True)
    repository.task["repository_path"] = str(safe_repository)
    instance = service(repository, FakeAdapter(available=False), safe_repository, monkeypatch)
    with pytest.raises(RuntimeError, match="unavailable"):
        instance.submit(repository.task_id)
    assert repository.execution is None


def test_real_adapter_boundary_persists_terminal_evidence(safe_repository, monkeypatch):
    repository = FakeRepository(approved=True)
    repository.task["repository_path"] = str(safe_repository)
    adapter = FakeAdapter()
    instance = service(repository, adapter, safe_repository, monkeypatch)
    result = instance.submit(repository.task_id)
    assert result["status"] == "QUEUED"
    deadline = time.time() + 3
    while repository.execution["status"] not in {"COMPLETED", "FAILED"} and time.time() < deadline:
        time.sleep(0.02)
    assert repository.execution["status"] == "COMPLETED"
    assert adapter.calls == [("Inspect repository.", safe_repository)]
    assert repository.execution["final_report"]["summary"] == "Verified completion."
    assert any(event["event_type"] == "RUNNING_TESTS" for event in repository.events)
    assert repository.execution["codex_session_id"] == "session-1"
    assert any(event["event_type"] == "EXECUTION_COMPLETED" for event in repository.events)
    assert repository.notifications[-1]["notification_type"] == "EXECUTION_COMPLETED"


def test_adapter_failure_is_persisted_and_not_reported_complete(safe_repository, monkeypatch):
    repository = FakeRepository(approved=True)
    repository.task["repository_path"] = str(safe_repository)
    instance = service(repository, FakeAdapter(fail=True), safe_repository, monkeypatch)
    instance.submit(repository.task_id)
    deadline = time.time() + 3
    while repository.execution["status"] not in {"COMPLETED", "FAILED"} and time.time() < deadline:
        time.sleep(0.02)
    assert repository.execution["status"] == "FAILED"
    assert repository.execution["failure_reason"] == "real adapter failure"
    assert repository.execution.get("final_report") is None
    assert repository.notifications[-1]["notification_type"] == "EXECUTION_FAILED"
