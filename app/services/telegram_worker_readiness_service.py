"""Canonical fail-closed readiness projection for the Telegram runtime."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Mapping

from app.models.worker_heartbeat import WorkerHealthClassification
from app.repositories.worker_heartbeat_repository import WorkerHeartbeatRepository
from app.services.worker_heartbeat_service import WorkerHeartbeatService
from app.services.worker_launcher_supervision_service import (
    WORKERS,
    ProcessAdapter,
)


class TelegramWorkerReadinessService:
    """Combine heartbeat, process ownership, scope, and launcher authority."""

    def __init__(
        self,
        *,
        heartbeat_repository: Any | None = None,
        process_adapter: Any | None = None,
        launcher_state_path: str | Path | None = None,
        environment: Mapping[str, str] | None = None,
        creator_profile_reader: Any | None = None,
        now: Any | None = None,
    ) -> None:
        self.heartbeats = heartbeat_repository or WorkerHeartbeatRepository()
        self.processes = process_adapter or ProcessAdapter()
        self.launcher_state_path = Path(launcher_state_path) if launcher_state_path else Path(
            "logs/runtime/launcher_state.json"
        )
        self.environment = environment if environment is not None else os.environ
        if creator_profile_reader is None:
            from app.repositories.creator_profile_repository import get_active_creator_profile
            creator_profile_reader = get_active_creator_profile
        self.creator_profile_reader = creator_profile_reader
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.definition = next(item for item in WORKERS if item.key == "telegram")

    def read(self, *, creator_profile_id: str | int) -> dict[str, Any]:
        expected_account = self._positive_int(self.environment.get("AVA_FANVUE_ACCOUNT_ID"))
        if expected_account is None:
            return self._blocked("configuration_blocked")
        creator = self.creator_profile_reader(str(expected_account)) or {}
        expected_creator = str(creator.get("id") or "").strip()
        if not expected_creator:
            return self._blocked("configuration_blocked")
        if not self._enabled(self.environment.get(self.definition.environment_switch)):
            return self._blocked("configuration_blocked")
        if any(not str(self.environment.get(name) or "").strip()
               for name in self.definition.required_environment):
            return self._blocked("configuration_blocked")

        launcher = self._launcher_state()
        if not launcher or launcher.get("launcherEnabled") is not True:
            return self._blocked("launcher_unavailable")
        if launcher.get("configurationBlocked") or launcher.get("crashLoopBlocked"):
            return self._blocked("launcher_blocked")
        if launcher.get("startupFailure") or launcher.get("lastLauncherAction") in {
            "startup_failed", "startup_blocked", "authorization_required",
            "crash_loop_blocked", "configuration_blocked", "disabled", "stopped",
            "force_stopped", "shutdown_blocked",
        }:
            return self._blocked("launcher_unhealthy")

        now = self.now()
        rows = [row for row in self.heartbeats.list_recent_instances(
            since=now - timedelta(minutes=10)
        ) if row.worker_name == self.definition.heartbeat_name]
        live = []
        for row in rows:
            threshold = int(dict(row.metadata or {}).get("stale_threshold_seconds") or 90)
            classification = WorkerHeartbeatService.classify(
                row, stale_threshold_seconds=threshold, now=now
            )
            if classification in {WorkerHealthClassification.HEALTHY,
                                   WorkerHealthClassification.IDLE} and (
                    row.process_id is not None and
                    self.processes.matches(row.process_id, self.definition)
            ):
                live.append((row, classification, threshold))
        if len(live) != 1:
            return self._blocked("no_singleton_runtime", authoritative_count=len(live))

        heartbeat, classification, threshold = live[0]
        metadata = dict(heartbeat.metadata or {})
        if heartbeat.creator_profile_id != expected_creator or heartbeat.account_id != expected_account:
            return self._blocked("wrong_account_scope")
        if metadata.get("account_scope") != "AVA_TELETHON_PRIVATE":
            return self._blocked("wrong_runtime_scope")
        if heartbeat.process_id is None or not self.processes.matches(
            heartbeat.process_id, self.definition
        ):
            return self._blocked("process_ownership_unverified")
        matching = self.processes.matching(self.definition)
        if matching != [heartbeat.process_id]:
            return self._blocked("no_singleton_process", process_count=len(matching))
        if launcher.get("pid") != heartbeat.process_id or launcher.get("instanceId") != heartbeat.worker_instance_id:
            return self._blocked("launcher_identity_mismatch")
        if metadata.get("authorized") is not True:
            return self._blocked("unauthorized")
        if metadata.get("database_healthy") is not True:
            return self._blocked("database_unhealthy")
        if metadata.get("lifecycle_state") != "CONNECTED":
            return self._blocked("disconnected")
        if heartbeat.last_error or launcher.get("error"):
            return self._blocked("runtime_error")

        return {
            "ready": True,
            "reason": None,
            "status": classification.value,
            "processId": heartbeat.process_id,
            "instanceId": heartbeat.worker_instance_id,
            "creatorProfileId": heartbeat.creator_profile_id,
            "accountId": heartbeat.account_id,
            "startedAt": heartbeat.started_at,
            "lastHeartbeatAt": heartbeat.last_heartbeat_at,
            "staleThresholdSeconds": threshold,
            "lifecycleState": metadata.get("lifecycle_state"),
            "authorized": True,
            "databaseHealthy": True,
            "launcherAction": launcher.get("lastLauncherAction"),
        }

    def _launcher_state(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.launcher_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        value = payload.get(self.definition.key)
        return dict(value) if isinstance(value, dict) else {}

    @staticmethod
    def _positive_int(value: Any) -> int | None:
        try:
            parsed = int(str(value or "").strip())
        except (TypeError, ValueError):
            return None
        return parsed if parsed > 0 else None

    @staticmethod
    def _enabled(value: Any) -> bool:
        return str(value or "").strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def _blocked(code: str, **details: Any) -> dict[str, Any]:
        return {
            "ready": False,
            "reason": "Telegram worker is absent or unhealthy.",
            "code": code,
            **details,
        }
