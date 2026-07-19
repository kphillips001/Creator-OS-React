from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import Mock

from app.models.telegram_commerce import TelegramDeliveryPayload
from app.services.global_automation_safety_service import GlobalAutomationSafetyService
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor


class MutableSafety:
    def __init__(self, allowed=False):
        self.allowed = allowed

    def check_global_safety(self):
        return {"allowed": self.allowed, "blocked": not self.allowed,
                "reason": None if self.allowed else "global_automation_disabled",
                "source": "dashboard_config"}


def test_long_running_safety_service_reloads_master_switch(tmp_path, monkeypatch):
    path = tmp_path / "behavior_config.json"
    path.write_text(json.dumps({"global_automation_enabled": True,
                                "global_sends_enabled": True,
                                "manual_pause_enabled": False}), encoding="utf-8")
    monkeypatch.setattr(GlobalAutomationSafetyService, "CONFIG_PATH", path)
    safety = GlobalAutomationSafetyService()
    assert safety.check_global_safety()["allowed"] is True
    path.write_text(json.dumps({"global_automation_enabled": False,
                                "global_sends_enabled": True,
                                "manual_pause_enabled": False}), encoding="utf-8")
    assert safety.check_global_safety()["reason"] == "global_automation_disabled"


def test_telegram_final_boundary_does_not_call_transport_when_off():
    sender = Mock()
    result = TelegramDeliveryExecutor(global_safety_service=MutableSafety(False)).execute(
        TelegramDeliveryPayload(message_text="Never send", delivery_method="text"),
        context={"chat_id": 7, "text_sender": sender},
    )
    assert result.status == "blocked"
    assert result.executed is False
    assert result.blocking_reason == "global_automation_disabled"
    sender.send_text.assert_not_called()


def test_reenable_allows_future_telegram_execution():
    safety = MutableSafety(False)
    sender = Mock()
    executor = TelegramDeliveryExecutor(global_safety_service=safety)
    payload = TelegramDeliveryPayload(message_text="Eligible later", delivery_method="text")
    assert executor.execute(payload, context={"chat_id": 7, "text_sender": sender}).executed is False
    safety.allowed = True
    assert executor.execute(payload, context={"chat_id": 7, "text_sender": sender}).executed is True
    sender.send_text.assert_called_once()


def test_workers_skip_before_claim_without_queue_mutation(monkeypatch):
    from app.services import delayed_message_worker_service as delayed
    from app.services import mass_ppv_worker_service as mass
    from app.services import outreach_worker_service as outreach
    from app.services import wall_worker_service as wall

    claims = {"outreach": 0, "delayed": 0, "mass": 0, "wall": 0}
    for module, key in ((outreach, "outreach"), (delayed, "delayed"),
                        (mass, "mass"), (wall, "wall")):
        monkeypatch.setattr(module, "claim_due_items", lambda *args, _key=key, **kwargs: claims.__setitem__(_key, claims[_key] + 1) or [])

    blocked = MutableSafety(False)
    outreach_worker = outreach.OutreachWorkerService.__new__(outreach.OutreachWorkerService)
    outreach_worker.worker_instance_id = "outreach-test"
    outreach_worker.global_safety_service = blocked
    delayed_worker = delayed.DelayedMessageWorkerService.__new__(delayed.DelayedMessageWorkerService)
    delayed_worker.worker_instance_id = "delayed-test"; delayed_worker.fanvue_account_id = None
    delayed_worker.global_safety_service = blocked; delayed_worker.logger = Mock()
    mass_worker = mass.MassPPVWorkerService.__new__(mass.MassPPVWorkerService)
    mass_worker.worker_instance_id = "mass-test"
    mass_worker.send_service = SimpleNamespace(global_safety=blocked)
    wall_worker = wall.WallWorkerService.__new__(wall.WallWorkerService)
    wall_worker.worker_instance_id = "wall-test"; wall_worker.global_safety_service = blocked

    assert outreach_worker.process_outreach_queue()["processed_count"] == 0
    assert delayed_worker.process_due_messages() == []
    assert mass_worker.process_pending_queue() == []
    assert wall_worker.process_wall_queue()["processed_count"] == 0
    assert claims == {"outreach": 0, "delayed": 0, "mass": 0, "wall": 0}


def test_operator_safety_ignores_only_autonomy_master(tmp_path, monkeypatch):
    path = tmp_path / "behavior_config.json"
    path.write_text(json.dumps({"global_automation_enabled": False,
                                "global_sends_enabled": True,
                                "manual_pause_enabled": False}), encoding="utf-8")
    monkeypatch.setattr(GlobalAutomationSafetyService, "CONFIG_PATH", path)
    safety = GlobalAutomationSafetyService()
    assert safety.check_global_safety()["allowed"] is False
    assert safety.check_operator_send_safety()["allowed"] is True


def test_blocked_worker_cycle_still_records_idle_heartbeat():
    from app.services.delayed_message_worker_loop_service import DelayedMessageWorkerLoopService

    events = []
    heartbeat = SimpleNamespace(
        worker_instance_id="heartbeat-test",
        register_startup=lambda: events.append("startup"),
        record_poll=lambda: events.append("poll"),
        record_success=lambda **kwargs: events.append(("success", kwargs["idle"])),
        record_stopping=lambda: events.append("stopping"),
        record_shutdown=lambda: events.append("shutdown"),
        record_failure=lambda error: events.append(("failure", type(error).__name__)),
    )
    worker = SimpleNamespace(worker_instance_id="worker-test", process_due_messages=lambda: [])
    DelayedMessageWorkerLoopService(
        heartbeat_service=heartbeat, worker_service=worker,
    ).start_loop(max_cycles=1)
    assert events == ["startup", "poll", ("success", True), "stopping", "shutdown"]
