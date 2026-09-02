from __future__ import annotations

import asyncio
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.integrations.telegram.telethon_transport import (
    TelethonAuthorizationRequiredError,
    TelethonTransientError,
)
from app.models.worker_heartbeat import WorkerHeartbeatStatus
from app.services.telegram_worker_ownership_service import TelegramWorkerOwnershipService
from app.services.worker_launcher_supervision_service import WORKERS
from app.test_worker_launcher_supervision import heartbeat, service


class Heartbeat:
    def __init__(self):
        self.events = []
        self.current = datetime(2026, 8, 25, tzinfo=timezone.utc)

    def now(self): return self.current
    def register_startup(self): self.events.append(("startup", {}))
    def heartbeat(self, **values): self.events.append(("heartbeat", values.get("metadata") or {}))
    def record_poll(self): self.events.append(("poll", {}))
    def record_success(self, **_): self.events.append(("success", {}))
    def record_failure(self, error): self.events.append(("degraded", {"error": str(error)}))
    def record_terminal_failure(self, error, *, metadata=None): self.events.append(("failed", {**(metadata or {}), "error": str(error)}))
    def record_stopping(self): self.events.append(("stopping", {}))
    def record_shutdown(self): self.events.append(("stopped", {}))


class Ownership:
    def __init__(self, *, fail_check=False): self.held = False; self.fail_check = fail_check
    def acquire(self): self.held = True; return True
    def check(self):
        if self.fail_check: raise ConnectionError("database unavailable")
        return self.held
    def release(self): self.held = False


class Transport:
    def __init__(self, outcomes):
        self.outcomes = list(outcomes); self.starts = 0; self.disconnects = 0; self.handlers = []
    def set_inbound_handler(self, handler):
        if handler not in self.handlers: self.handlers.append(handler)
    async def start(self): self.starts += 1
    async def run_until_disconnected(self):
        outcome = self.outcomes.pop(0)
        if callable(outcome): return await outcome()
        if isinstance(outcome, BaseException): raise outcome
    async def disconnect(self): self.disconnects += 1


def runtime(transport, *, ownership=None, heartbeat=None, initial=.01, maximum=.04, stable=60,
            heartbeat_interval_seconds=.001):
    return TelethonRuntime(
        transport=transport, inbound_adapter=SimpleNamespace(execute=lambda _: None),
        global_safety_service=SimpleNamespace(check_global_safety=lambda: {"allowed": False}),
        ownership_service=ownership or Ownership(), heartbeat_service=heartbeat or Heartbeat(),
        reconnect_initial_seconds=initial, reconnect_max_seconds=maximum,
        reconnect_stable_reset_seconds=stable, jitter=lambda delay: delay,
        heartbeat_interval_seconds=heartbeat_interval_seconds,
    )


@pytest.mark.parametrize("failure", [ConnectionResetError(), TimeoutError(), OSError("dns"), TelethonTransientError("rpc")])
def test_transient_disconnect_reconnects_without_duplicate_handler(failure):
    holder = {}
    async def stop(): holder["runtime"].request_shutdown("test")
    transport = Transport([failure, stop])
    value = holder["runtime"] = runtime(transport)
    asyncio.run(value.run())
    assert transport.starts == 2
    assert len(transport.handlers) == 1


def test_clean_unexpected_disconnect_reconnects():
    holder = {}
    async def stop(): holder["runtime"].request_shutdown("test")
    transport = Transport([None, stop])
    value = holder["runtime"] = runtime(transport)
    asyncio.run(value.run())
    assert transport.starts == 2


def test_repeated_disconnect_backoff_and_stable_reset():
    holder = {}; heartbeat = Heartbeat()
    async def stop(): holder["runtime"].request_shutdown("test")
    transport = Transport([ConnectionError(), ConnectionError(), stop])
    value = holder["runtime"] = runtime(transport, heartbeat=heartbeat)
    asyncio.run(value.run())
    attempts = [event[1]["reconnect_attempt_count"] for event in heartbeat.events
                if event[0] == "heartbeat" and event[1].get("lifecycle_state") == "RECONNECTING"]
    assert attempts == [1, 2]
    retries = [event[1]["next_retry_at_epoch"] - heartbeat.current.timestamp()
               for event in heartbeat.events
               if event[0] == "heartbeat" and event[1].get("lifecycle_state") == "RECONNECTING"]
    assert retries == pytest.approx([.01, .02])
    connected = [data for name, data in heartbeat.events
                 if name == "heartbeat" and data.get("lifecycle_state") == "CONNECTED"]
    assert connected[-1]["next_retry_at_epoch"] is None


def test_stable_connection_resets_reconnect_counter():
    holder = {}; heartbeat = Heartbeat()
    async def stop(): holder["runtime"].request_shutdown("test")
    transport = Transport([ConnectionError(), ConnectionError(), stop])
    value = holder["runtime"] = runtime(transport, heartbeat=heartbeat, stable=0)
    asyncio.run(value.run())
    attempts = [event[1]["reconnect_attempt_count"] for event in heartbeat.events
                if event[0] == "heartbeat" and event[1].get("lifecycle_state") == "RECONNECTING"]
    assert attempts == [1, 1]


def test_production_backoff_defaults_are_fast_bounded_and_jittered():
    value = TelethonRuntime(
        transport=Transport([None]), inbound_adapter=SimpleNamespace(execute=lambda _: None),
        heartbeat_service=Heartbeat(),
        global_safety_service=SimpleNamespace(check_global_safety=lambda: {"allowed": False}),
    )
    assert value._reconnect_initial == 1.0
    assert value._reconnect_max == 30.0
    samples = [value._jitter(10.0) for _ in range(20)]
    assert all(8.0 <= sample <= 12.0 for sample in samples)


def test_authorization_loss_is_terminal_and_operator_visible():
    transport = Transport([])
    async def unauthorized(): raise TelethonAuthorizationRequiredError("authorization required")
    transport.start = unauthorized
    heartbeat = Heartbeat()
    with pytest.raises(TelethonAuthorizationRequiredError):
        asyncio.run(runtime(transport, heartbeat=heartbeat).run())
    assert any(name == "failed" and data.get("authorization_required") for name, data in heartbeat.events)


def test_unexpected_non_network_exception_is_fatal():
    transport = Transport([])
    async def broken(): raise ValueError("corrupt runtime state")
    transport.start = broken; heartbeat = Heartbeat()
    with pytest.raises(ValueError):
        asyncio.run(runtime(transport, heartbeat=heartbeat).run())
    assert any(name == "failed" for name, _ in heartbeat.events)


def test_database_loss_blocks_inbound_before_ai_or_send():
    transport = Transport([]); ownership = Ownership(fail_check=True); ownership.held = True
    adapter = SimpleNamespace(calls=0)
    def execute(_): adapter.calls += 1
    adapter.execute = execute
    value = TelethonRuntime(
        transport=transport, inbound_adapter=adapter, ownership_service=ownership,
        heartbeat_service=Heartbeat(),
        global_safety_service=SimpleNamespace(check_global_safety=lambda: {"allowed": True}),
    )
    payload = SimpleNamespace(telegram_chat_id=1, telegram_user_id=1, message_id=1)
    with pytest.raises(ConnectionError): asyncio.run(value._handle_payload_observed(payload))
    assert adapter.calls == 0


def test_startup_readiness_orders_ownership_recovery_before_connection():
    events = []
    class OrderedOwnership(Ownership):
        def acquire(self): events.append("ownership"); return super().acquire()
    class Recovery:
        def recover_startup(self): events.append("ordinary_recovery")
    class OrderedTransport(Transport):
        async def start(self): events.append("transport_start"); await super().start()
    holder = {}
    async def stop(): holder["runtime"].request_shutdown("test")
    transport = OrderedTransport([stop]); heartbeat = Heartbeat()
    value = holder["runtime"] = TelethonRuntime(
        transport=transport, inbound_adapter=SimpleNamespace(execute=lambda _: None),
        ownership_service=OrderedOwnership(), ordinary_reply_service=Recovery(),
        heartbeat_service=heartbeat,
        global_safety_service=SimpleNamespace(check_global_safety=lambda: {"allowed": False}),
        jitter=lambda delay: delay,
    )
    asyncio.run(value.run())
    assert events == ["ownership", "ordinary_recovery", "transport_start"]
    lifecycle = [data.get("lifecycle_state") for name, data in heartbeat.events if name == "heartbeat"]
    assert lifecycle.index("STARTING") < lifecycle.index("CONNECTING") < lifecycle.index("CONNECTED")


def test_reconnect_stress_preserves_one_handler_and_interrupts_backoff():
    holder = {}; heartbeat = Heartbeat()
    async def stop_in_backoff():
        holder["runtime"].request_shutdown("operator_stop")
        raise ConnectionResetError()
    outcomes = [None, TimeoutError(), OSError("dns"), None, stop_in_backoff]
    transport = Transport(outcomes)
    value = holder["runtime"] = runtime(transport, heartbeat=heartbeat, initial=.01, maximum=.04)
    asyncio.run(value.run())
    assert transport.starts == 5
    assert len(transport.handlers) == 1
    assert any(data.get("shutdown_reason") == "operator_stop" for _, data in heartbeat.events)


def test_connected_transport_fails_safe_on_database_loss_then_replacement_recovers():
    class BlockingTransport(Transport):
        def __init__(self): super().__init__([]); self.closed = asyncio.Event()
        async def run_until_disconnected(self): await self.closed.wait()
        async def disconnect(self): self.disconnects += 1; self.closed.set()
    ownership = Ownership(); checks = {"count": 0}
    def fail_after_start():
        checks["count"] += 1
        if checks["count"] >= 1: raise ConnectionError("database unavailable")
        return True
    ownership.check = fail_after_start
    broken = runtime(BlockingTransport(), ownership=ownership, heartbeat_interval_seconds=.001)
    with pytest.raises(ConnectionError): asyncio.run(broken.run())
    holder = {}
    async def stop(): holder["runtime"].request_shutdown("recovered")
    replacement_transport = Transport([stop])
    replacement = holder["runtime"] = runtime(replacement_transport, ownership=Ownership())
    asyncio.run(replacement.run())
    assert replacement_transport.starts == 1


def test_supervisor_restarts_dead_worker_and_blocks_crash_loop(tmp_path):
    definition = WORKERS[0]
    environment = {definition.environment_switch: "true", "TG_API_ID": "1", "TG_API_HASH": "x", "AVA_FANVUE_ACCOUNT_ID": "2"}
    value, processes, heartbeats, clock = service(tmp_path, environment)
    value._record(definition, "started", launcher_enabled=True, pid=9)
    first = value.supervise_telegram_once(definition)
    assert first["lastLauncherAction"] == "started"
    assert first["supervisorRestartCount"] == 1
    processes.running.clear()
    for index in range(value.TELEGRAM_CRASH_LIMIT):
        clock.sleep(20)
        result = value.supervise_telegram_once(definition)
        processes.running.clear()
    assert result["lastLauncherAction"] == "crash_loop_blocked"


def test_supervisor_does_not_restart_authorization_failure(tmp_path):
    definition = WORKERS[0]
    environment = {definition.environment_switch: "true"}
    value, processes, heartbeats, clock = service(tmp_path, environment)
    row = heartbeat(definition, 77, clock.now(), WorkerHeartbeatStatus.FAILED)
    heartbeats.auto_register = False
    heartbeats.rows = [SimpleNamespace(**{**row.__dict__, "metadata": {"authorization_required": True}, "last_error": "authorization required"})]
    value._record(definition, "started", launcher_enabled=True, pid=77)
    result = value.supervise_telegram_once(definition)
    assert result["lastLauncherAction"] == "authorization_required"
    assert result["crashLoopBlocked"] is True
    assert processes.started == []


def test_monitor_pid_is_observable_and_gate_off_prevents_supervision(tmp_path):
    definition = WORKERS[0]
    value, processes, _, _ = service(tmp_path, {})
    value.monitor_telegram(max_cycles=1)
    state = value._load_state()[definition.key]
    assert state["supervisorPid"] is None
    assert processes.started == []

    enabled = {definition.environment_switch: "true", "TG_API_ID": "1", "TG_API_HASH": "x", "AVA_FANVUE_ACCOUNT_ID": "2"}
    value, _, _, _ = service(tmp_path, enabled)
    value.monitor_telegram(max_cycles=1)
    state = value._load_state()[definition.key]
    assert state["supervisorPid"] is None
    assert state["supervisorUpdatedAt"] is not None


def test_existing_monitor_supervises_enabled_commerce_worker(tmp_path):
    definition = next(item for item in WORKERS if item.key == "commerce_reconciliation")
    environment = {definition.environment_switch: "true"}
    value, processes, _, _ = service(tmp_path, environment)
    value.monitor_telegram(max_cycles=1)
    state = value._load_state()[definition.key]
    assert state["lastLauncherAction"] == "started"
    assert state["supervisorRestartCount"] == 1
    assert processes.started == [definition.command]


def _postgres_ownership():
    url = os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL required")
    return TelegramWorkerOwnershipService(
        connection_factory=lambda: connect(url, row_factory=dict_row),
        connection_releaser=lambda connection: connection.close(),
    )


def test_postgresql_advisory_lock_is_singleton_and_recovers_after_release():
    first = _postgres_ownership(); second = _postgres_ownership()
    try:
        assert first.acquire() is True
        assert second.acquire() is False
        first.release()
        assert second.acquire() is True
        assert second.check() is True
    finally:
        first.release(); second.release()


def test_hard_process_death_releases_postgresql_advisory_lock():
    url = os.getenv("TEST_DATABASE_URL")
    if not url: pytest.skip("TEST_DATABASE_URL required")
    child_code = """
import os, time
from psycopg import connect
from psycopg.rows import dict_row
from app.services.telegram_worker_ownership_service import TelegramWorkerOwnershipService
service=TelegramWorkerOwnershipService(connection_factory=lambda:connect(os.environ['TEST_DATABASE_URL'],row_factory=dict_row),connection_releaser=lambda c:c.close())
assert service.acquire()
print('READY', flush=True)
time.sleep(300)
"""
    child = subprocess.Popen(
        [sys.executable, "-c", child_code], cwd=os.getcwd(), env=dict(os.environ),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        creationflags=(subprocess.CREATE_NEW_PROCESS_GROUP if os.name == "nt" else 0),
    )
    replacement = _postgres_ownership()
    try:
        assert child.stdout.readline().strip() == "READY"
        assert replacement.acquire() is False
        child.kill(); child.wait(timeout=10)
        for _ in range(20):
            if replacement.acquire(): break
            __import__("time").sleep(.05)
        assert replacement.check() is True
    finally:
        if child.poll() is None: child.kill(); child.wait(timeout=10)
        replacement.release()
