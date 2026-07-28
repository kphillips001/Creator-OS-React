"""Read-only composition for the React Operations workspace."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
import json
from pathlib import Path
from typing import Any, Iterable, Mapping

from app.repositories.chat_commerce_delivery_repository import ChatCommerceDeliveryRepository
from app.repositories.outreach_queue_repository import fetch_outreach_queue_dashboard
from app.repositories.publishing_repository import PublishingRepository
from app.repositories.webhook_event_repository import list_webhook_events_for_account
from app.repositories.worker_heartbeat_repository import WorkerHeartbeatRepository
from app.services.delayed_messages_dashboard_service import DelayedMessagesDashboardService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.mass_ppv_dashboard_service import MassPPVDashboardService
from app.services.publishing_automation_service import PublishingAutomationService
from app.services.runtime_control_service import RuntimeControlService
from app.services.system_health_service import SystemHealthService
from app.services.wall_scheduler_dashboard_service import WallSchedulerDashboardService
from app.services.worker_heartbeat_service import WorkerHeartbeatService


class OperationsWorkspaceService:
    """Project persisted operational evidence without executing operational work."""

    STALE_AFTER = timedelta(minutes=30)

    def __init__(
        self,
        *,
        health_service: Any | None = None,
        runtime_service: Any | None = None,
        safety_service: Any | None = None,
        delayed_service: Any | None = None,
        mass_ppv_service: Any | None = None,
        wall_service: Any | None = None,
        publishing_repository: Any | None = None,
        publishing_automation_service: Any | None = None,
        outreach_reader: Any = fetch_outreach_queue_dashboard,
        webhook_reader: Any = list_webhook_events_for_account,
        delivery_repository: Any | None = None,
        heartbeat_repository: Any | None = None,
        launcher_state_path: str | Path | None = None,
        now: Any | None = None,
    ) -> None:
        self.health_service = health_service or SystemHealthService()
        self.runtime_service = runtime_service or RuntimeControlService()
        self.safety_service = safety_service or GlobalAutomationSafetyService()
        self.delayed_service = delayed_service or DelayedMessagesDashboardService()
        self.mass_ppv_service = mass_ppv_service or MassPPVDashboardService()
        self.wall_service = wall_service or WallSchedulerDashboardService()
        self.publishing_repository = publishing_repository or PublishingRepository()
        self.publishing_automation = publishing_automation_service or PublishingAutomationService()
        self.outreach_reader = outreach_reader
        self.webhook_reader = webhook_reader
        self.delivery_repository = delivery_repository or ChatCommerceDeliveryRepository()
        self.heartbeat_repository = heartbeat_repository or WorkerHeartbeatRepository()
        self.launcher_state_path = Path(launcher_state_path) if launcher_state_path else Path("logs/runtime/launcher_state.json")
        self.now = now or (lambda: datetime.now(timezone.utc))

    def overview(self, *, account_id: int) -> dict[str, Any]:
        health = self._health()
        runtime = self.runtime(account_id=account_id)
        queues = self.queues(account_id=account_id)
        publishing = self.publishing(account_id=account_id)
        failures = self.failures(account_id=account_id)
        workers = self.workers(account_id=account_id)
        worker_counts = workers["summary"]
        database = next((check for section in health["sections"] if section["name"] == "Database" for check in section["checks"] if check["name"] == "Database Connection"), None)
        return {
            "overallHealth": health["overallStatus"], "healthScore": health["score"],
            "database": database or {"status": "unknown", "summary": "Untracked"},
            "runtimeMode": runtime["snapshot"]["currentMode"],
            "autonomousExecution": "ACTIVE" if runtime["effectiveGlobalSafety"].get("allowed") else "BLOCKED",
            "globalAutomation": runtime["globalAutomation"], "globalSends": runtime["globalSends"],
            "manualPause": runtime["manualPause"], "queueTotals": queues["totals"],
            "failureCount": failures["total"], "publishingAttention": publishing["summary"]["attention"],
            "providerWarnings": health["providerWarnings"],
            "failingChecks": health["failingChecks"],
            "workerCounts": worker_counts,
            "warnings": workers["warnings"],
        }

    def runtime(self, *, account_id: int) -> dict[str, Any]:
        snapshot = self._plain(self.runtime_service.build_snapshot(creator_profile_id=account_id))
        config = dict(getattr(self.safety_service, "behavior_config", {}) or {})
        global_result = self.safety_service.check_global_safety()
        guards = {
            "Chat": self.safety_service.can_send_chat(),
            "Monetization": self.safety_service.can_send_monetization(),
            "Mass PPV": self.safety_service.can_send_mass_ppv(),
            "Post-purchase Reactions": self.safety_service.can_send_post_purchase_reaction(),
            "Delayed Follow-ups": self.safety_service.can_send_delayed_followup(),
            "Outreach": self.safety_service.can_send_outreach(),
            "Reactivation": self.safety_service.can_send_reactivation(),
        }
        return {
            "snapshot": self._camel(snapshot), "effectiveGlobalSafety": global_result,
            "globalAutomation": bool(config.get("global_automation_enabled", False)),
            "globalSends": bool(config.get("global_sends_enabled", False)),
            "manualPause": bool(config.get("manual_pause_enabled", False)),
            "guards": [{"module": name, **value} for name, value in guards.items()],
            "configurationWarnings": self._health()["configurationWarnings"],
            "warnings": ["Runtime mode is configured state and does not prove that a worker or transport is running."],
        }

    def workers(self, *, account_id: int) -> dict[str, Any]:
        evidence = self._evidence(account_id)
        launcher_state = self._launcher_state()
        heartbeat_warning = None
        try:
            heartbeats = {item.worker_name: item for item in self.heartbeat_repository.list_latest_per_worker(creator_profile_id=str(account_id), account_id=account_id)}
        except Exception as error:
            heartbeats = {}
            heartbeat_warning = f"Worker heartbeat persistence is unavailable: {error}"
        specifications = (
            ("FastAPI", "Desktop launcher", True, "FastAPI", 90, "Heartbeat persistence", None),
            ("React", "Desktop launcher", True, None, None, "Backend reachability is not instrumented", None),
            ("Fanvue webhook", "FastAPI request capability", True, "FastAPI", 90, "Webhook event persistence", self._latest(evidence["webhooks"])),
            ("Telegram", "Supervised module process", True, "Telegram", 90, "Telegram activity is not separately persisted", None),
            ("Outreach", "Supervised queue worker", True, "Outreach", 900, "Outreach queue activity", self._latest(evidence["outreach"])),
            ("Delayed Messages", "Supervised loop service", True, "Delayed Messages", 60, "Delayed queue activity", self._latest(evidence["delayed"])),
            ("Mass PPV", "Supervised loop service", True, "Mass PPV", 90, "Mass PPV queue activity", self._latest(evidence["massPpv"])),
            ("Wall Worker", "Supervised loop service", True, "Wall Worker", 180, "Wall queue activity", self._latest(evidence["wall"])),
            ("Publishing", "Request/service driven", False, None, None, "Publishing job activity", self._latest(evidence["publishing"])),
            ("Automated Reactions", "Event driven", False, None, None, "No standalone worker exists", None),
        )
        items = []
        for name, startup, launcher, heartbeat_name, threshold, source, activity in specifications:
            launch = launcher_state.get(name, {})
            heartbeat = heartbeats.get(heartbeat_name) if heartbeat_name else None
            heartbeat_data = self._plain(heartbeat) if heartbeat else {}
            persisted_threshold = int(heartbeat_data.get("metadata", {}).get("stale_threshold_seconds") or threshold or 60)
            classification = WorkerHeartbeatService.classify(heartbeat, stale_threshold_seconds=persisted_threshold, now=self.now()).value if heartbeat_name else "unknown"
            items.append({"name": name, "startupType": startup, "launcherManaged": launcher,
                "launcherEnabled": launch.get("launcherEnabled", True if name in {"FastAPI", "React"} else False),
                "expectedStartupMethod": launch.get("expectedStartupMethod", startup),
                "startupFailure": launch.get("startupFailure"),
                "configurationBlocked": bool(launch.get("configurationBlocked", False)),
                "lastLauncherAction": launch.get("lastLauncherAction"),
                "lastLauncherActionAt": launch.get("lastLauncherActionAt"),
                "lastObservedActivity": activity, "activityEvidence": source,
                "heartbeatAvailable": heartbeat is not None, "heartbeatStatus": classification if heartbeat else "untracked",
                "instanceId": heartbeat_data.get("worker_instance_id"), "processId": heartbeat_data.get("process_id"),
                "host": heartbeat_data.get("host_name"), "persistedStatus": heartbeat_data.get("status"),
                "startedAt": heartbeat_data.get("started_at"), "lastHeartbeatAt": heartbeat_data.get("last_heartbeat_at"),
                "lastPollAt": heartbeat_data.get("last_poll_at"), "lastSuccessAt": heartbeat_data.get("last_success_at"),
                "lastFailureAt": heartbeat_data.get("last_failure_at"), "lastError": heartbeat_data.get("last_error"),
                "staleThresholdSeconds": persisted_threshold if heartbeat_name else None,
                "attentionReason": self._worker_attention(classification, heartbeat is not None),
            })
        summary = {key: sum(item["heartbeatStatus"] == key for item in items) for key in ("healthy", "idle", "stale", "stopped", "failed", "untracked")}
        warnings = ["Queue or event activity is historical evidence and remains separate from worker heartbeat state."]
        if heartbeat_warning: warnings.append(heartbeat_warning)
        return {"items": items, "summary": summary, "warnings": warnings}

    def _launcher_state(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.launcher_state_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return {str(item.get("workerName")): item for item in payload.values() if isinstance(item, dict) and item.get("workerName")}

    @staticmethod
    def _worker_attention(classification: str, available: bool) -> str | None:
        if not available: return "Heartbeat unavailable; process liveness is untracked."
        if classification == "stale": return "Last heartbeat exceeded this worker's configured stale threshold."
        if classification == "failed": return "The worker recorded a failed or degraded cycle."
        if classification == "stopped": return "The worker recorded a graceful shutdown."
        return None

    def queues(self, *, account_id: int) -> dict[str, Any]:
        evidence = self._evidence(account_id)
        definitions = (
            ("Outreach", evidence["outreach"], "queue_status", "completed", "error_message"),
            ("Delayed Messages", evidence["delayed"], "status", "completed", "last_error"),
            ("Mass PPV", evidence["massPpv"], "status", "completed", "last_error"),
            ("Wall", evidence["wall"], "queue_status", "completed", "error_message"),
            ("Publishing", evidence["publishing"], "status", "COMPLETED", "failure_reason"),
            ("Webhooks", evidence["webhooks"], "status", "processed", "last_error"),
        )
        items = [self._queue_projection(*definition) for definition in definitions]
        keys = ("pending", "processing", "failed", "retryable", "stale", "recoverable")
        totals = {key: sum(int(item[key]) for item in items) for key in keys}
        totals["all"] = sum(item["total"] for item in items)
        return {"items": items, "totals": totals,
                "warnings": ["Lease expiration is persisted ownership evidence. Queue activity is not used as proof of worker health."]}

    def publishing(self, *, account_id: int) -> dict[str, Any]:
        items = []
        for queue_item in self.publishing_repository.list_queue_items(limit=500):
            job = queue_item.job
            if int(job.provider_account_id or -1) != int(account_id):
                continue
            automation = self.publishing_automation.build_status(publishing_queue_item=queue_item)
            items.append({
                "id": str(job.id), "status": job.status.value, "automationState": automation.state.value,
                "nextRecommendedAction": automation.next_recommended_action, "attention": automation.attention_required,
                "provider": job.provider, "providerStatus": queue_item.provider_status,
                "productId": str(job.product_id) if job.product_id else None, "productName": queue_item.product_name,
                "assetId": job.asset_id, "uploadStatus": queue_item.upload_status,
                "waitingForMediaLink": queue_item.waiting_for_media_link, "retryState": queue_item.retry_state,
                "retryCount": job.retry_count, "failure": queue_item.failure_summary or queue_item.provider_error,
                "lastAttemptedAt": queue_item.last_attempted_at, "updatedAt": job.updated_at,
            })
        return {"items": items, "summary": {
            "total": len(items), "queued": self._count(items, "status", "QUEUED"),
            "uploading": self._count(items, "status", "UPLOADING"),
            "waitingForMediaLink": sum(bool(item["waitingForMediaLink"]) for item in items),
            "retry": sum(item["retryState"] in {"RETRY_REQUIRED", "RETRY_QUEUED"} for item in items),
            "failed": self._count(items, "status", "FAILED"), "attention": sum(bool(item["attention"]) for item in items),
        }, "warnings": []}

    def failures(self, *, account_id: int) -> dict[str, Any]:
        evidence = self._evidence(account_id)
        failures: list[dict[str, Any]] = []
        definitions = (
            ("Outreach", evidence["outreach"], "queue_status", "error_message"),
            ("Delayed Messages", evidence["delayed"], "status", "last_error"),
            ("Mass PPV", evidence["massPpv"], "status", "last_error"),
            ("Wall", evidence["wall"], "queue_status", "error_message"),
            ("Webhooks", evidence["webhooks"], "status", "last_error"),
        )
        for source, rows, status_key, error_key in definitions:
            for row in rows:
                status = str(row.get(status_key) or "").lower()
                error = row.get(error_key)
                if status == "failed" or error:
                    failures.append(self._failure(source, row, status, error))
        for item in self.publishing(account_id=account_id)["items"]:
            if item["failure"] or item["attention"]:
                failures.append({"id": item["id"], "source": "Publishing", "status": item["status"],
                                 "error": item["failure"] or item["nextRecommendedAction"], "timestamp": item["updatedAt"],
                                 "retryCount": item["retryCount"], "related": {"productId": item["productId"], "assetId": item["assetId"]}, "evidence": item})
        for event in self.delivery_repository.list_events():
            payload = self._plain(event)
            if not self._belongs(payload, account_id) or str(payload.get("status") or payload.get("delivery_status") or "").lower() not in {"failed", "error", "blocked"}:
                continue
            failures.append(self._failure("Delivery", payload, str(payload.get("status") or "failed"), payload.get("error") or payload.get("reason")))
        health = self._health()
        for warning in health["providerWarnings"]:
            failures.append({"id": f"provider-{warning['name']}", "source": "Provider", "status": warning["status"],
                             "error": warning["summary"], "timestamp": None, "retryCount": 0, "related": {}, "evidence": warning})
        failures.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
        return {"items": failures, "total": len(failures), "warnings": ["Failures are persisted evidence only; no retry or recovery action is executed here."]}

    def _evidence(self, account_id: int) -> dict[str, list[dict[str, Any]]]:
        delayed = self.delayed_service.build_dashboard(fanvue_account_id=account_id)
        mass = self.mass_ppv_service.build_dashboard(fanvue_account_id=account_id)
        wall = self.wall_service.build_dashboard(fanvue_account_id=account_id)
        publishing = [self._plain(item.job) for item in self.publishing_repository.list_queue_items(limit=500) if int(item.job.provider_account_id or -1) == int(account_id)]
        return {"outreach": self._rows(self.outreach_reader(account_id, 250)), "delayed": self._rows(delayed.recent_rows),
                "massPpv": self._rows(mass.queue_rows), "wall": self._rows(wall.queue_rows),
                "publishing": publishing, "webhooks": self._rows(self.webhook_reader(account_id, 250))}

    def _health(self) -> dict[str, Any]:
        report = self.health_service.build_report()
        sections = [{"name": section.name, "status": section.status, "checks": [self._plain(check) for check in section.checks]} for section in report.sections]
        provider = next((section for section in sections if section["name"] == "Provider Connectivity"), {"checks": []})
        configuration_section = next(
            (section for section in sections if section["name"] == "Configuration"),
            {"checks": []},
        )
        failing_checks = []
        for section in sections:
            for check in section["checks"]:
                if check["status"] == "healthy":
                    continue
                requires_configuration = section["name"] in {
                    "Configuration", "Provider Connectivity",
                }
                failing_checks.append({
                    "section": section["name"], "check": check["name"],
                    "reason": check.get("detail") or check.get("summary")
                              or "The check did not provide a failure reason.",
                    "impact": (
                        "Provider capability is unavailable or degraded."
                        if requires_configuration else "Operational readiness or health score is reduced."
                    ),
                    "automaticRepair": not requires_configuration,
                    "status": check["status"],
                })
        return {"overallStatus": report.overall_status, "score": report.score, "headline": report.headline, "sections": sections,
                "providerWarnings": [item for item in provider["checks"] if item["status"] != "healthy"],
                "configurationWarnings": [item for item in configuration_section["checks"] if item["status"] != "healthy"],
                "failingChecks": failing_checks}

    def _queue_projection(self, name: str, rows: list[dict[str, Any]], status_key: str, complete: str, error_key: str) -> dict[str, Any]:
        normalized = [(row, str(row.get(status_key) or "").lower()) for row in rows]
        processing = [row for row, status in normalized if status in {"processing", "uploading"}]
        failed = [row for row, status in normalized if status in {"failed", "error"} or row.get(error_key)]
        pending = [row for row, status in normalized if status in {"pending", "queued", "received", "retry_scheduled"}]
        retryable = [row for row in failed if int(row.get("retry_count") or 0) < int(row.get("max_retries") or 3)]
        stale = [row for row in processing if self._is_stale(row)]
        completions = [row for row, status in normalized if status == complete.lower()]
        claims = [{"id": str(row.get("id")), "owner": row.get("worker_instance_id"),
                   "claimedAt": row.get("claimed_at"), "leaseExpiresAt": row.get("lease_expires_at"),
                   "stale": self._is_stale(row)} for row in processing if row.get("worker_instance_id")]
        return {"name": name, "total": len(rows), "pending": len(pending), "processing": len(processing), "failed": len(failed),
                "retryable": len(retryable), "stale": len(stale), "recoverable": len(stale),
                "activeClaims": claims, "oldestItem": self._oldest(pending),
                "latestCompletion": self._latest(completions), "latestFailure": self._latest(failed)}

    def _failure(self, source: str, row: Mapping[str, Any], status: str, error: Any) -> dict[str, Any]:
        return {"id": str(row.get("id") or row.get("external_event_id") or "unknown"), "source": source,
                "status": status, "error": str(error or "Failure recorded without an error message."),
                "timestamp": self._row_time(row), "retryCount": int(row.get("retry_count") or 0),
                "related": {"customerId": row.get("fanvue_user_id"), "productId": row.get("product_id"), "assetId": row.get("asset_id")},
                "evidence": self._plain(row)}

    def _is_stale(self, row: Mapping[str, Any]) -> bool:
        lease = self._date(row.get("lease_expires_at"))
        if lease is not None:
            return lease < self.now()
        value = self._date(row.get("processing_started_at") or row.get("updated_at"))
        return bool(value and self.now() - value > self.STALE_AFTER)

    def _latest(self, rows: Iterable[Mapping[str, Any]]) -> Any:
        values = [self._row_time(row) for row in rows if self._row_time(row) is not None]
        return max(values, default=None)

    def _oldest(self, rows: Iterable[Mapping[str, Any]]) -> Any:
        values = [self._row_time(row) for row in rows if self._row_time(row) is not None]
        return min(values, default=None)

    def _row_time(self, row: Mapping[str, Any]) -> Any:
        for key in ("updated_at", "completed_at", "processed_at", "failed_at", "received_at", "created_at", "scheduled_for"):
            if row.get(key) is not None: return row.get(key)
        return None

    @staticmethod
    def _date(value: Any) -> datetime | None:
        if isinstance(value, datetime): parsed = value
        else:
            try: parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except (TypeError, ValueError): return None
        return parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed.astimezone(timezone.utc)

    @staticmethod
    def _rows(rows: Iterable[Any]) -> list[dict[str, Any]]: return [OperationsWorkspaceService._plain(row) for row in (rows or ())]
    @staticmethod
    def _count(items: Iterable[Mapping[str, Any]], key: str, value: str) -> int: return sum(str(item.get(key)) == value for item in items)
    @staticmethod
    def _belongs(row: Mapping[str, Any], account_id: int) -> bool:
        value = row.get("fanvue_account_id") or row.get("provider_account_id") or OperationsWorkspaceService._plain(row.get("payload") or {}).get("fanvue_account_id")
        return str(value) == str(account_id)
    @staticmethod
    def _plain(value: Any) -> Any:
        if is_dataclass(value): return {key: OperationsWorkspaceService._plain(item) for key, item in asdict(value).items()}
        if isinstance(value, Enum): return value.value
        if isinstance(value, Mapping): return {str(key): OperationsWorkspaceService._plain(item) for key, item in value.items()}
        if isinstance(value, (tuple, list)): return [OperationsWorkspaceService._plain(item) for item in value]
        return value
    @staticmethod
    def _camel(value: Mapping[str, Any]) -> dict[str, Any]:
        def name(key: str) -> str:
            parts = key.split("_"); return parts[0] + "".join(part.title() for part in parts[1:])
        return {name(key): OperationsWorkspaceService._plain(item) for key, item in value.items()}
