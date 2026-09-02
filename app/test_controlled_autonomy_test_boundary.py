import asyncio
import json
from types import SimpleNamespace

import pytest

from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.services.controlled_autonomy_test_service import ControlledAutonomyTestService
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.private_chat_unlock_gateway_service import (
    PrivateChatUnlockGatewayService,
    UnlockUnavailableError,
)


TEST_USER_ID = 7812345698
TEST_CHAT_ID = 7812345698


class Transport:
    def set_inbound_handler(self, handler): self.handler = handler
    async def disconnect(self): return None


class Inbound:
    def __init__(self): self.payloads = []
    def execute(self, payload):
        self.payloads.append(payload)
        return TelegramInboundResult(
            correlation_id=f"telegram:{payload.telegram_chat_id}:{payload.message_id}",
            telegram_chat_id=payload.telegram_chat_id,
            telegram_user_id=payload.telegram_user_id,
            message_id=payload.message_id,
            engine_user_id=f"test:{payload.telegram_user_id}",
            response_text="", offer_authorized=False, offer_link=None,
            blocked=False, error_code=None, delivery_payload={},
            diagnostic_metadata={},
        )


def configure(monkeypatch):
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "true")
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_USER_ID", str(TEST_USER_ID))
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID", str(TEST_CHAT_ID))


def test_boundary_defaults_off_and_requires_complete_numeric_identity(monkeypatch):
    for key in (
        "CONTROLLED_AUTONOMY_TEST_ENABLED",
        "CONTROLLED_AUTONOMY_TELEGRAM_USER_ID",
        "CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID",
    ):
        monkeypatch.delenv(key, raising=False)
    boundary = ControlledAutonomyTestService()
    assert not boundary.decide(
        telegram_user_id=TEST_USER_ID, telegram_chat_id=TEST_CHAT_ID,
    ).allowed
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "true")
    assert boundary.configured_identity() is None


def test_context_allows_only_exact_numeric_identity_while_global_remains_off(
    monkeypatch, tmp_path,
):
    configure(monkeypatch)
    config = tmp_path / "behavior.json"
    config.write_text(json.dumps({"global_automation_enabled": False}))
    monkeypatch.setattr(GlobalAutomationSafetyService, "CONFIG_PATH", config)
    boundary = ControlledAutonomyTestService()
    safety = GlobalAutomationSafetyService()
    assert safety.check_global_safety()["reason"] == "global_automation_disabled"
    with boundary.scope(
        telegram_user_id=TEST_USER_ID, telegram_chat_id=TEST_CHAT_ID,
    ):
        decision = safety.check_global_safety()
        assert decision["allowed"] is True
        assert decision["source"] == "controlled_telegram_test_boundary"
    assert safety.check_global_safety()["allowed"] is False
    assert not boundary.decide(
        telegram_user_id=TEST_USER_ID + 1, telegram_chat_id=TEST_CHAT_ID + 1,
    ).allowed


def test_runtime_allows_exact_id_and_blocks_unknown_and_username_collision(
    monkeypatch, tmp_path,
):
    configure(monkeypatch)
    config = tmp_path / "behavior.json"
    config.write_text(json.dumps({"global_automation_enabled": False}))
    monkeypatch.setattr(GlobalAutomationSafetyService, "CONFIG_PATH", config)
    inbound = Inbound()
    runtime = TelethonRuntime(
        transport=Transport(), inbound_adapter=inbound,
        global_safety_service=GlobalAutomationSafetyService(),
    )
    async def exercise():
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=TEST_USER_ID, telegram_chat_id=TEST_CHAT_ID,
            telegram_username="same-name", message_text="hello", message_id=1,
        ))
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=TEST_USER_ID + 1,
            telegram_chat_id=TEST_CHAT_ID + 1,
            telegram_username="same-name", message_text="hello", message_id=2,
        ))
    asyncio.run(exercise())
    assert [item.telegram_user_id for item in inbound.payloads] == [TEST_USER_ID]


def test_new_service_instance_preserves_env_allowlist_across_restart(monkeypatch):
    configure(monkeypatch)
    assert ControlledAutonomyTestService().decide(
        telegram_user_id=TEST_USER_ID, telegram_chat_id=TEST_CHAT_ID,
    ).allowed
    audit = ControlledAutonomyTestService().audit_metadata()
    assert audit["controlled_autonomy_test_enabled"] is True
    assert len(audit["controlled_autonomy_identity_fingerprint"]) == 12
    assert str(TEST_USER_ID) not in audit["controlled_autonomy_identity_fingerprint"]
    assert ControlledAutonomyTestService().decide(
        telegram_user_id=TEST_USER_ID, telegram_chat_id=TEST_CHAT_ID,
    ).allowed


def test_unlock_fails_closed_outside_controlled_identity(monkeypatch):
    configure(monkeypatch)
    monkeypatch.setenv("PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED", "true")
    service = PrivateChatUnlockGatewayService(
        repository=SimpleNamespace(), token_secret="s" * 32,
    )
    wrong = SimpleNamespace(
        telegram_user_id=TEST_USER_ID + 1,
        telegram_chat_id=TEST_CHAT_ID + 1,
    )
    with pytest.raises(UnlockUnavailableError, match="controlled test boundary"):
        service.issue(wrong)
