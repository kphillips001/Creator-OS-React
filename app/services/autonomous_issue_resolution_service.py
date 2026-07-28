"""Evidence-based orchestration from diagnostics to Developer Agent validation."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.models.autonomous_issue_resolution import ResolutionDecision, ResolutionOutcome
from app.repositories.autonomous_issue_resolution_repository import (
    AutonomousIssueResolutionRepository,
)
from app.repositories.developer_agent_execution_repository import (
    DeveloperAgentExecutionRepository,
)
from app.services.developer_agent_execution_service import DeveloperAgentExecutionService


class AutonomousIssueResolutionService:
    def __init__(
        self, *, repository: Any | None = None, developer_agent: Any | None = None,
        execution_repository: Any | None = None,
    ) -> None:
        self.repository = repository or AutonomousIssueResolutionRepository()
        self.developer_agent = developer_agent or DeveloperAgentExecutionService()
        self.executions = execution_repository or DeveloperAgentExecutionRepository()

    @staticmethod
    def issue_is_resolved(issue_identifier: str, diagnostics: dict[str, Any]) -> bool:
        normalized = issue_identifier.strip().lower()
        problems = diagnostics.get("problems") or []
        health = diagnostics.get("systemHealth") or []
        still_problem = any(
            str(item.get("title", "")).strip().lower() == normalized
            for item in problems
        )
        matching = next((
            item for item in health
            if str(item.get("label", "")).strip().lower() == normalized
        ), None)
        return not still_problem and (
            matching is None or matching.get("status") == "Healthy"
        )

    @staticmethod
    def classify(issue: dict[str, Any], current: dict[str, Any]) -> tuple[str, str, str | None]:
        identifier = str(issue.get("component") or issue.get("issue_identifier") or "")
        if AutonomousIssueResolutionService.issue_is_resolved(identifier, current):
            return (
                ResolutionDecision.ALREADY_RESOLVED.value,
                "Fresh Creator Intelligence diagnostics no longer report this issue.",
                None,
            )
        diagnostic = issue.get("diagnostic") if isinstance(issue.get("diagnostic"), dict) else issue
        classification = str(diagnostic.get("classification") or "UNKNOWN").upper()
        automatic = diagnostic.get("automatic_resolution")
        reason = str(diagnostic.get("resolution_reason") or "").strip()
        action = str(diagnostic.get("recommended_action") or "").strip() or None
        if classification == "CONFIGURATION_REQUIRED":
            return (
                ResolutionDecision.CONFIGURATION_REQUIRED.value,
                reason or "The structured diagnostic requires configuration.",
                action,
            )
        if classification == "USER_ACTION_REQUIRED":
            return (
                ResolutionDecision.USER_ACTION_REQUIRED.value,
                reason or "The structured diagnostic requires an operator action.",
                action,
            )
        if classification in {
            "CACHED", "STALE_CACHE", "STALE_CERTIFICATION",
            "PROJECTION_MISMATCH",
        }:
            return (
                ResolutionDecision.NOT_FIXABLE.value,
                "Fresh diagnostics still report stale or mismatched projection evidence; code execution is suppressed.",
                action or "Refresh the authoritative diagnostic source and re-evaluate.",
            )
        if automatic is True:
            return (
                ResolutionDecision.AUTO_FIX.value,
                reason or "The structured diagnostic authorizes automatic repository repair.",
                None,
            )
        if not identifier or classification in {"UNKNOWN", "UNKNOWN_INTERNAL_FAILURE"}:
            return (
                ResolutionDecision.NOT_FIXABLE.value,
                reason or "The structured diagnostic does not contain enough evidence for safe repair.",
                action or "Collect additional diagnostic evidence before retrying.",
            )
        return (
            ResolutionDecision.NOT_FIXABLE.value,
            reason or "The structured diagnostic explicitly disallows automatic repair.",
            action,
        )

    def resolve(
        self, *, issue: dict[str, Any], current_diagnostics: dict[str, Any],
        investigation_package: str, implementation_task: str,
    ) -> dict[str, Any]:
        decision, reason, action = self.classify(issue, current_diagnostics)
        terminal = decision != ResolutionDecision.AUTO_FIX.value
        outcome = (
            ResolutionOutcome.ALREADY_RESOLVED.value
            if decision == ResolutionDecision.ALREADY_RESOLVED.value
            else ResolutionOutcome.USER_ACTION_REQUIRED.value
            if terminal else ResolutionOutcome.IN_PROGRESS.value
        )
        record = self.repository.create(
            issue_identifier=str(issue.get("component") or issue.get("issue_identifier")),
            issue_snapshot=issue, decision=decision, decision_reason=reason,
            required_action=action,
            destination_path=(issue.get("destination") or {}).get("path"),
            validation_status="NOT_REQUIRED" if terminal else "PENDING",
            outcome=outcome,
        )
        if decision != ResolutionDecision.AUTO_FIX.value:
            return {"resolution": record, "task": None, "execution": None}
        try:
            dispatched = self.developer_agent.create_and_dispatch(
                issue_identifier=record["issue_identifier"],
                investigation_package=investigation_package,
                implementation_task=implementation_task,
                require_manual_approval=False,
            )
            if dispatched.get("execution") is None:
                raise RuntimeError("Autonomous resolution requires an accepted execution.")
        except Exception as exc:
            self.repository.finalize(
                record["resolution_id"], validation_status="FAILED",
                outcome=ResolutionOutcome.COULD_NOT_RESOLVE.value,
                evidence={"dispatchError": str(exc)},
            )
            raise
        updated = self.repository.attach_execution(
            record["resolution_id"],
            task_id=dispatched["task"]["task_id"],
            execution_id=dispatched["execution"]["execution_id"],
        )
        return {"resolution": updated, **dispatched}

    def validate(
        self, resolution_id: UUID, *, current_diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        record = self.repository.get(resolution_id)
        if record is None:
            raise ValueError("Autonomous issue resolution was not found.")
        if record["decision"] != ResolutionDecision.AUTO_FIX.value:
            return record
        execution = self.executions.get_execution(record["developer_agent_execution_id"])
        if execution is None or execution["status"] not in {
            "COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED",
        }:
            raise RuntimeError("Developer Agent execution has not reached a terminal state.")
        if execution["status"] != "COMPLETED":
            return self.repository.finalize(
                resolution_id, validation_status="FAILED",
                outcome=ResolutionOutcome.COULD_NOT_RESOLVE.value,
                evidence={"executionStatus": execution["status"],
                          "failureReason": execution.get("failure_reason")},
            )
        resolved = self.issue_is_resolved(record["issue_identifier"], current_diagnostics)
        return self.repository.finalize(
            resolution_id,
            validation_status="PASSED" if resolved else "FAILED",
            outcome=(ResolutionOutcome.RESOLVED.value if resolved
                     else ResolutionOutcome.PARTIALLY_RESOLVED.value),
            evidence={
                "freshDiagnosticsGeneratedAt": str(
                    current_diagnostics.get("generatedAt") or ""
                ),
                "issueStillPresent": not resolved,
                "matchingProblems": [
                    item for item in current_diagnostics.get("problems", [])
                    if str(item.get("title", "")).lower()
                    == record["issue_identifier"].lower()
                ],
            },
        )
