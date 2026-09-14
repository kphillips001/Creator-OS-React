from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.api.relationships import RepairExecutionCreate, execute_conversation_repair
from app.services.conversation_repair_execution_gate import (
    ConversationRepairExecutionDisabled,
    ConversationRepairExecutionGate,
)
from app.services.conversation_repair_executor_service import (
    ConversationRepairExecutorService,
)


@pytest.mark.parametrize("environment", [{}, {"CONVERSATION_REPAIR_EXECUTION_ENABLED": "false"},
                                           {"CONVERSATION_REPAIR_EXECUTION_ENABLED": "invalid"}])
def test_missing_false_and_invalid_configuration_fail_closed(environment):
    gate = ConversationRepairExecutionGate(environment)
    assert gate.enabled() is False
    with pytest.raises(ConversationRepairExecutionDisabled, match="CONVERSATION REPAIR EXECUTION DISABLED"):
        gate.require_enabled()


@pytest.mark.parametrize("git_state", ["clean", "dirty"])
def test_direct_service_rejects_before_repository_safety_or_developer_activity(git_state):
    calls = {"repository": 0, "safety": 0, "developer": 0}

    class Repository:
        def claim(self, **_values):
            calls["repository"] += 1

    class Authorizations:
        def authorization(self, *_args, **_kwargs):
            calls["repository"] += 1

    class Developer:
        def create_and_dispatch(self, **_values):
            calls["developer"] += 1

    def safety():
        calls["safety"] += 1
        return {"safe": git_state == "clean", "reason": None}

    service = ConversationRepairExecutorService(
        repository=Repository(), authorization_repository=Authorizations(),
        developer_factory=lambda _stage: Developer(), safety=safety, analyses=object(),
        execution_gate=ConversationRepairExecutionGate({}),
    )
    with pytest.raises(ConversationRepairExecutionDisabled):
        service.execute(uuid4(), operator="operator", creator_profile_id=1,
                        fanvue_account_id=2, telegram_user_id=3,
                        telegram_chat_id=3, relationship_key="telegram:1:2:3")
    assert calls == {"repository": 0, "safety": 0, "developer": 0}


def test_api_rejects_before_constructing_executor(monkeypatch):
    monkeypatch.delenv("CONVERSATION_REPAIR_EXECUTION_ENABLED", raising=False)
    with pytest.raises(HTTPException) as error:
        execute_conversation_repair("unused", RepairExecutionCreate(authorizationId=uuid4()))
    assert error.value.status_code == 409
    assert error.value.detail == "CONVERSATION REPAIR EXECUTION DISABLED"
