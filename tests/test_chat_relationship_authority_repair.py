from types import SimpleNamespace
from datetime import datetime, timezone
import asyncio

import pytest

from app.models.telegram_inbound import TelegramInboundPayload
from app.services.ava_runtime_scope_service import AvaRuntimeScopeService
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.integrations.telegram.telethon_runtime import TelethonRuntime


def test_ava_scope_uses_configured_account_and_active_profile(monkeypatch):
    monkeypatch.setattr(
        "app.services.ava_runtime_scope_service.get_active_creator_profile",
        lambda account: {"id": 22, "fanvue_account_id": account})
    assert AvaRuntimeScopeService.resolve(
        requested_account_id=8, environment={"AVA_FANVUE_ACCOUNT_ID": "8"}) == (22, 8)
    with pytest.raises(ValueError, match="not the configured"):
        AvaRuntimeScopeService.resolve(
            requested_account_id=7, environment={"AVA_FANVUE_ACCOUNT_ID": "8"})


class IdentityAuthority:
    def __init__(self): self.observations = []
    def observe(self, **values): self.observations.append(values)
    def resolve_telegram_identity(self, _user_id): return None


class ProspectAuthority:
    def __init__(self): self.by_user = {}; self.observe_calls = 0
    def observe(self, **values):
        self.observe_calls += 1
        self.by_user.setdefault(values["telegram_user_id"], SimpleNamespace(
            prospect_id=f'p-{values["telegram_user_id"]}', relationship_state={}))
        return self.by_user[values["telegram_user_id"]]


class ArchiveAuthority:
    def __init__(self): self.correlations = []
    def correlate(self, _payload, **values): self.correlations.append(values)


@pytest.mark.parametrize("username,display_name", [
    (None, None), (None, "🌊✨"), ("new_person", "New Person")])
def test_new_private_sender_bootstrap_is_provider_free_and_idempotent(
        username, display_name):
    identities, prospects, archive = IdentityAuthority(), ProspectAuthority(), ArchiveAuthority()
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=8),
        conversation_gateway=SimpleNamespace(), creator_profile_id=22,
        fanvue_account_id=8, telegram_identity_service=identities,
        unmapped_telegram_prospect_service=prospects,
        private_inbound_backlog_service=archive)
    payload = TelegramInboundPayload(
        telegram_user_id=987654321, telegram_chat_id=987654321,
        message_text="hello", message_id=41, telegram_username=username,
        telegram_display_name=display_name)

    first = adapter.observe_identity_and_relationship(payload)
    second = adapter.observe_identity_and_relationship(payload)

    assert first[2].prospect_id == second[2].prospect_id == "p-987654321"
    assert identities.observations[-1]["display_name"] == display_name
    assert archive.correlations[-1]["prospect_id"] == "p-987654321"
    assert not hasattr(adapter._conversation_gateway, "execute_calls")


class DurableArchive:
    def __init__(self): self.rows = {}
    def capture(self, payload, **_):
        self.rows.setdefault(payload.message_id, {
            "telegram_user_id": payload.telegram_user_id,
            "telegram_chat_id": payload.telegram_chat_id,
            "message_text": payload.message_text})
    def correlate(self, payload, **values):
        self.rows[payload.message_id].update(
            {key: value for key, value in values.items() if value is not None})


class DeferredReplies:
    def __init__(self):
        self.operation = SimpleNamespace(operation_id="ordinary-41",
            state=SimpleNamespace(value="PENDING_GENERATION"))
        self.deferred = []
    def begin(self, _payload): return self.operation, not self.deferred
    def relationship_scheduling_profile(self, **_):
        return {"market_tier": "UNCLASSIFIED", "high_value_prospect": False}
    def defer_for_availability(self, operation, decision):
        self.deferred.append((operation.operation_id, decision.category))


class RuntimeSafety:
    behavior_config = {"global_automation_enabled": True}
    def refresh(self): return None
    def check_global_safety(self): return {"allowed": True}


class RuntimeTransport:
    def set_inbound_handler(self, handler): self.handler = handler


class RuntimeHeartbeat:
    def now(self): return datetime.now(timezone.utc)
    def heartbeat(self, **_): return None


@pytest.mark.parametrize("category", [
    "AVAILABLE", "BUSY", "AWAY", "SLEEPING", "INTERMITTENT"])
def test_new_sender_is_durable_and_visible_before_every_availability_return(category):
    identities, prospects, archive = IdentityAuthority(), ProspectAuthority(), DurableArchive()
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=8),
        conversation_gateway=SimpleNamespace(), creator_profile_id=22,
        fanvue_account_id=8, telegram_identity_service=identities,
        unmapped_telegram_prospect_service=prospects,
        private_inbound_backlog_service=archive)
    adapter.execute = lambda *_args, **_kwargs: (_ for _ in ()).throw(
        AssertionError("generation must remain behind availability"))
    replies = DeferredReplies()
    availability = SimpleNamespace(calculate=lambda **_: SimpleNamespace(
        category=category, available_at=datetime.now(timezone.utc), session_id="session"))
    runtime = TelethonRuntime(transport=RuntimeTransport(), inbound_adapter=adapter,
        heartbeat_service=RuntimeHeartbeat(), private_inbound_backlog_service=archive,
        ordinary_reply_service=replies, availability_service=availability,
        global_safety_service=RuntimeSafety())
    payload = TelegramInboundPayload(telegram_user_id=987654321,
        telegram_chat_id=987654321, message_text="hello", message_id=41,
        received_at=datetime.now(timezone.utc))

    assert asyncio.run(runtime._handle_payload_observed(payload)) is None
    row = archive.rows[41]
    assert row["prospect_id"] == "p-987654321"
    assert row["response_operation_id"] == "ordinary-41"
    assert 987654321 in prospects.by_user
    assert identities.observations
    assert replies.deferred == [("ordinary-41", category)]


def test_restart_style_reprocessing_keeps_one_relationship_and_operation_link():
    identities, prospects, archive = IdentityAuthority(), ProspectAuthority(), DurableArchive()
    payload = TelegramInboundPayload(telegram_user_id=456, telegram_chat_id=456,
        message_text="hello", message_id=9, received_at=datetime.now(timezone.utc))
    archive.capture(payload)
    for _ in range(2):
        adapter = TelegramInboundAdapter(
            identity_adapter=TelegramIdentityAdapter(engine_account_id=8),
            conversation_gateway=SimpleNamespace(), creator_profile_id=22,
            fanvue_account_id=8, telegram_identity_service=identities,
            unmapped_telegram_prospect_service=prospects,
            private_inbound_backlog_service=archive)
        adapter.observe_identity_and_relationship(payload)
        archive.correlate(payload, response_operation_id="same-operation")
    assert list(prospects.by_user) == [456]
    assert archive.rows[9]["prospect_id"] == "p-456"
    assert archive.rows[9]["response_operation_id"] == "same-operation"
