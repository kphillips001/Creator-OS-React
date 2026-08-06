"""Approval-gated, persistent Developer Agent execution orchestration."""
from __future__ import annotations

import asyncio
import subprocess
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import UUID

from app.repositories.developer_agent_execution_repository import (
    DeveloperAgentExecutionRepository,
)
from app.services.codex_developer_agent_adapter import CodexDeveloperAgentAdapter


REPOSITORY_PATH = Path(r"C:\Creator-OS-React")
EXPECTED_BRANCH = "react-migration"


class DeveloperAgentExecutionService:
    _executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="developer-agent")
    _active: dict[UUID, Future] = {}
    _lock = threading.Lock()

    def __init__(
        self, repository: DeveloperAgentExecutionRepository | None = None,
        adapter: CodexDeveloperAgentAdapter | None = None,
        repository_path: Path = REPOSITORY_PATH,
    ) -> None:
        self.repository = repository or DeveloperAgentExecutionRepository()
        self.adapter = adapter or CodexDeveloperAgentAdapter()
        self.repository_path = repository_path
        self._telemetry_degraded: set[UUID] = set()

    def readiness(self) -> dict[str, Any]:
        repository_ok = (
            self.repository_path.resolve() == REPOSITORY_PATH.resolve()
            and self.repository_path.is_dir()
            and self._is_git_repository()
        )
        branch = self._git("branch", "--show-current") if repository_ok else ""
        try:
            persistence = self.repository.persistence_ready()
        except Exception:
            persistence = False
        adapter = asyncio.run(self.adapter.health(self.repository_path)) if repository_ok else {
            "cliDetected": False, "sdkDetected": False,
            "authenticationAvailable": False, "appServerReachable": False,
            "reason": "Configured repository is unavailable.",
        }
        worker = not self._executor._shutdown
        ready = (
            repository_ok and branch == EXPECTED_BRANCH and worker and persistence
            and adapter["cliDetected"] and adapter["sdkDetected"]
            and adapter["authenticationAvailable"] and adapter["appServerReachable"]
        )
        return {
            **adapter,
            "repositoryAccessible": repository_ok,
            "expectedBranchActive": branch == EXPECTED_BRANCH,
            "currentBranch": branch or None,
            "executionWorkerAvailable": worker,
            "persistenceAvailable": persistence,
            "overallReadiness": "READY" if ready else (
                "DEGRADED" if repository_ok and worker else "UNAVAILABLE"
            ),
            "reason": (
                adapter["reason"]
                if persistence else
                "Developer Agent persistence migration is not applied."
            ),
        }

    def create_task(
        self, *, issue_identifier: str, investigation_package: str,
        implementation_task: str,
    ) -> dict[str, Any]:
        if not all(value.strip() for value in (
            issue_identifier, investigation_package, implementation_task,
        )):
            raise ValueError("Issue, investigation package, and implementation task are required.")
        return self.repository.create_task(
            issue_identifier=issue_identifier.strip(),
            investigation_package=investigation_package,
            implementation_task=implementation_task,
            repository_path=str(REPOSITORY_PATH),
            expected_branch=EXPECTED_BRANCH,
        )

    def approve_task(self, task_id: UUID) -> dict[str, Any]:
        return self.repository.approve_task(task_id)

    def reject_task(self, task_id: UUID) -> dict[str, Any]:
        return self.repository.reject_task(task_id)

    def create_and_dispatch(
        self, *, issue_identifier: str, investigation_package: str,
        implementation_task: str, require_manual_approval: bool = False,
    ) -> dict[str, Any]:
        task = self.create_task(
            issue_identifier=issue_identifier,
            investigation_package=investigation_package,
            implementation_task=implementation_task,
        )
        if require_manual_approval:
            return {"task": task, "execution": None}
        approved = self.approve_task(UUID(str(task["task_id"])))
        execution = self.submit(UUID(str(task["task_id"])))
        return {"task": approved, "execution": execution}

    def submit(self, task_id: UUID) -> dict[str, Any]:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ValueError("Developer Agent task was not found.")
        if task["status"] != "APPROVED" or task["approved_at"] is None:
            raise PermissionError("Task approval is required before execution.")
        self._validate_repository(task)
        health = self.readiness()
        if health["overallReadiness"] != "READY":
            raise RuntimeError(f"Developer Agent unavailable: {health['reason']}")
        execution = self.repository.create_execution(
            task_id=task_id,
            initial_git_status=self._git("status", "--short"),
            initial_branch=self._git("branch", "--show-current"),
            initial_head=self._git("rev-parse", "HEAD"),
        )
        execution_id = UUID(str(execution["execution_id"]))
        self._record_event(
            execution_id, "EXECUTION_ACCEPTED",
            "Queued: approved task accepted by the Developer Agent worker.",
        )
        self._record_notification(
            task_id=task_id, execution_id=execution_id,
            notification_type="EXECUTION_STARTED",
            title="Developer Agent execution started.",
            detail=task["issue_identifier"],
        )
        future = self._executor.submit(self._run_execution, execution_id, task)
        with self._lock:
            self._active[execution_id] = future
        return execution

    def cancel(self, execution_id: UUID) -> dict[str, Any]:
        with self._lock:
            future = self._active.get(execution_id)
        if future is None or future.done() or not future.cancel():
            raise RuntimeError("The active Codex turn cannot be safely cancelled at this stage.")
        result = self.repository.update_execution(
            execution_id, status="CANCELLED",
            cancellation_reason="Cancelled by operator before execution started.",
        )
        self._record_event(execution_id, "EXECUTION_CANCELLED", result["cancellation_reason"])
        self._record_notification(
            task_id=UUID(str(result["task_id"])), execution_id=execution_id,
            notification_type="EXECUTION_CANCELLED",
            title="Developer Agent execution cancelled.",
            detail=result["cancellation_reason"],
        )
        return result

    def recover_interrupted(self) -> int:
        return self.repository.interrupt_running()

    def _run_execution(self, execution_id: UUID, task: dict[str, Any]) -> None:
        started = time.monotonic()
        try:
            self.repository.update_execution(execution_id, status="STARTING")
            self._record_event(
                execution_id, "CODEX_SESSION_STARTING",
                "Starting: execution worker is connecting to Codex.",
            )
            self.repository.update_execution(execution_id, status="RUNNING")
            result = asyncio.run(self.adapter.execute(
                prompt=task["implementation_task"],
                repository=self.repository_path,
                on_session=lambda session_id: self._session_started(
                    execution_id, session_id,
                ),
                on_event=lambda event: self._persist_codex_event(
                    execution_id, event,
                ),
            ))
            self.repository.update_execution(
                execution_id, status="RUNNING",
                codex_session_id=result.session_id,
            )
            if result.error or "completed" not in result.status.lower():
                raise RuntimeError(result.error or f"Codex terminal status: {result.status}")
            self._record_event(
                execution_id, "PREPARING_REPORT",
                "Preparing report from Codex output and repository evidence.",
            )
            report = self._collect_report(
                execution_id=execution_id,
                result=result,
                duration_ms=int((time.monotonic() - started) * 1000),
            )
            self.repository.update_execution(
                execution_id, status="COMPLETED",
                codex_session_id=result.session_id, final_report=report,
            )
            self._record_event(
                execution_id, "EXECUTION_COMPLETED",
                "Codex reported terminal completion and repository evidence was collected.",
            )
            self._record_notification(
                task_id=UUID(str(task["task_id"])), execution_id=execution_id,
                notification_type="EXECUTION_COMPLETED",
                title="Implementation completed.",
                detail="Review the evidence-backed Developer Agent execution report.",
            )
        except BaseException as exc:
            reason = str(exc) or type(exc).__name__
            self.repository.update_execution(
                execution_id, status="FAILED", failure_reason=reason,
            )
            self._record_event(execution_id, "EXECUTION_FAILED", reason)
            self._record_notification(
                task_id=UUID(str(task["task_id"])), execution_id=execution_id,
                notification_type="EXECUTION_FAILED",
                title="Implementation failed.", detail=reason,
            )
        finally:
            with self._lock:
                self._active.pop(execution_id, None)

    def _session_started(self, execution_id: UUID, session_id: str) -> None:
        self.repository.update_execution(
            execution_id, status="RUNNING", codex_session_id=session_id,
        )
        self._record_event(
            execution_id, "CODEX_SESSION_STARTED",
            "Connected to Codex; session identifier captured.",
            {"sessionId": session_id},
        )

    def _persist_codex_event(
        self, execution_id: UUID, event: dict[str, Any],
    ) -> None:
        event_type = str(event.get("type") or "codexEvent")
        command = str(event.get("command") or "")
        lowered = command.lower()
        if event_type == "fileChange":
            semantic, message = "MODIFYING_FILES", "Codex reported a repository file change."
        elif event_type == "commandExecution" and any(
            token in lowered for token in ("pytest", "vitest", "npm test", "unittest")
        ):
            semantic, message = "RUNNING_TESTS", "Codex reported a test command."
        elif event_type == "commandExecution":
            semantic, message = "REPOSITORY_INSPECTION", "Codex reported a repository command."
        elif event_type == "agentMessage" and event.get("phase") == "commentary":
            semantic, message = "PLANNING", str(event.get("text") or "Codex reported planning activity.")
        elif event_type == "agentMessage":
            semantic, message = "CODEX_EVENT", str(event.get("text") or "Codex reported an agent message.")
        else:
            semantic, message = "CODEX_EVENT", event_type
        self._record_event(execution_id, semantic, message, event)

    def _record_event(
        self, execution_id: UUID, event_type: str, message: str,
        event_data: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Persist observability without allowing it to fail the operation."""
        try:
            return self.repository.add_event(
                execution_id, event_type, message, event_data,
            )
        except Exception as error:
            self._telemetry_degraded.add(execution_id)
            try:
                return self.repository.add_event(
                    execution_id,
                    "TELEMETRY_DEGRADED",
                    "A non-critical execution event could not be persisted; execution continued.",
                    {
                        "failedEventType": str(event_type),
                        "persistenceErrorType": type(error).__name__,
                    },
                )
            except Exception:
                return None

    def _record_notification(self, **values: Any) -> dict[str, Any] | None:
        execution_id = values.get("execution_id")
        try:
            return self.repository.create_notification(**values)
        except Exception:
            if execution_id is not None:
                self._telemetry_degraded.add(UUID(str(execution_id)))
            return None

    def _collect_report(self, *, execution_id: UUID, result, duration_ms: int) -> dict[str, Any]:
        events = self.repository.list_events(execution_id)
        commands = []
        tests = []
        for event in events:
            payload = event.get("event_data") or {}
            if payload.get("type") == "command_execution":
                command = {
                    "command": payload.get("command", "Not reported"),
                    "status": payload.get("status", "Not reported"),
                    "exitCode": payload.get("exit_code", payload.get("exitCode", "Not reported")),
                }
                commands.append(command)
                if any(token in str(command["command"]).lower() for token in ("pytest", "vitest", "npm test", "unittest")):
                    tests.append(command)
        status = self._git("status", "--short")
        diff_stat = self._git("diff", "--stat")
        diff_check = self._git_with_code("diff", "--check")
        diff = self._git("diff")
        head = self._git("rev-parse", "HEAD")
        execution = self.repository.get_execution(execution_id) or {}
        initial_head = execution.get("initial_head")
        commit_created = bool(initial_head and head != initial_head)
        return {
            "status": "COMPLETED",
            "summary": result.final_response or "Not reported",
            "rootCause": "Not verified",
            "actionsPerformed": commands,
            "filesModified": status.splitlines(),
            "databaseMigrationsApplied": "Not verified",
            "commandsExecuted": commands,
            "tests": tests or "Not reported",
            "validation": {
                "gitDiffCheck": {"exitCode": diff_check[0], "output": diff_check[1]},
                "currentBranch": self._git("branch", "--show-current"),
                "currentHead": head,
            },
            "remainingWarnings": (
                (["Execution telemetry was degraded; the repository operation completed."]
                 if execution_id in self._telemetry_degraded else [])
                + ([] if diff_check[0] == 0 else [diff_check[1]])
            ),
            "telemetryDegraded": execution_id in self._telemetry_degraded,
            "commitCreated": commit_created,
            "commitHash": head if commit_created else None,
            "executionDurationMs": result.duration_ms or duration_ms,
            "codexSessionId": result.session_id,
            "gitStatusShort": status,
            "gitDiffStat": diff_stat,
            "gitDiff": diff,
        }

    def _validate_repository(self, task: dict[str, Any]) -> None:
        expected = REPOSITORY_PATH.resolve()
        supplied = Path(task["repository_path"]).resolve()
        if supplied != expected or self.repository_path.resolve() != expected:
            raise PermissionError("Repository is not on the Developer Agent allowlist.")
        if not self._is_git_repository():
            raise RuntimeError("Configured repository is not a git repository.")
        branch = self._git("branch", "--show-current")
        if task["expected_branch"] != EXPECTED_BRANCH or branch != EXPECTED_BRANCH:
            raise RuntimeError(
                f"Expected branch {EXPECTED_BRANCH}; current branch is {branch or 'unknown'}."
            )

    def _git(self, *args: str) -> str:
        return self._git_with_code(*args)[1]

    def _is_git_repository(self) -> bool:
        code, value = self._git_with_code("rev-parse", "--is-inside-work-tree")
        if code != 0 or value.lower() != "true":
            return False
        code, git_dir = self._git_with_code("rev-parse", "--git-dir")
        return code == 0 and Path(git_dir).is_dir()

    def _git_with_code(self, *args: str) -> tuple[int, str]:
        result = subprocess.run(
            ["git", *args], cwd=str(self.repository_path),
            capture_output=True, text=True, timeout=60, check=False,
        )
        return result.returncode, (result.stdout or result.stderr).strip()
