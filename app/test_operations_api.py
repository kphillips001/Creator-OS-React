from datetime import datetime, timedelta, timezone
from pathlib import Path
import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import operations as api
from app.models.system_health import HealthCheck, HealthSection, SystemHealthReport
from app.models.worker_heartbeat import WorkerHeartbeat, WorkerHeartbeatStatus
from uuid import UUID
from app.services.operations_workspace_service import OperationsWorkspaceService


NOW = datetime(2026, 7, 19, 12, 0, tzinfo=timezone.utc)


class FakeHealth:
    def build_report(self):
        provider = HealthSection("Provider Connectivity", (HealthCheck("Telegram Provider", "warning", "Authentication Required"),))
        configuration = HealthSection("Configuration", (HealthCheck("Fanvue", "healthy", "Configured"),))
        database = HealthSection("Database", (HealthCheck("Database Connection", "healthy", "Connected"),))
        return SystemHealthReport("warning", 97, "1 Warning", (provider, configuration, database), warnings=provider.checks)


class FakeRuntime:
    def build_snapshot(self, **kwargs):
        return {"creator_profile_id": str(kwargs["creator_profile_id"]), "runtime_status": "observe", "current_mode": "observe", "current_runtime_provider": "telegram", "last_started": NOW}


class FakeSafety:
    behavior_config = {"global_automation_enabled": True, "global_sends_enabled": False, "manual_pause_enabled": False}
    def check_global_safety(self): return {"allowed": False, "blocked": True, "reason": "global_sends_disabled"}
    can_send_chat = check_global_safety; can_send_monetization = check_global_safety; can_send_mass_ppv = check_global_safety
    can_send_post_purchase_reaction = check_global_safety; can_send_delayed_followup = check_global_safety
    can_send_outreach = check_global_safety; can_send_reactivation = check_global_safety


class FakeDelayed:
    def build_dashboard(self, **kwargs):
        return SimpleNamespace(summary={}, recent_rows=({"id": 1, "fanvue_account_id": kwargs["fanvue_account_id"], "status": "failed", "last_error": "send failed", "retry_count": 1, "max_retries": 3, "updated_at": NOW},))


class FakeMass:
    def build_dashboard(self, **kwargs):
        return SimpleNamespace(queue_rows=({"id": 2, "fanvue_account_id": kwargs["fanvue_account_id"], "status": "processing", "processing_started_at": NOW - timedelta(hours=1)},), campaign_rows=(), analytics_rows=())


class FakeWall:
    def build_dashboard(self, **kwargs): return SimpleNamespace(queue_rows=(), counts={})


class FakePublishing:
    def list_queue_items(self, **kwargs): return ()


class FakeAutomation: pass
class FakeDeliveries:
    def list_events(self): return ()


class FakeHeartbeats:
    def list_latest_per_worker(self, **kwargs):
        return (WorkerHeartbeat(heartbeat_id=UUID("00000000-0000-0000-0000-000000000001"), worker_name="FastAPI", worker_instance_id="fastapi-1", worker_type="application_runtime", host_name="test-host", status=WorkerHeartbeatStatus.RUNNING, started_at=NOW, last_heartbeat_at=NOW, process_id=42),)


def service(launcher_state_path=None):
    return OperationsWorkspaceService(health_service=FakeHealth(), runtime_service=FakeRuntime(), safety_service=FakeSafety(), delayed_service=FakeDelayed(), mass_ppv_service=FakeMass(), wall_service=FakeWall(), publishing_repository=FakePublishing(), publishing_automation_service=FakeAutomation(), outreach_reader=lambda account, limit: [{"id": 3, "fanvue_account_id": account, "queue_status": "pending", "created_at": NOW}], webhook_reader=lambda account, limit: [{"id": 4, "fanvue_account_id": account, "status": "processed", "received_at": NOW, "processed_at": NOW}], delivery_repository=FakeDeliveries(), heartbeat_repository=FakeHeartbeats(), launcher_state_path=launcher_state_path, now=lambda: NOW)


def test_read_projections_report_unknown_heartbeats_and_persisted_failures():
    workspace = service()
    workers = workspace.workers(account_id=7)
    assert next(item for item in workers["items"] if item["name"] == "FastAPI")["heartbeatStatus"] == "healthy"
    assert next(item for item in workers["items"] if item["name"] == "Telegram")["heartbeatStatus"] == "untracked"
    queues = workspace.queues(account_id=7)
    assert next(item for item in queues["items"] if item["name"] == "Mass PPV")["stale"] == 1
    failures = workspace.failures(account_id=7)
    assert any(item["source"] == "Delayed Messages" and item["error"] == "send failed" for item in failures["items"])
    overview = workspace.overview(account_id=7)
    assert overview["globalSends"] is False and overview["runtimeMode"] == "observe"


def test_operations_api_is_get_only_and_exposes_six_sections(monkeypatch):
    app = FastAPI(); app.include_router(api.router)
    monkeypatch.setattr(api, "_workspace_service", service); monkeypatch.setattr(api, "_account_id", lambda: 7)
    client = TestClient(app)
    for section in ("overview", "runtime", "workers", "queues", "publishing", "failures"):
        assert client.get(f"/api/v1/operations/{section}").status_code == 200
        assert client.post(f"/api/v1/operations/{section}").status_code == 405


def test_operations_sources_do_not_import_execution_or_mutation_services():
    source = Path("app/services/operations_workspace_service.py").read_text(encoding="utf-8")
    forbidden = ("WorkerService", "WorkerLoopService", "ConversationGateway", "DecisionEngine", "mark_webhook", "mark_outreach", ".start(", ".stop(", ".observe(", "send_message", "process_pending_events")
    assert all(token not in source for token in forbidden)


def test_worker_projection_includes_read_only_launcher_state(tmp_path):
    state = tmp_path / "launcher_state.json"
    state.write_text(json.dumps({"outreach": {"workerName": "Outreach", "launcherEnabled": True,
        "expectedStartupMethod": "python -m app.workers.outreach_queue", "lastLauncherAction": "startup_failed",
        "lastLauncherActionAt": NOW.isoformat(), "startupFailure": "Heartbeat timeout",
        "configurationBlocked": False}}), encoding="utf-8")
    item = next(row for row in service(state).workers(account_id=7)["items"] if row["name"] == "Outreach")
    assert item["launcherManaged"] is True and item["launcherEnabled"] is True
    assert item["expectedStartupMethod"].endswith("app.workers.outreach_queue")
    assert item["startupFailure"] == "Heartbeat timeout"
