from unittest.mock import Mock

from app.repositories.generation_library_record_repository import (
    GenerationLibraryRecordRepository,
)
from app.services.operations_workspace_service import OperationsWorkspaceService


class Cursor:
    def __init__(self):
        self.sql = ""

    def execute(self, sql, _params=None):
        self.sql = sql
        return self

    def fetchone(self):
        return {"active": 4, "staged": 3, "archived": 2}

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


class Connection:
    def __init__(self, cursor):
        self.value = cursor

    def cursor(self):
        return self.value

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_generation_library_overview_counts_never_select_record_payload():
    cursor = Cursor()
    repository = GenerationLibraryRecordRepository(
        connection_factory=lambda: Connection(cursor),
    )
    assert repository.overview_counts() == {
        "active": 4, "staged": 3, "archived": 2,
    }
    assert "record_payload" not in cursor.sql
    assert "COUNT(*) FILTER" in cursor.sql


def test_operations_overview_reuses_health_evidence_and_publishing_once():
    service = OperationsWorkspaceService()
    health = {
        "overallStatus": "healthy", "score": 100,
        "sections": [{"name": "Database", "checks": [{
            "name": "Database Connection", "status": "healthy",
        }]}],
        "providerWarnings": [], "configurationWarnings": [],
        "failingChecks": [],
    }
    evidence = {key: [] for key in (
        "outreach", "delayed", "massPpv", "wall", "publishing", "webhooks",
    )}
    publishing = {"items": [], "summary": {"attention": 0}}
    service._health = Mock(return_value=health)
    service._evidence = Mock(return_value=evidence)
    service.runtime = Mock(return_value={
        "snapshot": {"currentMode": "LIVE"},
        "effectiveGlobalSafety": {"allowed": True},
        "globalAutomation": True, "globalSends": True, "manualPause": False,
    })
    service.queues = Mock(return_value={"totals": {"pending": 0}})
    service.publishing = Mock(return_value=publishing)
    service.failures = Mock(return_value={"total": 0})
    service.workers = Mock(return_value={
        "summary": {"healthy": 1}, "warnings": [],
    })

    result = service.overview(account_id=2)

    assert result["healthScore"] == 100
    service._health.assert_called_once_with()
    service._evidence.assert_called_once_with(2)
    service.runtime.assert_called_once_with(account_id=2, health=health)
    service.queues.assert_called_once_with(account_id=2, evidence=evidence)
    service.failures.assert_called_once_with(
        account_id=2, evidence=evidence, health=health, publishing=publishing,
    )
    service.workers.assert_called_once_with(account_id=2, evidence=evidence)
