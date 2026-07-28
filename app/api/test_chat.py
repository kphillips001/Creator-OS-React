"""Narrow developer-only API for exercising the Sales Agent brain."""

from fastapi import APIRouter, Depends, HTTPException
from app.api.developer_authorization import require_developer_authorization
from pydantic import BaseModel, Field

from app.api.content_studio import _current_account_id
from app.services.test_chat_service import TestChatExecutionError, TestChatService


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
