from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import operations as api
from app.models.runtime_control import RuntimeMode, RuntimeStatus
from app.services.module_switches_service import ModuleSwitchesService


NOW = datetime(2026, 7, 19, tzinfo=timezone.utc)


class Runtime:
    def __init__(self): self.states = {}; self.calls = []
    def get_state(self, *, creator_profile_id):
        return self.states.setdefault(str(creator_profile_id), SimpleNamespace(mode=RuntimeMode.OFFLINE,
            status=RuntimeStatus.OFFLINE, updated_at=NOW))
    def evaluate_runtime(self, *, creator_profile_id):
        state = self.get_state(creator_profile_id=creator_profile_id)
        return SimpleNamespace(mode=state.mode, reason=f"runtime_{state.mode.value.lower()}")
    def _set(self, profile, mode):
        self.calls.append((str(profile), mode.value)); self.states[str(profile)] = SimpleNamespace(mode=mode,
            status=RuntimeStatus(mode.value), updated_at=NOW)
    def stop(self, *, creator_profile_id): self._set(creator_profile_id, RuntimeMode.OFFLINE)
    def observe(self, *, creator_profile_id): self._set(creator_profile_id, RuntimeMode.OBSERVE)
    def start(self, *, creator_profile_id): self._set(creator_profile_id, RuntimeMode.LIVE)


class Safety:
    def __init__(self, config): self.config = config
    def check_global_safety(self):
        if not self.config.get("global_automation_enabled"): return {"allowed": False, "reason": "global_automation_disabled"}
        if not self.config.get("global_sends_enabled"): return {"allowed": False, "reason": "global_sends_disabled"}
        if self.config.get("manual_pause_enabled"): return {"allowed": False, "reason": "manual_pause_enabled"}
        return {"allowed": True, "reason": None}
    def _module(self, key):
        global_result = self.check_global_safety()
        if not global_result["allowed"]: return global_result
        return {"allowed": bool(self.config["modules"].get(key)), "reason": None if self.config["modules"].get(key) else f"{key}_disabled"}
    def can_send_chat(self): return self._module("main_chat_enabled")
    def can_send_outreach(self): return self._module("outreach_enabled")
    def can_send_delayed_followup(self): return self._module("delayed_followups_enabled")
    def can_send_reactivation(self): return self._module("reactivation_enabled")
    def can_send_mass_ppv(self): return self._module("mass_ppv_enabled")
    def can_send_post_purchase_reaction(self): return self._module("post_purchase_reactions_enabled")


class Operations:
    def workers(self, *, account_id): return {"summary": {"healthy": 1, "untracked": 5, "account": account_id}}


def boundary():
    store = {"global_automation_enabled": True, "global_sends_enabled": True, "manual_pause_enabled": False,
             "modules": {key: True for key in ("main_chat_enabled", "outreach_enabled", "delayed_followups_enabled",
                         "reactivation_enabled", "mass_ppv_enabled", "post_purchase_reactions_enabled")}}
    runtime = Runtime(); saved = []
    def load(): return deepcopy(store), {}
    def save(value): store.clear(); store.update(deepcopy(value)); saved.append(deepcopy(value))
    service = ModuleSwitchesService(runtime_service=runtime, safety_factory=lambda: Safety(store),
        config_loader=load, config_saver=save, operations_service=Operations())
    return service, store, runtime, saved


def test_reads_configured_effective_and_unimplemented_states():
    service, _, _, _ = boundary()
    result = service.read(creator_profile_id=7)
    reply = next(item for item in result["cards"]["Messaging"] if item["key"] == "telegram_replies")
    assert reply == {"key": "telegram_replies", "label": "Telegram Replies", "configured": True,
                     "effective": "ACTIVE", "reason": None, "editable": True, "implemented": True}
    assert next(item for item in result["cards"]["Publishing"] if item["key"] == "telegram_wall")["effective"] == "NOT_IMPLEMENTED"
    assert next(item for item in result["cards"]["AI"] if item["key"] == "sales_agent")["editable"] is False
    assert result["globalStatus"]["heartbeatSummary"]["account"] == 7
    assert [item["label"] for item in result["deploymentReadiness"]] == [
        "Fanvue Live Replies", "Mass PPV Live Transport", "Reaction Live Execution",
        "Telegram Runtime Readiness", "Webhook Processing",
    ]
    assert all(item["editable"] is False and item["source"] == "Environment"
               for item in result["deploymentReadiness"])


def test_operator_projections_ignore_deployment_permits(monkeypatch):
    for variable in ("ENABLE_REALTIME_FANVUE_SEND", "ENABLE_MASS_PPV_SENDS",
                     "ENABLE_REALTIME_MONETIZATION_REACTIONS"):
        monkeypatch.setenv(variable, "false")
    service, _, _, _ = boundary()
    result = service.read(creator_profile_id=7)
    projected = {item["key"]: item for card in ("Messaging", "Sales")
                 for item in result["cards"][card] if item["editable"]}
    assert projected["telegram_replies"]["effective"] == "ACTIVE"
    assert projected["mass_ppv"]["effective"] == "ACTIVE"
    assert projected["purchase_reactions"]["effective"] == "ACTIVE"
    assert all(item["reason"] is None for item in projected.values())
    readiness = {item["key"]: item for item in result["deploymentReadiness"]}
    assert readiness["fanvue_live_replies"]["status"] == "BLOCKED"
    assert readiness["mass_ppv_live_transport"]["currentValue"] == "Disabled"
    assert readiness["reaction_live_execution"]["restartRequired"] is True


def test_offline_runtime_does_not_block_normal_module_projection():
    service, _, runtime, _ = boundary()
    assert runtime.get_state(creator_profile_id=7).mode is RuntimeMode.OFFLINE
    result = service.read(creator_profile_id=7)
    projected = [item for card in ("Messaging", "Sales") for item in result["cards"][card] if item["editable"]]
    assert all(item["effective"] == "ACTIVE" for item in projected)
    assert all(item["reason"] != "runtime_offline" for item in projected)


def test_updates_existing_behavior_config_and_recalculates_effective_state():
    service, store, runtime, saved = boundary(); runtime.start(creator_profile_id=7)
    result = service.update("mass_ppv", False, creator_profile_id=7)
    item = next(item for item in result["cards"]["Sales"] if item["key"] == "mass_ppv")
    assert store["modules"]["mass_ppv_enabled"] is False and item["effective"] == "OFF"
    assert len(saved) == 1


def test_master_update_preserves_runtime_and_other_safety_configuration():
    service, store, runtime, saved = boundary()
    original_modules = deepcopy(store["modules"])
    result = service.update("global_automation", False, creator_profile_id=7)
    assert store["global_automation_enabled"] is False
    assert store["global_sends_enabled"] is True
    assert store["manual_pause_enabled"] is False
    assert store["modules"] == original_modules
    assert runtime.calls == [] and len(saved) == 1
    assert result["masterControl"]["effective"] == "BLOCKED"
    assert result["masterControl"]["reason"] == "Autonomous Sales & Messaging is OFF"
    assert all(item["effective"] == "BLOCKED" for card in ("Messaging", "Sales", "Publishing")
               for item in result["cards"][card])


def test_runtime_updates_are_creator_scoped_and_do_not_rewrite_module_config():
    service, store, runtime, saved = boundary(); original = deepcopy(store)
    service.update("runtime", "OBSERVE", creator_profile_id=7)
    service.update("runtime", "LIVE", creator_profile_id=8)
    assert runtime.calls == [("7", "OBSERVE"), ("8", "LIVE")]
    assert store == original and saved == []


def test_validation_rejects_unknown_informational_and_invalid_values():
    service, _, _, _ = boundary()
    for module, value in (("runtime", "invalid"), ("mass_ppv", "yes"), ("telegram_wall", True), ("unknown", True)):
        try: service.update(module, value, creator_profile_id=7)
        except ValueError: pass
        else: raise AssertionError(f"Expected {module} validation failure")


def test_api_reads_and_patches_without_transport_execution(monkeypatch):
    service, store, runtime, _ = boundary()
    monkeypatch.setattr(api, "_module_switches_service", lambda: service)
    monkeypatch.setattr(api, "_account_id", lambda: 7)
    app = FastAPI(); app.include_router(api.router); client = TestClient(app)
    assert client.get("/api/v1/operations/module-switches").status_code == 200
    response = client.patch("/api/v1/operations/module-switches/delayed_messages", json={"value": False})
    assert response.status_code == 200 and store["modules"]["delayed_followups_enabled"] is False
    assert client.patch("/api/v1/operations/module-switches/runtime", json={"value": "LIVE"}).status_code == 200
    assert runtime.calls[-1] == ("7", "LIVE")
    assert client.patch("/api/v1/operations/module-switches/unknown", json={"value": True}).status_code == 422


def test_service_contains_no_execution_or_transport_dependencies():
    from pathlib import Path
    source = Path("app/services/module_switches_service.py").read_text(encoding="utf-8")
    for forbidden in ("send_message", "process_outreach", "process_due", "publish(", "claim_due_items", "start_worker"):
        assert forbidden not in source
