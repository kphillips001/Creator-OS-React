"""Narrow developer-only API for exercising the Sales Agent brain."""

from fastapi import APIRouter, Depends, HTTPException
from app.api.developer_authorization import require_developer_authorization
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.services.test_chat_service import TestChatExecutionError, TestChatService
from app.services.live_controlled_test_observer_service import (
    LiveControlledTestObserverService, LiveControlledTestUnavailable,
)
from app.services.controlled_test_reset_service import ControlledTestResetService


__test__ = False


router = APIRouter(
    prefix="/api/v1/developer/test-chat",
    tags=["developer-test-chat"],
    dependencies=[Depends(require_developer_authorization)],
)


class TestChatTurnRequest(BaseModel):
    session_id: str = Field(min_length=1)
    customer_message: str = Field(min_length=1, max_length=4000)


class TestChatSessionRequest(BaseModel):
    session_id: str = Field(min_length=1)


class ScenarioPrepareRequest(BaseModel):
    scenario_id: str = Field(pattern=r"^C(?:0[1-9]|1[0-9]|20)$")


class ScenarioTargetRequest(BaseModel):
    scenario_id: str = Field(pattern=r"^C(?:0[1-9]|1[0-9]|20)$")


class ScenarioTurnRequest(BaseModel):
    customer_message: str = Field(min_length=1, max_length=4000)
    language_mode: str = Field(
        default="REAL_AVA_LANGUAGE",
        pattern=r"^(?:REAL_AVA_LANGUAGE|DETERMINISTIC_CERTIFICATION)$",
    )


class ScenarioCompleteRequest(BaseModel):
    grade: str = Field(pattern=r"^(?:PASS|PASS_WITH_NOTES|FAIL)$")


class ScenarioDefectRequest(BaseModel):
    severity: str = Field(pattern=r"^(?:QUALITY|MAJOR|CRITICAL)$")
    note: str = Field(min_length=1, max_length=2000)


class ScenarioRecoveryRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)
    recovery_operation_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9-]{8,80}$",
    )


class ScenarioRestartRequest(BaseModel):
    scenario_id: str = Field(pattern=r"^C(?:0[1-9]|1[0-9]|20)$")
    reason: str | None = Field(default=None, max_length=500)


def _scenario_runner():
    try:
        from app.testing.session5_scenario_runner import Session5ScenarioRunner
        return Session5ScenarioRunner()
    except (PermissionError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


def _scenario_action(action):
    runner = _scenario_runner()
    try:
        result = action(runner)
        return {"result": result, "snapshot": runner.operator_snapshot()}
    except (RuntimeError, ValueError, LookupError, PermissionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("/scenarios")
def scenario_lab_snapshot():
    return _scenario_runner().operator_snapshot()


@router.get("/scenarios/full-analysis")
def scenario_lab_full_analysis(scenario_id: str | None = None):
    try:
        return _scenario_runner().full_attempt_analysis(scenario_id=scenario_id)
    except (RuntimeError, ValueError, LookupError, PermissionError) as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/scenarios/prepare")
def prepare_scenario(request: ScenarioPrepareRequest):
    return _scenario_action(lambda runner: runner.prepare(request.scenario_id))


@router.post("/scenarios/turn")
def scenario_turn(request: ScenarioTurnRequest):
    return _scenario_action(lambda runner: runner.turn(
        request.customer_message, language_mode=request.language_mode,
    ))


@router.post("/scenarios/simulate-purchase")
def scenario_simulate_purchase():
    return _scenario_action(lambda runner: runner.simulate_purchase())


@router.post("/scenarios/retry-previous-turn")
def scenario_retry_previous_turn(request: ScenarioRecoveryRequest):
    return _scenario_action(lambda runner: (
        runner.retry_previous_turn(
            request.reason, recovery_operation_id=request.recovery_operation_id,
        ) if request.recovery_operation_id else runner.retry_previous_turn(request.reason)
    ))


@router.post("/scenarios/restart")
def scenario_restart(request: ScenarioRestartRequest):
    # The runner owns incomplete-attempt archival and the guarded clean restart.
    return _scenario_action(lambda runner: runner.restart_scenario(
        request.scenario_id, request.reason,
    ))


@router.post("/scenarios/defect")
def scenario_defect(request: ScenarioDefectRequest):
    return _scenario_action(lambda runner: runner.defect(request.severity, request.note))


@router.post("/scenarios/complete")
def scenario_complete(request: ScenarioCompleteRequest):
    return _scenario_action(lambda runner: runner.complete(request.grade))


@router.post("/scenarios/snapshot")
def scenario_snapshot(request: ScenarioTargetRequest):
    return _scenario_action(lambda runner: runner.snapshot(request.scenario_id))


@router.post("/scenarios/reset")
def scenario_reset(request: ScenarioTargetRequest):
    return _scenario_action(lambda runner: runner.reset(request.scenario_id))


@router.get("/scenarios/verify-clean")
def scenario_verify_clean():
    return _scenario_runner().verify_clean()


def _service() -> TestChatService:
    account_id = _current_account_id()
    if account_id is None:
        raise HTTPException(status_code=404, detail="Active account required.")
    try:
        return TestChatService(account_id=account_id)
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/sessions")
def new_test_chat():
    return _service().new_session()


@router.post("/turns")
def process_test_chat_turn(request: TestChatTurnRequest):
    try:
        return _service().process(request.session_id, request.customer_message)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except TestChatExecutionError as error:
        raise HTTPException(status_code=502, detail=error.diagnostics) from error


@router.post("/clear")
def clear_test_chat(request: TestChatSessionRequest):
    try:
        return _service().clear_chat(request.session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/reset-memory")
def reset_test_chat_memory(request: TestChatSessionRequest):
    try:
        return _service().reset_memory(request.session_id)
    except KeyError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/live")
def live_controlled_test_snapshot():
    try:
        return LiveControlledTestObserverService().snapshot()
    except LiveControlledTestUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("/live/reset-dry-run")
def live_controlled_test_reset_dry_run():
    try:
        return LiveControlledTestObserverService().reset_dry_run()
    except LiveControlledTestUnavailable as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.post("/live/reset")
def reset_live_controlled_test():
    try:
        result = ControlledTestResetService().execute()
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    if not result.get("executed"):
        raise HTTPException(status_code=409, detail=result)
    return result
