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
from datetime import datetime, timedelta, timezone
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
    WorkerLaunchDefinition("fanvue_commercial_publications", "Fanvue Commercial Publications",
                           "CREATOR_OS_LAUNCH_FANVUE_COMMERCIAL_PUBLICATIONS",
                           "app.workers.fanvue_commercial_publications",
                           "Fanvue Commercial Publications", 30, 30,
                           "fanvue_commercial_publications.log"),
    WorkerLaunchDefinition(
        "commerce_reconciliation", "Commerce Reconciliation",
        "CREATOR_OS_LAUNCH_COMMERCE_RECONCILIATION",
        "app.workers.commerce_reconciliation", "Commerce Reconciliation",
        30, 30, "commerce_reconciliation.log",
    ),
    WorkerLaunchDefinition("background_operations", "Background Operations",
                           "CREATOR_OS_LAUNCH_BACKGROUND_OPERATIONS",
                           "app.workers.background_operations", "Background Operations",
                           30, 30, "background_operations.log"),
    WorkerLaunchDefinition("x_competitor_refresh", "X Competitor Refresh",
                           "CREATOR_OS_LAUNCH_X_COMPETITOR_REFRESH",
                           "app.workers.x_competitor_refresh", "X Competitor Refresh",
                           30, 30, "x_competitor_refresh.log"),
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
    def matching_command(fragment: str) -> list[int]:
        matches = []
        for process in psutil.process_iter(("pid", "cmdline")):
            try:
                command = " ".join(process.info.get("cmdline") or ())
            except (psutil.NoSuchProcess, psutil.ZombieProcess, psutil.AccessDenied):
                continue
            if fragment in command:
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
    TELEGRAM_CRASH_WINDOW_SECONDS = 300
    TELEGRAM_CRASH_LIMIT = 5
    TELEGRAM_MONITOR_SECONDS = 5
    DEV_AUTO_RELOAD_SWITCH = "CREATOR_OS_DEV_AUTO_RELOAD"
    DEV_RELOAD_DEBOUNCE_SECONDS = 1.0
    DEV_WATCH_ROOTS = ("app",)
    DEV_WATCH_EXCLUDED_PARTS = frozenset({
        "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
    })
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
        self.reload_log_path = self.runtime_logs / "dev_auto_reload.log"
        self._reload_snapshot: dict[str, tuple[int, int]] | None = None
        self._reload_pending: set[str] = set()
        self._reload_last_change_at: datetime | None = None

    def configuration(self) -> tuple[dict[str, Any], ...]:
        return tuple({**asdict(item), "command": list(item.command),
                      "enabled": _enabled(self.environment.get(item.environment_switch))} for item in WORKERS)

    def start_enabled(self) -> tuple[dict[str, Any], ...]:
        return tuple(self.start_worker(item) for item in WORKERS)

    def stop_managed(self) -> tuple[dict[str, Any], ...]:
        self.stop_telegram_monitor()
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

    def monitor_telegram(self, *, max_cycles: int | None = None) -> None:
        definitions = tuple(
            item for item in WORKERS
            if item.key in {"telegram", "commerce_reconciliation"}
        )
        for definition in definitions:
            self._record_supervisor_pid(definition, os.getpid())
        cycles = 0
        try:
            while any(_enabled(self.environment.get(item.environment_switch)) for item in definitions):
                for definition in definitions:
                    if _enabled(self.environment.get(definition.environment_switch)):
                        self.supervise_telegram_once(definition)
                self.poll_development_reload()
                cycles += 1
                if max_cycles is not None and cycles >= max_cycles:
                    return
                self.sleep(self.TELEGRAM_MONITOR_SECONDS)
        finally:
            for definition in definitions:
                self._record_supervisor_pid(definition, None, expected_pid=os.getpid())

    def poll_development_reload(self) -> dict[str, Any] | None:
        """Coalesce Python source edits and reload enabled workers in development."""
        if not _enabled(self.environment.get(self.DEV_AUTO_RELOAD_SWITCH)):
            self._reload_snapshot = None
            self._reload_pending.clear()
            self._reload_last_change_at = None
            return None
        current = self._source_snapshot()
        if self._reload_snapshot is None:
            self._reload_snapshot = current
            self._log_reload("watch_started", watched_roots=list(self.DEV_WATCH_ROOTS))
            return None
        changed = self._changed_sources(self._reload_snapshot, current)
        self._reload_snapshot = current
        if changed:
            self._reload_pending.update(changed)
            self._reload_last_change_at = self.now()
            self._log_reload("source_change_detected", files=sorted(changed))
            return {"status": "debouncing", "files": sorted(self._reload_pending)}
        if not self._reload_pending or self._reload_last_change_at is None:
            return None
        if (self.now() - self._reload_last_change_at).total_seconds() < self.DEV_RELOAD_DEBOUNCE_SECONDS:
            return {"status": "debouncing", "files": sorted(self._reload_pending)}
        files = sorted(self._reload_pending)
        self._reload_pending.clear()
        self._reload_last_change_at = None
        return self.reload_enabled_workers(files)

    def reload_enabled_workers(self, changed_files: list[str]) -> dict[str, Any]:
        """Stop every enabled worker before starting any replacement."""
        enabled = [item for item in WORKERS
                   if _enabled(self.environment.get(item.environment_switch))]
        state = self._load_state()
        old_pids = {}
        self._log_reload("worker_reload_started", files=changed_files,
                         workers=[item.name for item in enabled])
        # Complete the entire shutdown phase first. If any owned process cannot
        # stop, the exception aborts before a replacement can be authoritative.
        for definition in reversed(enabled):
            record = state.get(definition.key) or {}
            pid = record.get("pid")
            if pid:
                old_pids[definition.key] = int(pid)
                self.stop_worker(definition, int(pid))
                self._log_reload("old_worker_stopped", worker=definition.name,
                                 old_pid=int(pid))
        results = []
        for definition in enabled:
            result = self.start_worker(definition)
            results.append(result)
            self._log_reload("new_worker_started", worker=definition.name,
                             old_pid=old_pids.get(definition.key),
                             new_pid=result.get("pid"),
                             action=result.get("lastLauncherAction"))
        return {"status": "reloaded", "files": changed_files,
                "workers": results, "oldPids": old_pids}

    def _source_snapshot(self) -> dict[str, tuple[int, int]]:
        snapshot = {}
        for root_name in self.DEV_WATCH_ROOTS:
            root = self.project_root / root_name
            if not root.is_dir():
                continue
            for path in root.rglob("*.py"):
                relative = path.relative_to(self.project_root)
                if any(part in self.DEV_WATCH_EXCLUDED_PARTS for part in relative.parts):
                    continue
                try:
                    stat = path.stat()
                except OSError:
                    continue
                snapshot[relative.as_posix()] = (stat.st_mtime_ns, stat.st_size)
        return snapshot

    @staticmethod
    def _changed_sources(previous: Mapping[str, tuple[int, int]],
                         current: Mapping[str, tuple[int, int]]) -> set[str]:
        return {name for name in set(previous) | set(current)
                if previous.get(name) != current.get(name)}

    def _log_reload(self, event: str, **fields: Any) -> None:
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        payload = {"timestamp": self.now().isoformat(), "event": event, **fields}
        with self.reload_log_path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(payload, default=str, sort_keys=True) + "\n")

    def supervise_telegram_once(self, definition: WorkerLaunchDefinition | None = None) -> dict[str, Any]:
        definition = definition or next(item for item in WORKERS if item.key == "telegram")
        if not _enabled(self.environment.get(definition.environment_switch)):
            return self._record(definition, "disabled", launcher_enabled=False, pid=None)
        live = self._healthy_live_heartbeat(definition)
        if live is not None:
            state = self._load_state().get(definition.key) or {}
            started = self._parse_time(state.get("stableSince")) or live.started_at
            if (self.now() - started).total_seconds() >= self.TELEGRAM_CRASH_WINDOW_SECONDS:
                return self._record(definition, "healthy", launcher_enabled=True, pid=live.process_id,
                                    instance_id=live.worker_instance_id, restart_history=[])
            return self._record(definition, "healthy", launcher_enabled=True, pid=live.process_id,
                                instance_id=live.worker_instance_id)

        state = self._load_state().get(definition.key) or {}
        latest = self._latest_heartbeat(definition)
        if latest is not None and bool(dict(latest.metadata or {}).get("authorization_required")):
            return self._record(definition, "authorization_required", launcher_enabled=True, pid=None,
                                instance_id=latest.worker_instance_id, error=latest.last_error,
                                crash_loop_blocked=True)
        if state.get("lastLauncherAction") in {"stopped", "force_stopped", "disabled"}:
            return state
        matches = self.processes.matching(definition)
        if matches:
            latest = self._latest_heartbeat(definition)
            threshold = int(dict(getattr(latest, "metadata", {}) or {}).get("stale_threshold_seconds") or 90)
            if latest is not None and (self.now() - latest.last_heartbeat_at).total_seconds() <= threshold * 2:
                return self._record(definition, "degraded", launcher_enabled=True, pid=matches[0],
                                    instance_id=latest.worker_instance_id, error=latest.last_error)
            self.stop_worker(definition, matches[0])

        history = [value for value in state.get("restartHistory", [])
                   if (self.now() - self._parse_time(value)).total_seconds() <= self.TELEGRAM_CRASH_WINDOW_SECONDS]
        if len(history) >= self.TELEGRAM_CRASH_LIMIT:
            return self._record(definition, "crash_loop_blocked", launcher_enabled=True, pid=None,
                                error="Automatic restart threshold reached; operator attention required.",
                                restart_history=history, crash_loop_blocked=True)
        next_retry = self._parse_time(state.get("nextRestartAt"))
        if next_retry is not None and self.now() < next_retry:
            return state
        history.append(self.now().isoformat())
        delay = min(60, 2 ** max(0, len(history) - 1))
        result = self.start_worker(definition)
        return self._record(definition, result["lastLauncherAction"], launcher_enabled=True,
                            pid=result.get("pid"), instance_id=result.get("instanceId"),
                            error=result.get("error"), restart_history=history,
                            next_restart_at=(self.now() + timedelta(seconds=delay)).isoformat(),
                            supervisor_restarts=len(history))

    def stop_telegram_monitor(self) -> None:
        fragment = "tools.launcher.worker_supervisor monitor-telegram"
        matcher = getattr(self.processes, "matching_command", None)
        if matcher is None:
            return
        for pid in matcher(fragment):
            if pid != os.getpid() and self.processes.exists(pid):
                graceful = self.processes.graceful_stop(pid)
                if graceful is False and self.processes.exists(pid):
                    self.processes.force_stop(pid)
        for definition in WORKERS:
            if definition.key in {"telegram", "commerce_reconciliation"}:
                self._record_supervisor_pid(definition, None)

    def _record_supervisor_pid(self, definition: WorkerLaunchDefinition, pid: int | None,
                               *, expected_pid: int | None = None) -> None:
        state = self._load_state()
        record = dict(state.get(definition.key) or {})
        if expected_pid is not None and record.get("supervisorPid") not in {None, expected_pid}:
            return
        record["supervisorPid"] = pid
        record["supervisorUpdatedAt"] = self.now().isoformat()
        state[definition.key] = record
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)

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

    def _latest_heartbeat(self, definition):
        return next((row for row in self.heartbeats.list_latest_per_worker()
                     if row.worker_name == definition.heartbeat_name), None)

    @staticmethod
    def _parse_time(value):
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if not value:
            return None
        parsed = datetime.fromisoformat(str(value))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)

    def _record(self, definition, action, *, launcher_enabled, pid, instance_id=None, error=None,
                restart_history=None, next_restart_at=None, supervisor_restarts=None,
                crash_loop_blocked=False):
        state = self._load_state()
        record = {"workerName": definition.name, "launcherManaged": True, "launcherEnabled": launcher_enabled,
                  "expectedStartupMethod": " ".join(definition.command), "expectedHeartbeatName": definition.heartbeat_name,
                  "pid": pid, "instanceId": instance_id, "lastLauncherAction": action,
                  "lastLauncherActionAt": self.now().isoformat(), "startupFailure": error if "startup" in action else None,
                  "configurationBlocked": action == "configuration_blocked", "error": error}
        previous = state.get(definition.key) or {}
        record["restartHistory"] = list(restart_history if restart_history is not None else previous.get("restartHistory", []))
        record["nextRestartAt"] = next_restart_at if next_restart_at is not None else previous.get("nextRestartAt")
        record["supervisorRestartCount"] = supervisor_restarts if supervisor_restarts is not None else previous.get("supervisorRestartCount", 0)
        record["crashLoopBlocked"] = bool(crash_loop_blocked)
        record["supervisorPid"] = previous.get("supervisorPid")
        record["supervisorUpdatedAt"] = previous.get("supervisorUpdatedAt")
        if action == "started":
            record["stableSince"] = self.now().isoformat()
        elif action == "healthy":
            record["stableSince"] = previous.get("stableSince") or self.now().isoformat()
        else:
            record["stableSince"] = previous.get("stableSince")
        state[definition.key] = record
        self.runtime_logs.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(state, indent=2), encoding="utf-8")
        temporary.replace(self.state_path)
        return record

    def _load_state(self) -> dict[str, Any]:
        try: return json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError): return {}
