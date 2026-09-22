from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.integrations.telegram.telethon_runtime import TelethonRuntime
from app.models.telegram_inbound import TelegramInboundPayload


NOW = datetime(2026, 9, 17, 2, 0, tzinfo=timezone.utc)


def payload(user: int, message: int, minute: int) -> TelegramInboundPayload:
    return TelegramInboundPayload(
        telegram_user_id=user, telegram_chat_id=user,
        message_text=f"message {message}", message_id=message,
        received_at=datetime(2026, 9, 17, 1, minute, tzinfo=timezone.utc),
    )


class Transport:
    def __init__(self, rows): self.rows = tuple(rows); self.handler = None
    def set_inbound_handler(self, handler): self.handler = handler
    async def bounded_private_inbound_history(self, **_): return self.rows


class Backlog:
    def __init__(self, fail_after=None):
        self.archive = {}; self.operations = {}; self.fail_after = fail_after; self.calls = 0
    def latest_boundary(self, **_):
        if not self.archive: return {"received_at": datetime(2026, 9, 17, 0, 8, tzinfo=timezone.utc)}
        latest = max(self.archive.values(), key=lambda item: item.received_at)
        return {"received_at": latest.received_at, "telegram_message_id": latest.message_id}
    def capture(self, item, **_):
        self.calls += 1
        if self.fail_after is not None and self.calls > self.fail_after:
            raise RuntimeError("crash midway")
        key = (item.telegram_chat_id, item.message_id); created = key not in self.archive
        self.archive.setdefault(key, item)
        return self.archive[key], created
    def reconcile_chat(self, *, chat_id, response_allowed, **_):
        pending = [item for (chat, _), item in self.archive.items() if chat == chat_id]
        if not response_allowed or not pending:
            return {"outcome": "NO_RESPONSE_REQUIRED", "response_operation_id": None}
        authoritative = max(pending, key=lambda item: (item.received_at, item.message_id))
        self.operations.setdefault(chat_id, authoritative.message_id)
        return {"outcome": "RESPOND", "response_operation_id": f"operation:{chat_id}"}


class Adapter:
    _creator_profile_id = 2; _fanvue_account_id = 2; _relationship_controls = None
    def __init__(self): self.observed = []
    def observe_identity_and_relationship(self, item): self.observed.append(item.message_id)


class Safety:
    behavior_config = {"global_automation_enabled": True}
    def refresh(self): return None
    def check_global_safety(self): return {"allowed": True}


class Heartbeat:
    def now(self): return NOW
    def heartbeat(self, **_): return None


def runtime(rows, backlog):
    target = TelethonRuntime(
        transport=Transport(rows), inbound_adapter=Adapter(),
        private_inbound_backlog_service=backlog,
        global_safety_service=Safety(), heartbeat_service=Heartbeat(),
    )
    return target


def test_three_message_fixture_is_captured_coalesced_and_restart_idempotent():
    rows = (payload(7595047025, 6410, 10), payload(7595047025, 6411, 12),
            payload(5729124166, 6412, 20))
    backlog = Backlog(); target = runtime(rows, backlog)
    first = asyncio.run(target._recover_startup_history())
    second = asyncio.run(target._recover_startup_history())
    assert first == {**first, "captured": 3, "chats": 2, "operations": 2}
    assert second["captured"] == 0
    assert len(backlog.archive) == 3
    assert backlog.archive[(5729124166, 6412)].received_at == rows[2].received_at
    assert backlog.operations == {7595047025: 6411, 5729124166: 6412}


def test_history_and_live_overlap_capture_once_and_post_query_live_is_once():
    shared = payload(5729124166, 6412, 20); later = payload(5729124166, 6413, 21)
    backlog = Backlog(); target = runtime((shared,), backlog)
    target.handle_payload = lambda _item: asyncio.sleep(0)
    async def exercise():
        await target._handle_payload_observed(shared)
        await target._recover_startup_history()
        await target._handle_payload_observed(later)
    asyncio.run(exercise())
    assert sorted(key[1] for key in backlog.archive) == [6412, 6413]


def test_mid_catchup_crash_is_safe_to_retry():
    rows = (payload(7595047025, 6410, 10), payload(7595047025, 6411, 12),
            payload(5729124166, 6412, 20))
    backlog = Backlog(fail_after=1); target = runtime(rows, backlog)
    with pytest.raises(RuntimeError, match="crash midway"):
        asyncio.run(target._recover_startup_history())
    backlog.fail_after = None; backlog.calls = 0
    result = asyncio.run(target._recover_startup_history())
    assert result["captured"] == 2
    assert len(backlog.archive) == 3
    assert backlog.operations == {7595047025: 6411, 5729124166: 6412}
