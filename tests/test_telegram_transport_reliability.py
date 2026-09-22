"""Neutral fixtures only. No Telegram calls or application database connections."""
import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.telegram_transport_contract import (
    TelegramRequirements, TelegramReachability, TelegramPreflightError,
)
from app.integrations.telegram.bot_api_sender import (
    TelegramBotApiSender, TelegramOutboundSendAmbiguousError,
    TelegramOutboundSendError, TelegramBusinessProviderVerificationError,
)
from app.integrations.telegram.telethon_transport import TelethonUserTransport, TelethonTransportError
from app.services.telegram_transport_boundary import (
    RoutedTelegramSender, ManualInvocationRecorder, acknowledgement_scope,
    TelegramAcknowledgementPersistenceError, TelegramInvocationUnknown,
)
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.telegram_transport_reconciliation import assess_telegram_history

NOW = datetime.now(timezone.utc)


def peer(kind="BOT_API", *, age=0):
    return TelegramReachability(kind, "test-sender", 123,
        {"BOT_API": "BOT_INBOUND", "TELEGRAM_BUSINESS": "BUSINESS_INBOUND",
         "TELETHON": "AUTHORIZED_SESSION_ENTITY"}[kind], NOW-timedelta(hours=age),
        "test-connection" if kind == "TELEGRAM_BUSINESS" else None, sender_id=42)


class Response:
    status_code = 200
    def __init__(self, payload): self.payload = payload
    def json(self):
        if isinstance(self.payload, Exception): raise self.payload
        return self.payload


class Http:
    def __init__(self, response): self.response = response; self.calls = []
    def post(self, *args, **kwargs):
        self.calls.append(kwargs)
        if isinstance(self.response, Exception): raise self.response
        return Response(self.response)


def bot(payload, *, evidence=None):
    http = Http(payload)
    sender = TelegramBotApiSender(bot_token="neutral-test-token", session=http,
        peer_evidence=lambda _: evidence, sender_scope="test-sender")
    return sender, http


@pytest.mark.parametrize("kind", ["BOT_API", "TELEGRAM_BUSINESS", "TELETHON"])
@pytest.mark.parametrize("shape", [{}, {"photo": True}, {"photo": True, "caption": True},
                                  {"suppress_preview": True}])
def test_required_capabilities_with_matching_peer(kind, shape):
    peer(kind).validate(TelegramRequirements(**shape))


@pytest.mark.parametrize("kind", ["BOT_API", "TELEGRAM_BUSINESS"])
@pytest.mark.parametrize("photo", [False, True])
def test_supported_url_action(kind, photo):
    peer(kind).validate(TelegramRequirements(photo=photo, caption=photo, url_action=True))


def test_telethon_action_fails_before_send():
    with pytest.raises(TelegramPreflightError): peer("TELETHON").validate(TelegramRequirements(url_action=True))


@pytest.mark.parametrize("age", [24, 25, 240])
def test_business_stale(age):
    with pytest.raises(TelegramPreflightError): peer("TELEGRAM_BUSINESS", age=age).validate(TelegramRequirements())


@pytest.mark.parametrize("evidence", [None, peer("TELETHON"), peer("TELEGRAM_BUSINESS")])
def test_bot_unknown_or_other_identity_is_not_reachable(evidence):
    sender, http = bot({}, evidence=evidence)
    with pytest.raises(TelegramPreflightError): sender.prepare_delivery(chat_id=123, requirements=TelegramRequirements())
    assert not http.calls


def test_sender_scope_requirement():
    with pytest.raises(TelegramPreflightError): peer().validate(TelegramRequirements(sender_scope="other"))


@pytest.mark.parametrize("payload", [ValueError("invalid json"), None, [], {}, {"ok": 1},
    {"ok": False}, {"ok": True}, {"ok": True, "result": {}},
    {"ok": True, "result": {"message_id": True}}])
@pytest.mark.parametrize("media", [False, True])
def test_malformed_response_never_definitive(payload, media, tmp_path):
    sender, http = bot(payload)
    file = tmp_path/"test.bin"; file.write_bytes(b"neutral fixture")
    with pytest.raises((TelegramOutboundSendAmbiguousError, TelegramBusinessProviderVerificationError)) as caught:
        if media: sender.send_asset(chat_id=123, asset_path=str(file), message_text="Creator-OS media transport test")
        else: sender.send_text(chat_id=123, message_text="Creator-OS transport test")
    assert caught.value.certainty == "UNKNOWN"
    assert len(http.calls) == 1


@pytest.mark.parametrize("error", [TimeoutError(), ConnectionError(), OSError()])
def test_invoked_network_error_unknown(error):
    sender, http = bot(error)
    with pytest.raises(TelegramOutboundSendAmbiguousError): sender.send_text(chat_id=123, message_text="test")
    assert len(http.calls) == 1


def test_explicit_rejection():
    sender, _ = bot({"ok": False, "error_code": 400, "description": "Bad Request: PEER_ID_INVALID"})
    with pytest.raises(TelegramOutboundSendError) as caught: sender.send_text(chat_id=123, message_text="test")
    assert caught.value.certainty == "REJECTED"


def test_local_validation_has_no_invocation():
    sender, http = bot({})
    with pytest.raises(ValueError): sender.send_text(chat_id=-1, message_text="test")
    assert not http.calls


def business_response(action=False):
    result = {"message_id": 99, "business_connection_id": "test-connection", "chat": {"id": 123},
              "caption": "Creator-OS media transport test", "photo": [{"file_id": "neutral"}],
              "from": {"id": 42}, "sender_business_bot": {"id": 43}}
    if action: result["reply_markup"] = {"inline_keyboard": [[{"text": "Open test page", "url": "https://example.invalid/test"}]]}
    return {"ok": True, "result": result}


@pytest.mark.parametrize("action", [False, True])
@pytest.mark.parametrize("mismatch", [None, "caption", "photo", "reply_markup"])
def test_media_ack_precedes_verification(action, mismatch, tmp_path):
    payload = business_response(action)
    if mismatch: payload["result"][mismatch] = [] if mismatch != "caption" else "incorrect"
    sender, http = bot(payload)
    file = tmp_path/"test.bin"; file.write_bytes(b"neutral")
    evidence = []
    values = dict(chat_id=123, asset_path=str(file), message_text="Creator-OS media transport test",
                  business_connection_id="test-connection")
    if action: values.update(button_label="Open test page", button_url="https://example.invalid/test")
    with acknowledgement_scope(lambda value: evidence.append(value) or value):
        if mismatch in {"caption", "photo"} or (action and mismatch == "reply_markup"):
            with pytest.raises(TelegramBusinessProviderVerificationError) as caught: sender.send_asset(**values)
            assert caught.value.certainty == "ACCEPTED"
            assert caught.value.provider_evidence["telegram_message_id"] == 99
        else:
            assert sender.send_asset(**values).id == 99
    assert evidence[0]["telegram_message_id"] == 99
    assert len(http.calls) == 1


def test_ack_write_failure_carries_acceptance():
    sender, _ = bot({"ok": True, "result": {"message_id": 99}})
    def fail(_): raise OSError("isolated database fault")
    with acknowledgement_scope(fail), pytest.raises(TelegramAcknowledgementPersistenceError) as caught:
        sender.send_text(chat_id=123, message_text="test")
    assert caught.value.provider_evidence["telegram_message_id"] == 99
    assert caught.value.certainty == "ACCEPTED"


def test_route_persisted_before_call_and_acceptance_after():
    sender, http = bot({"ok": True, "result": {"message_id": 99}}, evidence=peer())
    records = []
    def record(value): records.append((len(http.calls), value)); return value
    routed = RoutedTelegramSender(sender, context={"operation_id": "test-operation", "record_transport_evidence": record}, metadata={})
    assert routed.send_text(chat_id=123, message_text="test", disable_link_preview=True) == 99
    assert records[0][0] == 0
    assert records[0][1]["transport_route"]["required_capabilities"]["suppress_preview"]
    assert records[1][0] == 1
    assert http.calls[0]["json"]["link_preview_options"] == {"is_disabled": True}
    with pytest.raises(TelegramInvocationUnknown): routed.send_text(chat_id=123, message_text="test")
    assert len(http.calls) == 1


@pytest.mark.parametrize("media", [False, True])
@pytest.mark.parametrize("returned_action", [False, True])
def test_plain_bot_required_action_roundtrip(media, returned_action, tmp_path):
    result = {"message_id": 99, "text": "test", "photo": [{"file_id": "neutral"}], "caption": "test"}
    action = {"text": "Open test page", "url": "https://example.invalid/test"}
    if returned_action: result["reply_markup"] = {"inline_keyboard": [[action]]}
    sender, http = bot({"ok": True, "result": result})
    values = {"chat_id": 123, "message_text": "test", "button_label": action["text"], "button_url": action["url"]}
    if media:
        path = tmp_path/"neutral.bin"; path.write_bytes(b"neutral")
        values["asset_path"] = str(path)
    method = sender.send_asset if media else sender.send_text
    if returned_action: assert method(**values).provider_action_verified
    else:
        with pytest.raises(TelegramBusinessProviderVerificationError) as caught: method(**values)
        assert caught.value.provider_evidence["telegram_message_id"] == 99
    assert len(http.calls) == 1


def test_bot_inbound_learns_only_its_own_identity():
    first = TelegramBotApiSender(bot_token="first")
    second = TelegramBotApiSender(bot_token="second")
    first.observe_inbound(123)
    assert first.prepare_delivery(chat_id=123, requirements=TelegramRequirements()).sender_scope == first.sender_scope
    with pytest.raises(TelegramPreflightError): second.prepare_delivery(chat_id=123, requirements=TelegramRequirements())


def test_missing_file_fails_before_claim(tmp_path):
    sender, http = bot({}, evidence=peer())
    records = []
    routed = RoutedTelegramSender(sender, context={"record_transport_evidence": lambda e: records.append(e) or e}, metadata={})
    with pytest.raises(TelegramPreflightError):
        routed.send_asset(chat_id=123, asset_path=str(tmp_path/"absent.png"), message_text="test")
    assert not records and not http.calls


def test_failed_route_write_prevents_invocation():
    sender, http = bot({}, evidence=peer())
    routed = RoutedTelegramSender(sender, context={"record_transport_evidence": lambda _: None}, metadata={})
    with pytest.raises(TelegramInvocationUnknown): routed.send_text(chat_id=123, message_text="test")
    assert not http.calls


def test_wrapped_telethon_failure_quarantined():
    recorded = []
    service = object.__new__(OrdinaryChatReplyService)
    service.worker_id = "test"
    service.repository = SimpleNamespace(fail_send=lambda *a, **k: recorded.append(k))
    service.failed(SimpleNamespace(operation_id=uuid4()), TelethonTransportError("network fault"))
    assert recorded[0]["ambiguous"] is True


@pytest.mark.parametrize("resolvable", [True, False])
def test_telethon_cache_preflight(resolvable):
    class Client:
        _self_id = 42
        def is_connected(self): return True
        async def is_user_authorized(self): return True
        @property
        def session(self): return self
        def get_input_entity(self, _):
            if not resolvable: raise ValueError("unknown")
            return object()
    transport = TelethonUserTransport(client=Client())
    operation = transport.prepare_delivery(chat_id=123, requirements=TelegramRequirements())
    if resolvable: assert asyncio.run(operation).transport == "TELETHON"
    else:
        with pytest.raises(TelegramPreflightError): asyncio.run(operation)


@pytest.mark.parametrize("known_id", [True, False])
@pytest.mark.parametrize("authenticated", [True, False])
def test_history_missing_id_and_unmapped_peer(known_id, authenticated):
    route = {"provider_attempt_id": "attempt", "payload_sha256": "digest", "sender_id": 42,
             "sender_scope": "test-sender", "peer_id": 123, "invocation_started_at": NOW.isoformat(),
             "required_capabilities": {}}
    evidence = {"transport_route": route}
    if known_id: evidence["telegram_message_id"] = 99
    operation = {"provider_delivery_evidence": evidence, "uncertain_at": NOW.isoformat(), "text": "test"}
    history = {"authenticated": authenticated, "canonical_session": True, "query_succeeded": True,
               "complete": True, "sender_id": 42, "sender_scope": "test-sender", "peer_id": 123,
               "query_start": NOW.isoformat(), "query_end": NOW.isoformat(),
               "unique_attempt_proven": True, "provider_attempt_id": "attempt", "payload_sha256": "digest",
               "messages": [{"message_id": 99, "sender_id": 42, "peer_id": 123, "outbound": True,
                             "text": "test", "sent_at": NOW.isoformat()}]}
    result = assess_telegram_history(operation=operation, history=history)
    assert result["outcome"] == ("DELIVERED" if authenticated else "UNKNOWN")
    assert result["retry_authorized"] is False
