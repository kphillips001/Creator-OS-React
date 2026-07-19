"""Process-only supervision for autonomous Creator_OS runtimes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from app.models.worker_heartbeat import WorkerHealthClassification, WorkerHeartbeatStatus
from app.repositories.worker_heartbeat_repository import WorkerHeartbeatRepository
from app.services.worker_heartbeat_service import WorkerHeartbeatService


@dataclass(frozen=True)
class WorkerLaunchDefinition:
    key: str
    name: str
    environment_switch: str
    module: str
    heartbeat_name: str
    startup_timeout: int
    shutdown_timeout: int
    log_name: str
    required_environment: tuple[str, ...] = ()

    @property
    def command(self) -> tuple[str, ...]:
        return (sys.executable, "-m", self.module)


WORKERS = (
    WorkerLaunchDefinition("telegram", "Telegram", "CREATOR_OS_LAUNCH_TELEGRAM",
                           "app.integrations.telegram.telethon_runtime", "Telegram", 60, 30,
                           "telegram.log", ("TG_API_ID", "TG_API_HASH", "AVA_FANVUE_ACCOUNT_ID")),
    WorkerLaunchDefinition("outreach", "Outreach", "CREATOR_OS_LAUNCH_OUTREACH",
                           "app.workers.outreach_queue", "Outreach", 30, 30, "outreach.log"),
    WorkerLaunchDefinition("delayed_messages", "Delayed Messages", "CREATOR_OS_LAUNCH_DELAYED_MESSAGES",
                           "app.workers.delayed_messages", "Delayed Messages", 30, 30, "delayed_messages.log"),
    WorkerLaunchDefinition("mass_ppv", "Mass PPV", "CREATOR_OS_LAUNCH_MASS_PPV",
                           "app.workers.mass_ppv", "Mass PPV", 30, 30, "mass_ppv.log"),
    WorkerLaunchDefinition("wall", "Wall Worker", "CREATOR_OS_LAUNCH_WALL_WORKER",
                           "app.workers.wall", "Wall Worker", 30, 30, "wall_worker.log"),
)


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class ProcessAdapter:
    def start(self, command: tuple[str, ...], *, cwd: Path, stdout, stderr):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        return subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, creationflags=flags)

    @staticmethod
    def exists(pid: int) -> bool:
        try:
            os.kill(pid, 0)
            return True
        except (OSError, ProcessLookupError):
            return False

    @staticmethod
    def command_line(pid: int) -> str:
        if os.name != "nt":
            try: return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode()
            except OSError: return ""
        escaped = str(int(pid))
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {escaped}').CommandLine"],
            capture_output=True, text=True, timeout=5, check=False,
        )
        return result.stdout.strip()

    def matches(self, pid: int, definition: WorkerLaunchDefinition) -> bool:
        return self.exists(pid) and definition.module in self.command_line(pid)

    def matching(self, definition: WorkerLaunchDefinition) -> list[int]:
        if os.name != "nt": return []
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if not result.stdout.strip(): return []
        payload = json.loads(result.stdout)
        rows = payload if isinstance(payload, list) else [payload]
        return [int(row["ProcessId"]) for row in rows if definition.module in str(row.get("CommandLine") or "")]

    @staticmethod
    def graceful_stop(pid: int) -> None:
        if os.name == "nt": os.kill(pid, signal.CTRL_BREAK_EVENT)
        else: os.kill(pid, signal.SIGTERM)

    @staticmethod
    def force_stop(pid: int) -> None:
        if os.name == "nt": subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, check=False)
        else: os.kill(pid, signal.SIGKILL)


class WorkerLauncherSupervisionService:
    def __init__(self, *, project_root: Path | None = None, environment: Mapping[str, str] | None = None,
                 process_adapter: Any | None = None, heartbeat_repository: Any | None = None,
                 sleep: Callable[[float], None] = time.sleep, now: Callable[[], datetime] | None = None):
        self.project_root = project_root or Path(__file__).resolve().parents[2]
        self.environment = environment if environment is not None else os.environ
        self.processes = process_adapter or ProcessAdapter()
        self.heartbeats = heartbeat_repository or WorkerHeartbeatRepository()
        self.sleep = sleep
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.runtime_logs = self.project_root / "logs" / "runtime"
        self.state_path = self.runtime_logs / "launcher_state.json"

    def configuration(self) -> tuple[dict[str, Any], ...]:
        return tuple({**asdict(item), "command": list(item.command),
                      "enabled": _enabled(self.environment.get(item.environment_switch))} for item in WORKERS)

    def start_enabled(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.start_worker(item) for item in WORKERS)

    def stop_managed(self) -> tuple[dict[str, Any], ...]:
        state = self._load_state()
        results = []
        for definition in reversed(WORKERS):
            record = state.get(definition.key) or {}
            if record.get("pid"):
                results.append(self.stop_worker(definition, int(record["pid"])))
        return tuple(results)

    def start_worker(self, definition: WorkerLaunchDefinition) -> dict[str, Any]:
        if not _enabled(self.environment.get(definition.environment_switch)):
            return self._record(definition, "disabled", launcher_enabled=False, pid=None)
        missing = [name for name in definition.required_environment if not str(self.environment.get(name) or "").strip()]
        if missing:
            return self._record(definition, "configuration_blocked", launcher_enabled=True, pid=None,
                                error="Missing required configuration: " + ", ".join(missing))
        live = self._healthy_live_heartbeat(definition)
        if live:
            return self._record(definition, "already_running", launcher_enabled=True,
                                pid=live.process_id, instance_id=live.worker_instance_id)
        matches = self.processes.matching(definition)
        if matches:
            return self._record(definition, "startup_blocked", launcher_enabled=True, pid=matches[0],
                                error="Matching Creator_OS process exists without a healthy heartbeat.")
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        output = open(self.runtime_logs / definition.log_name, "a", encoding="utf-8")
        error = open(self.runtime_logs / definition.log_name.replace(".log", "_error.log"), "a", encoding="utf-8")
        process = self.processes.start(definition.command, cwd=self.project_root, stdout=output, stderr=error)
        try:
            heartbeat = self._wait_for_heartbeat(definition, process.pid, definition.startup_timeout)
            if heartbeat is None:
                self.processes.force_stop(process.pid)
                return self._record(definition, "startup_failed", launcher_enabled=True, pid=process.pid,
                                    error="Heartbeat did not become healthy before startup timeout.")
            return self._record(definition, "started", launcher_enabled=True, pid=process.pid,
                                instance_id=heartbeat.worker_instance_id)
        finally:
            output.close(); error.close()

    def stop_worker(self, definition: WorkerLaunchDefinition, pid: int) -> dict[str, Any]:
        if not self.processes.matches(pid, definition):
            return self._record(definition, "shutdown_blocked", launcher_enabled=_enabled(self.environment.get(definition.environment_switch)),
                                pid=pid, error="PID no longer belongs to the configured Creator_OS worker.")
        self.processes.graceful_stop(pid)
        deadline = self.now().timestamp() + definition.shutdown_timeout
        while self.now().timestamp() < deadline:
            if not self.processes.exists(pid) and self._shutdown_recorded(definition, pid):
                return self._record(definition, "stopped", launcher_enabled=_enabled(self.environment.get(definition.environment_switch)), pid=None)
            self.sleep(0.25)
        self.processes.force_stop(pid)
        return self._record(definition, "force_stopped", launcher_enabled=_enabled(self.environment.get(definition.environment_switch)), pid=None,
                            error="Graceful shutdown timeout expired.")

    def _healthy_live_heartbeat(self, definition: WorkerLaunchDefinition):
        rows = self.heartbeats.list_latest_per_worker()
        heartbeat = next((row for row in rows if row.worker_name == definition.heartbeat_name), None)
        if heartbeat is None or heartbeat.process_id is None or not self.processes.matches(heartbeat.process_id, definition): return None
        threshold = int(dict(heartbeat.metadata or {}).get("stale_threshold_seconds") or 90)
        classification = WorkerHeartbeatService.classify(heartbeat, stale_threshold_seconds=threshold, now=self.now())
        return heartbeat if classification in {WorkerHealthClassification.HEALTHY, WorkerHealthClassification.IDLE} else None

    def _shutdown_recorded(self, definition: WorkerLaunchDefinition, pid: int) -> bool:
        rows = self.heartbeats.list_latest_per_worker()
        heartbeat = next((row for row in rows if row.worker_name == definition.heartbeat_name and row.process_id == pid), None)
        return bool(heartbeat and heartbeat.status in {WorkerHeartbeatStatus.STOPPING, WorkerHeartbeatStatus.STOPPED})

    def _wait_for_heartbeat(self, definition: WorkerLaunchDefinition, pid: int, timeout: int):
        deadline = self.now().timestamp() + timeout
        while self.now().timestamp() < deadline:
            heartbeat = self._healthy_live_heartbeat(definition)
            if heartbeat is not None and heartbeat.process_id == pid: return heartbeat
            if not self.processes.exists(pid): return None
            self.sleep(0.25)
        return None

    def _record(self, definition, action, *, launcher_enabled, pid, instance_id=None, error=None):
        state = self._load_state()
        record = {"workerName": definition.name, "launcherManaged": True, "launcherEnabled": launcher_enabled,
                  "expectedStartupMethod": " ".join(definition.command), "expectedHeartbeatName": definition.heartbeat_name,
                  "pid": pid, "instanceId": instance_id, "lastLauncherAction": action,
                  "lastLauncherActionAt": self.now().isoformat(), "startupFailure": error if "startup" in action else None,
                  "configurationBlocked": action == "configuration_blocked", "error": error}
        state[definition.key] = record
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)
        return record

    def _load_state(self) -> dict[str, Any]:
        try: return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}
