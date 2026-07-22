"""Process-only supervision for autonomous Creator_OS runtimes."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import psutil
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
    WorkerLaunchDefinition("nudenet_analysis", "NudeNet Analysis", "CREATOR_OS_LAUNCH_NUDENET_ANALYSIS",
                           "app.workers.nudenet_analysis", "NudeNet Analysis", 30, 30,
                           "nudenet_analysis.log"),
    WorkerLaunchDefinition("analysis_orchestrator", "Analysis Orchestrator", "CREATOR_OS_LAUNCH_ANALYSIS_ORCHESTRATOR",
                           "app.workers.analysis_orchestrator", "Analysis Orchestrator", 30, 30,
                           "analysis_orchestrator.log"),
    WorkerLaunchDefinition("vision_analysis", "Vision Analysis", "CREATOR_OS_LAUNCH_VISION_ANALYSIS",
                           "app.workers.vision_analysis", "Vision Analysis", 30, 30,
                           "vision_analysis.log"),
    WorkerLaunchDefinition("grok_analysis", "Grok Analysis", "CREATOR_OS_LAUNCH_GROK_ANALYSIS",
                           "app.workers.grok_analysis", "Grok Analysis", 30, 30,
                           "grok_analysis.log", ("GROK_API_KEY",)),
    WorkerLaunchDefinition("content_intelligence_merge", "Content Intelligence Merge",
                           "CREATOR_OS_LAUNCH_CONTENT_INTELLIGENCE_MERGE",
                           "app.workers.content_intelligence_merge", "Content Intelligence Merge",
                           30, 30, "content_intelligence_merge.log"),
    WorkerLaunchDefinition("photoshoot_analysis", "Photoshoot Analysis",
                           "CREATOR_OS_LAUNCH_PHOTOSHOOT_ANALYSIS",
                           "app.workers.photoshoot_analysis", "Photoshoot Analysis",
                           30, 30, "photoshoot_analysis.log"),
    WorkerLaunchDefinition("photoshoot_auto_run", "Photoshoot Auto Run",
                           "CREATOR_OS_LAUNCH_PHOTOSHOOT_AUTO_RUN",
                           "app.workers.photoshoot_auto_run", "Photoshoot Auto Run",
                           30, 30, "photoshoot_auto_run.log"),
    WorkerLaunchDefinition("ready_asset_chat_registration", "READY Asset Chat Registration",
                           "CREATOR_OS_LAUNCH_READY_ASSET_CHAT_REGISTRATION",
                           "app.workers.ready_asset_chat_registration", "READY Asset Chat Registration",
                           30, 30, "ready_asset_chat_registration.log"),
)


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


class ProcessAdapter:
    def start(self, command: tuple[str, ...], *, cwd: Path, stdout, stderr):
        flags = subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0
        return subprocess.Popen(command, cwd=cwd, stdout=stdout, stderr=stderr, creationflags=flags)

    @staticmethod
    def exists(pid: int) -> bool:
        if int(pid) <= 0:
            return False
        return psutil.pid_exists(int(pid))

    @staticmethod
    def command_line(pid: int) -> str:
        try:
            return " ".join(psutil.Process(int(pid)).cmdline())
        except (psutil.NoSuchProcess, psutil.ZombieProcess):
            return ""
        except psutil.AccessDenied as error:
            raise RuntimeError(f"Cannot validate command line ownership for PID {pid}: access denied.") from error

    def matches(self, pid: int, definition: WorkerLaunchDefinition) -> bool:
        return self.exists(pid) and definition.module in self.command_line(pid)

    def matching(self, definition: WorkerLaunchDefinition) -> list[int]:
        matches = []
        for process in psutil.process_iter(("pid", "cmdline")):
            try:
                command = " ".join(process.info.get("cmdline") or ())
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                continue
            if definition.module in command:
                matches.append(int(process.info["pid"]))
        return matches

    @staticmethod
    def graceful_stop(pid: int) -> bool:
        if os.name != "nt":
            os.kill(pid, signal.SIGTERM)
            return True
        # A later launcher invocation is not necessarily attached to the
        # console that created this process group. GenerateConsoleCtrlEvent
        # (Python's CTRL_BREAK_EVENT path) then fails with WinError 87. Use
        # Windows' process-tree shutdown boundary after ownership validation.
        result = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode == 0 or not ProcessAdapter.exists(pid):
            return True
        detail = (result.stderr or result.stdout or "unknown taskkill error").strip()
        if "can only be terminated forcefully" in detail.lower():
            return False
        if result.returncode != 0:
            raise RuntimeError(
                f"Graceful worker process-tree shutdown failed for PID {pid}: "
                f"command='taskkill /PID {pid} /T', exit={result.returncode}: {detail}"
            )
        return True

    @staticmethod
    def force_stop(pid: int) -> None:
        if os.name != "nt":
            os.kill(pid, signal.SIGKILL)
            return
        result = subprocess.run(
            ["taskkill", "/PID", str(int(pid)), "/T", "/F"],
            capture_output=True, text=True, timeout=10, check=False,
        )
        if result.returncode != 0 and ProcessAdapter.exists(pid):
            detail = (result.stderr or result.stdout or "unknown taskkill error").strip()
            raise RuntimeError(
                f"Forced worker process-tree shutdown failed for PID {pid}: "
                f"command='taskkill /PID {pid} /T /F', exit={result.returncode}: {detail}"
            )


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
                pid = int(record["pid"])
                try:
                    results.append(self.stop_worker(definition, pid))
                except Exception as error:
                    raise RuntimeError(
                        f"Worker shutdown failed: worker={definition.name!r}, "
                        f"pid={pid}, operation={type(error).__name__}: {error}"
                    ) from error
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
        if not self.processes.exists(pid):
            return self._record(
                definition, "stopped",
                launcher_enabled=_enabled(self.environment.get(definition.environment_switch)),
                pid=None,
            )
        if not self.processes.matches(pid, definition):
            return self._record(definition, "shutdown_blocked", launcher_enabled=_enabled(self.environment.get(definition.environment_switch)),
                                pid=pid, error="PID no longer belongs to the configured Creator_OS worker.")
        graceful_requested = self.processes.graceful_stop(pid)
        if graceful_requested is False:
            self.processes.force_stop(pid)
            return self._record(
                definition, "force_stopped",
                launcher_enabled=_enabled(self.environment.get(definition.environment_switch)),
                pid=None,
                error=("Windows required forced console-worker shutdown; "
                       f"command='taskkill /PID {pid} /T /F'."),
            )
        deadline = self.now().timestamp() + definition.shutdown_timeout
        while self.now().timestamp() < deadline:
            if not self.processes.exists(pid):
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
