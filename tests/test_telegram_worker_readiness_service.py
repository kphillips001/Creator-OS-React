from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest

from app.models.worker_heartbeat import WorkerHeartbeat, WorkerHeartbeatStatus
from app.services.telegram_worker_readiness_service import TelegramWorkerReadinessService


NOW = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)


class Heartbeats:
    def __init__(self, rows):
        self.rows = rows

    def list_recent_instances(self, *, since):
        return tuple(row for row in self.rows if row.last_heartbeat_at >= since)


class Processes:
    def __init__(self, *, matches=True, matching=None):
        self.owned = matches
        self.matches_list = [68032] if matching is None else matching

    def matches(self, pid, definition):
        return self.owned and pid in self.matches_list and definition.module.endswith("telethon_runtime")

    def matching(self, definition):
        return list(self.matches_list)


def heartbeat(*, status=WorkerHeartbeatStatus.IDLE, age=1, creator="1", account=2,
              metadata=None, error=None, instance="telegram-current", pid=68032):
    values = {
        "stale_threshold_seconds": 90,
        "account_scope": "AVA_TELETHON_PRIVATE",
        "authorized": True,
        "database_healthy": True,
        "lifecycle_state": "CONNECTED",
    }
    values.update(metadata or {})
    return WorkerHeartbeat(
        heartbeat_id=uuid4(), worker_name="Telegram", worker_instance_id=instance,
        worker_type="transport_runtime", creator_profile_id=creator,
        account_id=account, process_id=pid, host_name="host", status=status,
        started_at=NOW - timedelta(minutes=2),
        last_heartbeat_at=NOW - timedelta(seconds=age), last_error=error,
        metadata=values,
    )


def launcher(tmp_path, **overrides):
    value = {
        "workerName": "Telegram", "launcherEnabled": True, "pid": 68032,
        "instanceId": "telegram-current", "lastLauncherAction": "healthy",
        "startupFailure": None, "configurationBlocked": False,
        "crashLoopBlocked": False, "error": None,
    }
    value.update(overrides)
    path = tmp_path / "launcher.json"
    path.write_text(json.dumps({"telegram": value}), encoding="utf-8")
    return path


def service(tmp_path, rows, *, processes=None, launch=None, environment=None):
    return TelegramWorkerReadinessService(
        heartbeat_repository=Heartbeats(rows), process_adapter=processes or Processes(),
        launcher_state_path=launch or launcher(tmp_path), now=lambda: NOW,
        creator_profile_reader=lambda _account: {"id": 1},
        environment=environment if environment is not None else {
            "CREATOR_OS_LAUNCH_TELEGRAM": "true", "TG_API_ID": "1",
            "TG_API_HASH": "hash", "AVA_FANVUE_ACCOUNT_ID": "2",
        },
    )


def test_production_shaped_singleton_is_ready(tmp_path):
    result = service(tmp_path, [heartbeat()]).read(creator_profile_id=1)
    assert result["ready"] is True
    assert result["status"] == "idle"
    assert result["processId"] == 68032


@pytest.mark.parametrize(("change", "code"), [
    ({"metadata": {"lifecycle_state": "DISCONNECTED"}}, "disconnected"),
    ({"metadata": {"authorized": False}}, "unauthorized"),
    ({"metadata": {"database_healthy": False}}, "database_unhealthy"),
    ({"age": 91}, "no_singleton_runtime"),
    ({"status": WorkerHeartbeatStatus.FAILED}, "no_singleton_runtime"),
    ({"creator": "99"}, "wrong_account_scope"),
    ({"account": 99}, "wrong_account_scope"),
])
def test_heartbeat_failures_remain_blocked(tmp_path, change, code):
    result = service(tmp_path, [heartbeat(**change)]).read(creator_profile_id=1)
    assert result["ready"] is False
    assert result["code"] == code


@pytest.mark.parametrize("launcher_change", [
    {"lastLauncherAction": "startup_failed", "startupFailure": "boom"},
    {"lastLauncherAction": "crash_loop_blocked", "crashLoopBlocked": True},
    {"lastLauncherAction": "configuration_blocked", "configurationBlocked": True},
])
def test_launcher_failures_remain_blocked(tmp_path, launcher_change):
    result = service(tmp_path, [heartbeat()], launch=launcher(tmp_path, **launcher_change)).read(
        creator_profile_id=1
    )
    assert result["ready"] is False


def test_no_worker_and_duplicate_runtime_are_blocked(tmp_path):
    assert service(tmp_path, []).read(creator_profile_id=1)["ready"] is False
    duplicate = heartbeat(instance="telegram-other", pid=68033)
    result = service(
        tmp_path, [heartbeat(), duplicate],
        processes=Processes(matching=[68032, 68033]),
    ).read(creator_profile_id=1)
    assert result["ready"] is False
    assert result["code"] == "no_singleton_runtime"


def test_process_and_launcher_identity_must_match(tmp_path):
    result = service(tmp_path, [heartbeat()], processes=Processes(matches=False)).read(
        creator_profile_id=1
    )
    assert result["code"] == "no_singleton_runtime"
    result = service(
        tmp_path, [heartbeat()], launch=launcher(tmp_path, pid=999),
    ).read(creator_profile_id=1)
    assert result["code"] == "launcher_identity_mismatch"


def test_configuration_and_missing_launcher_fail_closed(tmp_path):
    result = service(tmp_path, [heartbeat()], environment={}).read(creator_profile_id=1)
    assert result["code"] == "configuration_blocked"
    missing = tmp_path / "missing.json"
    result = service(tmp_path, [heartbeat()], launch=missing).read(creator_profile_id=1)
    assert result["code"] == "launcher_unavailable"
