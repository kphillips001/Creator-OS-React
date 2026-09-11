from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from app.models.commerce_mode import CommerceMode
from app.models.runtime_control import RuntimeMode
from app.services.ava_bot_control_service import AvaBotControlService
from app.services.global_selling_permissions_service import GlobalSellingPermissionsService


class ConfigStore:
    def __init__(self, **overrides):
        self.value = {
            "global_automation_enabled": False,
            "global_sends_enabled": True,
            "manual_pause_enabled": False,
            "commerce_mode": "OFF",
            "modules": {"main_chat_enabled": False, "ppv_offers_enabled": False},
            **overrides,
        }

    def load(self):
        return self.value.copy() | {"modules": dict(self.value.get("modules", {}))}, {}

    def save(self, value):
        self.value = value


class Runtime:
    def __init__(self, mode=RuntimeMode.OFFLINE, fail=False):
        self.mode, self.fail, self.starts, self.stops = mode, fail, 0, 0

    def get_state(self, **_):
        return SimpleNamespace(mode=self.mode)

    def start(self, **_):
        self.starts += 1
        if self.fail:
            raise RuntimeError("runtime failure")
        self.mode = RuntimeMode.LIVE


class Commerce:
    def __init__(self, store, fail=False):
        self.store, self.fail = store, fail

    def get_mode(self):
        return CommerceMode(str(self.store.value.get("commerce_mode", "OFF")))

    def set_mode(self, mode):
        if self.fail:
            raise RuntimeError("commerce failure")
        self.store.value["commerce_mode"] = mode.value


class Controlled:
    def __init__(self, enabled=False): self.enabled = enabled
    def configured_identity(self): return (1, 1) if self.enabled else None


def service(store, *, runtime=None, commerce=None, controlled=None,
            worker=True, transport=True):
    return AvaBotControlService(
        runtime_service=runtime or Runtime(),
        commerce_mode_service=commerce or Commerce(store),
        controlled_autonomy_service=controlled or Controlled(),
        config_loader=store.load, config_saver=store.save,
        worker_readiness=lambda _: {"ready": worker},
        transport_readiness=lambda: {"ready": transport},
    )


def test_global_permissions_default_off_and_persist_independently():
    store = ConfigStore()
    permissions = GlobalSellingPermissionsService(
        config_loader=store.load, config_saver=store.save)
    assert permissions.read() == {
        "contentSellingEnabled": False, "sessionSellingEnabled": False}
    permissions.set_content(True)
    assert permissions.read() == {
        "contentSellingEnabled": True, "sessionSellingEnabled": False}


@pytest.mark.parametrize("content,session", [
    (False, False), (True, False), (False, True), (True, True),
])
def test_global_selling_permissions_cover_every_independent_combination(
    content, session,
):
    store = ConfigStore(
        content_selling_enabled=content,
        session_selling_enabled=session,
    )
    assert GlobalSellingPermissionsService(
        config_loader=store.load, config_saver=store.save,
    ).read() == {
        "contentSellingEnabled": content,
        "sessionSellingEnabled": session,
    }


def test_ava_bot_successful_on_prepares_compatibility_and_enables_last(monkeypatch):
    monkeypatch.setenv("TELEGRAM_REPLIES_ENABLED", "true")
    monkeypatch.setenv("TG_API_ID", "1")
    monkeypatch.setenv("TG_API_HASH", "hash")
    store, runtime = ConfigStore(), Runtime()
    result = service(store, runtime=runtime).turn_on(creator_profile_id=1)
    assert result["success"] is True
    assert result["state"]["avaBot"]["effective"] == "ON"
    assert runtime.starts == 1
    assert store.value["modules"]["main_chat_enabled"] is True
    assert store.value["modules"]["ppv_offers_enabled"] is True


@pytest.mark.parametrize("overrides,worker,transport,controlled,reason", [
    ({"global_sends_enabled": False}, True, True, False, "global_sends_disabled"),
    ({"manual_pause_enabled": True}, True, True, False, "manual_pause_enabled"),
    ({}, False, True, False, "telegram_worker_unhealthy"),
    ({}, True, False, False, "telegram_transport_unavailable"),
    ({}, True, True, True, "controlled_autonomy_test_enabled"),
])
def test_ava_bot_on_hard_blockers_leave_automation_off(
    monkeypatch, overrides, worker, transport, controlled, reason,
):
    monkeypatch.setenv("TELEGRAM_REPLIES_ENABLED", "true")
    store = ConfigStore(**overrides)
    result = service(store, worker=worker, transport=transport,
                     controlled=Controlled(controlled)).turn_on(creator_profile_id=1)
    assert result["success"] is False
    assert result["reason"] == reason
    assert store.value["global_automation_enabled"] is False


def test_runtime_or_commerce_failure_leaves_automation_off(monkeypatch):
    monkeypatch.setenv("TELEGRAM_REPLIES_ENABLED", "true")
    for failing in ("runtime", "commerce"):
        store = ConfigStore()
        result = service(
            store,
            runtime=Runtime(fail=failing == "runtime"),
            commerce=Commerce(store, fail=failing == "commerce"),
        ).turn_on(creator_profile_id=1)
        assert result["success"] is False
        assert store.value["global_automation_enabled"] is False


def test_turn_off_only_changes_global_automation(monkeypatch):
    monkeypatch.setenv("TELEGRAM_REPLIES_ENABLED", "true")
    store = ConfigStore(global_automation_enabled=True, commerce_mode="LIVE",
                        content_selling_enabled=True, session_selling_enabled=True)
    runtime = Runtime(RuntimeMode.LIVE)
    before = dict(store.value)
    result = service(store, runtime=runtime).turn_off(creator_profile_id=1)
    assert result["success"] is True
    assert store.value["global_automation_enabled"] is False
    assert store.value["commerce_mode"] == before["commerce_mode"]
    assert runtime.mode == RuntimeMode.LIVE
    assert store.value["content_selling_enabled"] is True
    assert store.value["session_selling_enabled"] is True


def test_worker_diagnostic_failure_is_fail_closed_attention(monkeypatch):
    monkeypatch.setattr(
        "app.services.operations_workspace_service.OperationsWorkspaceService.workers",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            TypeError("mixed diagnostic timestamps")),
    )
    result = AvaBotControlService._default_worker_readiness(1)
    assert result == {
        "ready": False,
        "reason": "Worker readiness could not be verified.",
    }


def test_genuine_worker_readiness_failure_keeps_enabled_bot_at_attention():
    store = ConfigStore(global_automation_enabled=True, commerce_mode="LIVE",
                        modules={"main_chat_enabled": True,
                                 "ppv_offers_enabled": True})
    result = service(store, runtime=Runtime(RuntimeMode.LIVE), worker=False).read(
        creator_profile_id=1)
    assert result["avaBot"]["desired"] == "ON"
    assert result["avaBot"]["effective"] == "ATTENTION"
    assert result["avaBot"]["reason"] == "Telegram worker is unavailable."
