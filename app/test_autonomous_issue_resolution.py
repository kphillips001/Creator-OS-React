from uuid import uuid4

import pytest

from app.services.autonomous_issue_resolution_service import (
    AutonomousIssueResolutionService,
)


class Repo:
    def __init__(self):
        self.row = None

    def create(self, **values):
        self.row = {"resolution_id": uuid4(), **values}
        return self.row

    def attach_execution(self, resolution_id, **values):
        self.row.update({
            "developer_agent_task_id": values["task_id"],
            "developer_agent_execution_id": values["execution_id"],
        })
        return self.row

    def get(self, resolution_id):
        return self.row

    def finalize(self, resolution_id, **values):
        self.row.update(values)
        return self.row


class Agent:
    def __init__(self):
        self.calls = 0

    def create_and_dispatch(self, **values):
        self.calls += 1
        return {
            "task": {"task_id": uuid4()},
            "execution": {"execution_id": uuid4(), "status": "QUEUED"},
        }


class Executions:
    def __init__(self, status="COMPLETED"):
        self.status = status

    def get_execution(self, execution_id):
        return {"status": self.status, "failure_reason": "failed"}


def diagnostics(status="Warning"):
    return {
        "generatedAt": "2026-07-26T12:00:00Z",
        "systemHealth": [{"label": "Workers", "status": status}],
        "problems": [] if status == "Healthy" else [{"title": "Workers"}],
    }


def issue(evidence="One persisted worker failed.", *, automatic=True, classification="WORKER_HEALTH_FAILURE"):
    return {
        "component": "Workers", "summary": evidence, "evidence": evidence,
        "classification": classification,
        "root_cause": evidence,
        "automatic_resolution": automatic,
        "resolution_reason": "Repository repair is supported." if automatic else "Operator action is required.",
        "recommended_action": "Repair the worker.",
    }


def test_already_resolved_does_not_dispatch():
    repository, agent = Repo(), Agent()
    result = AutonomousIssueResolutionService(
        repository=repository, developer_agent=agent,
    ).resolve(
        issue=issue(), current_diagnostics=diagnostics("Healthy"),
        investigation_package="investigate", implementation_task="fix",
    )
    assert result["resolution"]["decision"] == "ALREADY_RESOLVED"
    assert result["execution"] is None
    assert agent.calls == 0


def test_configuration_required_does_not_dispatch():
    repository, agent = Repo(), Agent()
    result = AutonomousIssueResolutionService(
        repository=repository, developer_agent=agent,
    ).resolve(
        issue=issue(
            "OAuth credential configuration is missing.", automatic=False,
            classification="CONFIGURATION_REQUIRED",
        ),
        current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    assert result["resolution"]["decision"] == "CONFIGURATION_REQUIRED"
    assert agent.calls == 0


def test_not_fixable_without_evidence_does_not_dispatch():
    repository, agent = Repo(), Agent()
    result = AutonomousIssueResolutionService(
        repository=repository, developer_agent=agent,
    ).resolve(
        issue={"component": "Workers", "summary": "", "evidence": "",
               "classification": "UNKNOWN_INTERNAL_FAILURE",
               "automatic_resolution": False},
        current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    assert result["resolution"]["decision"] == "NOT_FIXABLE"
    assert agent.calls == 0


def test_stale_projection_never_dispatches():
    repository, agent = Repo(), Agent()
    result = AutonomousIssueResolutionService(
        repository=repository, developer_agent=agent,
    ).resolve(
        issue=issue(automatic=False, classification="STALE_CACHE"),
        current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    assert result["resolution"]["decision"] == "NOT_FIXABLE"
    assert agent.calls == 0


def test_auto_fix_dispatches_and_persists_execution():
    repository, agent = Repo(), Agent()
    result = AutonomousIssueResolutionService(
        repository=repository, developer_agent=agent,
    ).resolve(
        issue=issue(), current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    assert result["resolution"]["decision"] == "AUTO_FIX"
    assert result["resolution"]["developer_agent_execution_id"] == result["execution"]["execution_id"]
    assert agent.calls == 1


@pytest.mark.parametrize(
    ("fresh_status", "validation", "outcome"),
    [("Healthy", "PASSED", "RESOLVED"),
     ("Warning", "FAILED", "PARTIALLY_RESOLVED")],
)
def test_validation_uses_fresh_diagnostics(fresh_status, validation, outcome):
    repository = Repo()
    service = AutonomousIssueResolutionService(
        repository=repository, developer_agent=Agent(),
        execution_repository=Executions(),
    )
    created = service.resolve(
        issue=issue(), current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    result = service.validate(
        created["resolution"]["resolution_id"],
        current_diagnostics=diagnostics(fresh_status),
    )
    assert result["validation_status"] == validation
    assert result["outcome"] == outcome


def test_failed_execution_cannot_report_success():
    repository = Repo()
    service = AutonomousIssueResolutionService(
        repository=repository, developer_agent=Agent(),
        execution_repository=Executions("FAILED"),
    )
    created = service.resolve(
        issue=issue(), current_diagnostics=diagnostics(),
        investigation_package="investigate", implementation_task="fix",
    )
    result = service.validate(
        created["resolution"]["resolution_id"],
        current_diagnostics=diagnostics("Healthy"),
    )
    assert result["validation_status"] == "FAILED"
    assert result["outcome"] == "COULD_NOT_RESOLVE"
