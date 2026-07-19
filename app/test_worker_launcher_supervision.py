from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from app.models.worker_heartbeat import WorkerHeartbeat, WorkerHeartbeatStatus
from app.services.worker_launcher_supervision_service import WORKERS, WorkerLauncherSupervisionService


class Clock:
    def __init__(self): self.value = datetime(2026, 7, 19, tzinfo=timezone.utc)
    def now(self): return self.value
    def sleep(self, seconds): self.value += timedelta(seconds=max(seconds, 1))


class Process:
    def __init__(self, pid): self.pid = pid


class Processes:
    def __init__(self):
        self.started = []; self.running = set(); self.matches_by_module = {}; self.graceful = []; self.forced = []
        self.stop_on_graceful = True
    def start(self, command, **_):
        pid = 100 + len(self.started); self.started.append(command); self.running.add(pid)
        definition = next(item for item in WORKERS if item.module in command)
        self.matches_by_module[definition.module] = pid
        return Process(pid)
    def exists(self, pid): return pid in self.running
    def matches(self, pid, definition): return pid in self.running and self.matches_by_module.get(definition.module, pid) == pid
    def matching(self, definition): return [pid for pid in self.running if self.matches_by_module.get(definition.module) == pid]
    def graceful_stop(self, pid):
        self.graceful.append(pid)
        if self.stop_on_graceful: self.running.discard(pid)
    def force_stop(self, pid): self.forced.append(pid); self.running.discard(pid)


class Heartbeats:
    def __init__(self, processes, clock): self.processes = processes; self.clock = clock; self.rows = []; self.auto_register = True
    def list_latest_per_worker(self, **_):
        if self.auto_register and self.processes.started:
            command = self.processes.started[-1]
            definition = next(item for item in WORKERS if item.module in command)
            pid = max(self.processes.running)
            if not any(row.process_id == pid for row in self.rows): self.rows.append(heartbeat(definition, pid, self.clock.now()))
        return tuple(reversed(self.rows))


def heartbeat(definition, pid, at, status=WorkerHeartbeatStatus.RUNNING):
    return WorkerHeartbeat(heartbeat_id=uuid4(), worker_name=definition.heartbeat_name,
        worker_instance_id=f"{definition.key}-{pid}", worker_type="queue_worker",
        creator_profile_id=None, account_id=None, process_id=pid, host_name="test",
        application_version=None, status=status, started_at=at, last_heartbeat_at=at,
        metadata={"stale_threshold_seconds": 60})


def service(tmp_path, environment=None):
    clock = Clock(); processes = Processes(); heartbeats = Heartbeats(processes, clock)
    value = WorkerLauncherSupervisionService(project_root=tmp_path, environment=environment or {},
        process_adapter=processes, heartbeat_repository=heartbeats, sleep=clock.sleep, now=clock.now)
    return value, processes, heartbeats, clock


def test_authoritative_entry_points_and_defaults_are_safe(tmp_path):
    value, processes, _, _ = service(tmp_path)
    configuration = value.configuration()
    assert all(not item["enabled"] for item in configuration)
    modules = {item["key"]: item["module"] for item in configuration}
    assert modules == {"telegram": "app.integrations.telegram.telethon_runtime",
                       "outreach": "app.workers.outreach_queue", "delayed_messages": "app.workers.delayed_messages",
                       "mass_ppv": "app.workers.mass_ppv", "wall": "app.workers.wall"}
    assert "app.outreach_worker" not in modules.values()
    value.start_enabled()
    assert processes.started == []


def test_enabled_worker_requires_healthy_heartbeat(tmp_path):
    definition = WORKERS[1]
    value, processes, heartbeats, _ = service(tmp_path, {definition.environment_switch: "true"})
    started = value.start_worker(definition)
    assert started["lastLauncherAction"] == "started"
    assert started["pid"] == 100
    heartbeats.auto_register = False
    processes.running.clear()
    failed = value.start_worker(definition)
    assert failed["lastLauncherAction"] == "startup_failed"
    assert processes.forced


def test_healthy_live_heartbeat_blocks_duplicate_but_stale_history_does_not(tmp_path):
    definition = WORKERS[2]
    value, processes, heartbeats, clock = service(tmp_path, {definition.environment_switch: "true"})
    processes.running.add(77); processes.matches_by_module[definition.module] = 77
    heartbeats.rows = [heartbeat(definition, 77, clock.now())]
    result = value.start_worker(definition)
    assert result["lastLauncherAction"] == "already_running" and not processes.started
    processes.running.clear(); heartbeats.rows[0] = heartbeat(definition, 77, clock.now() - timedelta(minutes=10))
    result = value.start_worker(definition)
    assert result["lastLauncherAction"] == "started"


def test_configuration_block_prevents_telegram_start(tmp_path):
    definition = WORKERS[0]
    value, processes, _, _ = service(tmp_path, {definition.environment_switch: "true"})
    result = value.start_worker(definition)
    assert result["configurationBlocked"] is True
    assert processes.started == []


def test_matching_process_without_healthy_heartbeat_blocks_duplicate_start(tmp_path):
    definition = WORKERS[4]
    value, processes, heartbeats, _ = service(tmp_path, {definition.environment_switch: "true"})
    heartbeats.auto_register = False
    processes.running.add(88); processes.matches_by_module[definition.module] = 88
    result = value.start_worker(definition)
    assert result["lastLauncherAction"] == "startup_blocked"
    assert processes.started == []


def test_graceful_and_forced_shutdown_validate_owned_pid(tmp_path):
    definition = WORKERS[3]
    value, processes, heartbeats, clock = service(tmp_path, {definition.environment_switch: "true"})
    processes.running.add(51); processes.matches_by_module[definition.module] = 51
    heartbeats.auto_register = False
    heartbeats.rows = [heartbeat(definition, 51, clock.now(), WorkerHeartbeatStatus.STOPPED)]
    result = value.stop_worker(definition, 51)
    assert result["lastLauncherAction"] == "stopped" and processes.graceful == [51]
    processes.running.add(52); processes.matches_by_module[definition.module] = 52; processes.stop_on_graceful = False
    heartbeats.rows = [heartbeat(definition, 52, clock.now())]
    result = value.stop_worker(definition, 52)
    assert result["lastLauncherAction"] == "force_stopped" and processes.forced == [52]
    processes.running.add(999)
    result = value.stop_worker(definition, 999)
    assert result["lastLauncherAction"] == "shutdown_blocked" and 999 not in processes.forced


def test_reverse_shutdown_and_startup_order_and_no_runtime_mutation(tmp_path):
    environment = {item.environment_switch: "true" for item in WORKERS}
    environment.update({"TG_API_ID": "1", "TG_API_HASH": "hash", "AVA_FANVUE_ACCOUNT_ID": "2"})
    original = dict(environment)
    value, processes, heartbeats, clock = service(tmp_path, environment)
    assert [item["workerName"] for item in value.start_enabled()] == [item.name for item in WORKERS]
    state = value._load_state()
    heartbeats.auto_register = False
    for definition in WORKERS:
        pid = state[definition.key]["pid"]; processes.matches_by_module[definition.module] = pid
        heartbeats.rows.append(heartbeat(definition, pid, clock.now(), WorkerHeartbeatStatus.STOPPED))
    stopped = value.stop_managed()
    assert [item["workerName"] for item in stopped] == [item.name for item in reversed(WORKERS)]
    assert environment == original
    assert not any(key in environment for key in ("GLOBAL_SENDS_ENABLED", "GLOBAL_AUTOMATION_ENABLED", "RUNTIME_MODE"))


def test_supervision_boundary_contains_no_queue_or_send_mutation():
    import inspect
    from app.services import worker_launcher_supervision_service

    source = inspect.getsource(worker_launcher_supervision_service)
    for forbidden in ("claim_due_items", "release_claim", "recover_stale_claims", "send_message",
                      "GLOBAL_SENDS_ENABLED =", "GLOBAL_AUTOMATION_ENABLED =", "RUNTIME_MODE ="):
        assert forbidden not in source
