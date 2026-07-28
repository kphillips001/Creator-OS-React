"""Authorized Developer Agent task, execution, event and notification API."""
from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.api.developer_authorization import require_developer_authorization
from app.repositories.developer_agent_execution_repository import (
    DeveloperAgentExecutionRepository,
)
from app.services.developer_agent_execution_service import (
    DeveloperAgentExecutionService,
)
from app.api.customers import _account_id
from app.repositories.creator_profile_repository import get_active_creator_profile
from app.repositories.autonomous_issue_resolution_repository import (
    AutonomousIssueResolutionRepository,
)
from app.services.autonomous_issue_resolution_service import (
    AutonomousIssueResolutionService,
)
from app.services.creator_intelligence_service import CreatorIntelligenceService


router = APIRouter(
    prefix="/api/v1/developer-agent",
    tags=["developer-agent-execution"],
    dependencies=[Depends(require_developer_authorization)],
)


class CreateTaskRequest(BaseModel):
    issue_identifier: str = Field(min_length=1, max_length=300)
    investigation_package: str = Field(min_length=1, max_length=100_000)
    implementation_task: str = Field(min_length=1, max_length=100_000)

class DispatchTaskRequest(CreateTaskRequest):
    require_manual_approval: bool = False


class ResolveIssueRequest(BaseModel):
    issue: dict[str, Any]
    investigation_package: str = Field(min_length=1, max_length=100_000)
    implementation_task: str = Field(min_length=1, max_length=100_000)


def _json(value: Any) -> Any:
    if isinstance(value, (UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    if isinstance(value, dict):
        return {key: _json(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_json(item) for item in value]
    return value


def _service() -> DeveloperAgentExecutionService:
    return DeveloperAgentExecutionService()


def _fresh_diagnostics() -> dict[str, Any]:
    account_id = _account_id()
    profile = get_active_creator_profile(str(account_id)) or {}
    return CreatorIntelligenceService().dashboard(
        creator_profile_id=int(profile.get("id") or account_id),
        fanvue_account_id=account_id,
    )


@router.get("/health")
def health():
    return _service().readiness()


@router.post("/tasks", status_code=201)
def create_task(payload: CreateTaskRequest):
    try:
        return _json(_service().create_task(
            issue_identifier=payload.issue_identifier,
            investigation_package=payload.investigation_package,
            implementation_task=payload.implementation_task,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/tasks/dispatch", status_code=202)
def dispatch_task(payload: DispatchTaskRequest):
    try:
        return _json(_service().create_and_dispatch(
            issue_identifier=payload.issue_identifier,
            investigation_package=payload.investigation_package,
            implementation_task=payload.implementation_task,
            require_manual_approval=payload.require_manual_approval,
        ))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/tasks/{task_id}")
def get_task(task_id: UUID):
    item = DeveloperAgentExecutionRepository().get_task(task_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Developer Agent task was not found.")
    return _json(item)


@router.post("/tasks/{task_id}/approve")
def approve_task(task_id: UUID):
    try:
        return _json(_service().approve_task(task_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/reject")
def reject_task(task_id: UUID):
    try:
        return _json(_service().reject_task(task_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/tasks/{task_id}/executions", status_code=202)
def submit_task(task_id: UUID):
    try:
        return _json(_service().submit(task_id))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/executions/{execution_id}")
def get_execution(execution_id: UUID):
    repository = DeveloperAgentExecutionRepository()
    item = repository.get_execution(execution_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Developer Agent execution was not found.")
    item["events"] = repository.list_events(execution_id)
    return _json(item)

@router.get("/history")
def list_executions(limit: int = 20):
    return {
        "items": _json(
            DeveloperAgentExecutionRepository().list_executions(limit=limit)
        )
    }


@router.post("/resolutions", status_code=202)
def resolve_issue(payload: ResolveIssueRequest):
    try:
        return _json(AutonomousIssueResolutionService().resolve(
            issue=payload.issue,
            current_diagnostics=_fresh_diagnostics(),
            investigation_package=payload.investigation_package,
            implementation_task=payload.implementation_task,
        ))
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/resolutions")
def list_resolutions(limit: int = 20):
    return {
        "items": _json(AutonomousIssueResolutionRepository().list(limit=limit))
    }


@router.get("/resolutions/{resolution_id}")
def get_resolution(resolution_id: UUID):
    item = AutonomousIssueResolutionRepository().get(resolution_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Resolution was not found.")
    return _json(item)


@router.post("/resolutions/{resolution_id}/validate")
def validate_resolution(resolution_id: UUID):
    try:
        return _json(AutonomousIssueResolutionService().validate(
            resolution_id, current_diagnostics=_fresh_diagnostics(),
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/executions/{execution_id}/cancel")
def cancel_execution(execution_id: UUID):
    try:
        return _json(_service().cancel(execution_id))
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/executions/{execution_id}/reviews/{status}")
def review_execution(execution_id: UUID, status: str):
    normalized = status.upper()
    if normalized not in {"ACKNOWLEDGED", "REJECTED", "ARCHIVED"}:
        raise HTTPException(status_code=422, detail="Unsupported review status.")
    try:
        return _json(DeveloperAgentExecutionRepository().update_review(
            execution_id, normalized,
        ))
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/notifications")
def list_notifications():
    return {"items": _json(DeveloperAgentExecutionRepository().list_notifications())}


@router.post("/notifications/{notification_id}/read")
def mark_notification_read(notification_id: UUID):
    try:
        return _json(
            DeveloperAgentExecutionRepository().mark_notification_read(notification_id)
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
