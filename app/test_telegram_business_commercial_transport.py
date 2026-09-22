from app.testing.telegram_transport_fixtures import ReachableTestSender
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.integrations.telegram.bot_api_sender import (
    TelegramBotApiSender,
    TelegramBusinessPeerUsageMissingError,
)
from app.models.telegram_business_connection import TelegramBusinessConnection
from app.models.telegram_commerce import TelegramDeliveryPayload
from app.services.telegram_business_commercial_transport import (
    TelegramBusinessCommercialTransport,
    TelegramBusinessConnectionDisabledError,
    TelegramBusinessReplyNotAllowedError,
    TelegramBusinessTransportError,
)
from app.services.telegram_business_connection_service import (
    TelegramBusinessConnectionService,
)
from app.services.telegram_business_connection_worker import (
    TelegramBusinessConnectionWorker,
)
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor


NOW = datetime.now(timezone.utc)


def connection(*, connection_id="bc-1", enabled=True, can_reply=True):
    return TelegramBusinessConnection(
        business_connection_id=connection_id,
        business_owner_telegram_user_id=6432023689,
        bot_telegram_user_id=8214690576,
        is_enabled=enabled, can_reply=can_reply,
        rights={"can_reply": can_reply}, provider_updated_at=NOW,
        observed_at=NOW, superseded_at=None, created_at=NOW, updated_at=NOW,
    )


class Connections:
    def __init__(self, item): self.item = item
    def current(self, **_kwargs): return self.item
    def active(self, **_kwargs):
        return self.item if self.item and self.item.usable else None


class Sender(ReachableTestSender):
    def __init__(self): self.calls = []
    def send_text(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=700, final_text=kwargs["message_text"],
            actionable_destination_attached=True,
            provider_action_verified=True, provider_markup_included=True,
            provider_markup_verified=True,
            attachment_mode="TELEGRAM_BUSINESS_INLINE_BUTTON",
            business_connection_id=kwargs["business_connection_id"],
            sender_business_bot={"id": 8214690576},
            sender={"id": 6432023689},
        )
    def send_asset(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id=702, final_text=kwargs["message_text"],
            actionable_destination_attached=True,
            provider_action_verified=True, provider_markup_included=True,
            provider_markup_verified=True, provider_media_included=True,
            attachment_mode="TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON",
            business_connection_id=kwargs["business_connection_id"],
            sender_business_bot={"id": 8214690576},
            sender={"id": 6432023689},
        )


def transport(item=None, *, enabled=True):
    sender = Sender()
    return TelegramBusinessCommercialTransport(
        enabled=enabled, owner_user_id=6432023689, bot_id=8214690576,
        connection_service=Connections(item), sender=sender,
        peer_observations=SimpleNamespace(evidence=lambda **_: {"is_enabled": True, "can_reply": True, "last_business_inbound_at": datetime.now(timezone.utc)}),
    ), sender


def test_business_transport_default_is_off(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BUSINESS_COMMERCIAL_TRANSPORT_ENABLED", raising=False)
    candidate = TelegramBusinessCommercialTransport(
        owner_user_id=6432023689, bot_id=8214690576,
    )
    assert candidate.enabled is False


@pytest.mark.parametrize("item,error", [
    (None, TelegramBusinessTransportError),
    (connection(enabled=False), TelegramBusinessConnectionDisabledError),
    (connection(can_reply=False), TelegramBusinessReplyNotAllowedError),
])
def test_connection_failures_are_closed(item, error):
    candidate, sender = transport(item)
    with pytest.raises(error):
        candidate.send_text(
            chat_id=7857064998, message_text="offer",
            button_label="🔓 Unlock", button_url="https://creator.example/unlock/x",
        )
    assert sender.calls == []


def test_business_transport_preserves_unicode_and_authoritative_values():
    candidate, sender = transport(connection())
    receipt = candidate.send_text(
        chat_id=7857064998, message_text="Natural Ava offer",
        button_label="🔓 Unlock", button_url="https://creator.example/unlock/opaque",
    )
    assert receipt.id == 700
    assert sender.calls == [{
        "business_connection_id": "bc-1", "chat_id": 7857064998,
        "message_text": "Natural Ava offer", "button_label": "🔓 Unlock",
        "button_url": "https://creator.example/unlock/opaque",
        "disable_link_preview": True,
        "expected_business_owner_user_id": 6432023689,
        "expected_business_bot_id": 8214690576,
    }]
    assert "https://" not in sender.calls[0]["message_text"]


def test_business_transport_preserves_media_caption_and_inline_button():
    candidate, sender = transport(connection())
    receipt = candidate.send_asset(
        chat_id=7857064998, asset_path="safe-teaser.png",
        message_text="Natural Ava offer", button_label="🔓 Unlock",
        button_url="https://creator.example/unlock/opaque",
    )
    assert receipt.attachment_mode == "TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON"
    assert sender.calls[0]["asset_path"] == "safe-teaser.png"
    assert sender.calls[0]["message_text"] == "Natural Ava offer"
    assert sender.calls[0]["button_url"] == "https://creator.example/unlock/opaque"

def test_business_transport_rejects_a_different_prepared_connection():
    candidate,sender=transport(connection(connection_id="bc-current"))
    with pytest.raises(TelegramBusinessTransportError,match="prepared"):
        candidate.send_text(chat_id=7857064998,message_text="offer",
            button_label="ðŸ”“ Unlock",button_url="https://creator.example/unlock/opaque",
            expected_business_connection_id="bc-prepared")
    assert sender.calls == []


class Response:
    def __init__(self, payload, status=200): self.payload=payload; self.status_code=status
    def json(self): return self.payload
    def raise_for_status(self): return None


class Http:
    def __init__(self, response): self.response=response; self.calls=[]
    def post(self, url, **kwargs): self.calls.append((url,kwargs)); return self.response


def provider_result(label="🔓 Unlock"):
    return {"ok": True, "result": {
        "message_id": 701, "business_connection_id": "bc-1",
        "chat": {"id": 7857064998}, "text": "Natural Ava offer",
        "from": {"id": 6432023689, "is_bot": False},
        "sender_business_bot": {"id": 8214690576, "is_bot": True},
        "reply_markup": {"inline_keyboard": [[{
            "text": label, "url": "https://creator.example/unlock/opaque",
        }]]},
    }}


def test_bot_api_returns_and_verifies_business_provider_receipt():
    http = Http(Response(provider_result()))
    sender = TelegramBotApiSender(bot_token="token", session=http)
    receipt = sender.send_text(
        business_connection_id="bc-1", chat_id=7857064998,
        message_text="Natural Ava offer", button_label="🔓 Unlock",
        button_url="https://creator.example/unlock/opaque",
        expected_business_owner_user_id=6432023689,
        expected_business_bot_id=8214690576,
    )
    assert receipt.id == 701
    assert receipt.provider_markup_verified is True
    assert http.calls[0][1]["json"]["reply_markup"]["inline_keyboard"][0][0]["text"] == "🔓 Unlock"


def test_bot_api_verifies_plain_business_text_without_reply_markup():
    payload=provider_result()
    payload["result"].pop("reply_markup")
    http=Http(Response(payload))
    receipt=TelegramBotApiSender(bot_token="token",session=http).send_text(
        business_connection_id="bc-1",chat_id=7857064998,
        message_text="Natural Ava offer",expected_business_owner_user_id=6432023689,
        expected_business_bot_id=8214690576)
    assert "reply_markup" not in http.calls[0][1]["json"]
    assert receipt.attachment_mode == "TELEGRAM_BUSINESS_TEXT"
    assert receipt.actionable_destination_attached is False


def test_business_bot_api_disables_preview_and_preserves_unlock_button():
    provider_payload = provider_result()
    label = provider_payload["result"]["reply_markup"]["inline_keyboard"][0][0]["text"]
    http = Http(Response(provider_payload))
    receipt = TelegramBotApiSender(bot_token="token", session=http).send_text(
        business_connection_id="bc-1", chat_id=7857064998,
        message_text="Natural Ava offer", button_label=label,
        button_url="https://creator.example/unlock/opaque",
        disable_link_preview=True,
        expected_business_owner_user_id=6432023689,
        expected_business_bot_id=8214690576,
    )
    request = http.calls[0][1]["json"]
    assert request["link_preview_options"] == {"is_disabled": True}
    assert request["reply_markup"]["inline_keyboard"][0][0]["url"] == (
        "https://creator.example/unlock/opaque"
    )
    assert receipt.provider_action_verified is True


def test_bot_api_send_photo_verifies_media_caption_and_inline_keyboard(tmp_path):
    path = tmp_path / "safe-teaser.bin"
    path.write_bytes(b"safe teaser")
    payload = provider_result()
    payload["result"].pop("text")
    payload["result"].update({
        "caption": "Natural Ava offer",
        "photo": [{"file_id": "provider-photo"}],
    })
    http = Http(Response(payload))
    normalizer = SimpleNamespace(is_supported_image=lambda _path: False)
    receipt = TelegramBotApiSender(
        bot_token="token", session=http, image_normalizer=normalizer,
    ).send_asset(
        business_connection_id="bc-1", chat_id=7857064998,
        asset_path=str(path), message_text="Natural Ava offer",
        button_label="🔓 Unlock",
        button_url="https://creator.example/unlock/opaque",
        expected_business_owner_user_id=6432023689,
        expected_business_bot_id=8214690576,
    )
    request = http.calls[0][1]
    assert request["data"]["caption"] == "Natural Ava offer"
    assert "https://" not in request["data"]["caption"]
    assert "https://creator.example/unlock/opaque" in request["data"]["reply_markup"]
    assert receipt.provider_media_included is True
    assert receipt.provider_markup_verified is True
    assert receipt.attachment_mode == "TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON"


def test_bot_api_preserves_sanitized_provider_rejection_diagnostics():
    http=Http(Response({"ok":False,"error_code":400,
                        "description":"Bad Request: chat not found"},400))
    sender=TelegramBotApiSender(bot_token="secret-token",session=http)
    with pytest.raises(Exception) as caught:
        sender.send_text(chat_id=7857064998,message_text="hello")
    assert "HTTP 400" in str(caught.value)
    assert "error_code 400" in str(caught.value)
    assert "chat not found" in str(caught.value)
    assert "secret-token" not in str(caught.value)


def test_peer_usage_missing_is_explicit_and_never_retried():
    http = Http(Response({"ok": False, "error_code": 400, "description": "Bad Request: BUSINESS_PEER_USAGE_MISSING"}, 400))
    sender = TelegramBotApiSender(bot_token="token", session=http)
    with pytest.raises(TelegramBusinessPeerUsageMissingError):
        sender.send_text(chat_id=7857064998, message_text="offer")
    assert len(http.calls) == 1


class Allow:
    def check_global_safety(self): return {"allowed": True}


class OrdinarySender(ReachableTestSender):
    def __init__(self): self.calls=[]
    async def send_text(self, **kwargs): self.calls.append(kwargs); return 99


def test_executor_uses_business_only_for_unlock_and_telethon_for_ordinary(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/"safe-teaser.png").write_bytes(b"neutral image fixture")
    business, business_sender = transport(connection())
    ordinary = OrdinarySender()
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    ordinary_result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(message_text="hello", delivery_method="text"),
        context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": ordinary},
    ))
    commercial_result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(
            message_text="Natural Ava offer", asset_path="safe-teaser.png",
            delivery_method="private_ppv_media",
            metadata={"private_chat_unlock_button": {
                "label": "🔓 Unlock", "url": "https://creator.example/unlock/opaque",
            }},
        ), context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": ordinary},
    ))
    assert ordinary_result.metadata["telegram_message_id"] == 99
    assert len(ordinary.calls) == 1
    assert len(business_sender.calls) == 1
    assert commercial_result.metadata["attachment_mode"] == "TELEGRAM_BUSINESS_MEDIA_INLINE_BUTTON"


def test_executor_routes_ppv_teaser_caption_and_button_as_one_business_media_send(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path/"safe-teaser.png").write_bytes(b"neutral image fixture")
    business, sender = transport(connection())
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(
            message_text="Natural Ava offer", asset_path="safe-teaser.png",
            delivery_method="private_ppv_media",
            metadata={"private_chat_unlock_button": {
                "label": "🔓 Unlock",
                "url": "https://creator.example/unlock/opaque",
            }},
        ), context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": OrdinarySender()},
    ))
    assert len(sender.calls) == 1
    assert sender.calls[0]["asset_path"] == "safe-teaser.png"
    assert sender.calls[0]["button_url"] not in sender.calls[0]["message_text"]
    assert result.metadata["provider_media_included"] is True
    assert result.metadata["provider_markup_verified"] is True


def test_executor_rejects_visible_ppv_url_before_provider_send():
    business, sender = transport(connection())
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    with pytest.raises(Exception, match="commerce URL"):
        asyncio.run(executor.execute_async(
            TelegramDeliveryPayload(
                message_text="Unlock: https://creator.example/unlock/opaque",
                asset_path="safe-teaser.png", delivery_method="private_ppv_media",
                metadata={"private_chat_unlock_button": {
                    "label": "🔓 Unlock",
                    "url": "https://creator.example/unlock/opaque",
                }},
            ), context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": OrdinarySender(),
                        "raise_on_failure": True},
        ))
    assert sender.calls == []


def test_executor_rejects_automated_text_only_ppv_before_provider_send():
    business, sender = transport(connection())
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(
            message_text="Natural Ava offer", delivery_method="text",
            metadata={"private_chat_unlock_button": {
                "label": "🔓 Unlock",
                "url": "https://creator.example/unlock/opaque",
            }},
        ), context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": OrdinarySender()},
    ))
    assert result.executed is False
    assert result.metadata["failure_code"] == "PRIVATE_PPV_MEDIA_REQUIRED"
    assert sender.calls == []


def test_executor_rejects_local_destination_before_business_send():
    business, sender = transport(connection())
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    with pytest.raises(ValueError, match="CUSTOMER_FACING_DESTINATION_NOT_PUBLIC"):
        asyncio.run(executor.execute_async(
            TelegramDeliveryPayload(
                message_text="offer", asset_path="safe-teaser.png",
                delivery_method="private_ppv_media",
                metadata={"private_chat_unlock_button": {
                    "label": "🔓 Unlock", "url": "http://127.0.0.1:8001/unlock/x",
                }},
            ), context={"record_transport_evidence": lambda evidence: evidence, "chat_id": 7857064998, "transport": OrdinarySender(),
                        "raise_on_failure": True},
        ))
    assert sender.calls == []


class Lifecycle:
    def __init__(self): self.events=[]
    def capture(self, event): self.events.append(event); return event


class GetSession:
    def __init__(self, updates): self.updates=updates; self.calls=[]
    def get(self, url, **kwargs):
        self.calls.append((url,kwargs)); return Response({"ok":True,"result":{"url":""} if url.endswith("getWebhookInfo") else self.updates})


def test_lifecycle_worker_observes_business_messages_without_conversation_routing():
    lifecycle=Lifecycle()
    peer=Lifecycle()
    session=GetSession([
        {"update_id":1,"business_message":{
            "business_connection_id":"bc-2","message_id":90,"date":1700000001,
            "from":{"id":7857064998},
            "chat":{"id":7857064998,"type":"private"},"text":"do not route"}},
        {"update_id":2,"business_connection":{
            "id":"bc-2","user":{"id":6432023689,"first_name":"Ava"},
            "user_chat_id":6432023689,"date":1700000000,"is_enabled":True,
            "rights":{"can_reply":True},
        }},
    ])
    worker=TelegramBusinessConnectionWorker(
        bot_token="token",lifecycle_service=lifecycle,
        peer_observation_service=peer,session=session,timeout_seconds=0,
    )
    assert len(worker.poll_once()) == 2
    assert len(lifecycle.events) == 1
    assert len(peer.events) == 1
    assert peer.events[0].telegram_message_id == 90
    assert worker.offset == 3


class ReconcileRepository:
    def __init__(self): self.current_item=None; self.items={}
    def reconcile(self, **values):
        if self.current_item and self.current_item.business_connection_id != values["business_connection_id"]:
            self.current_item = SimpleNamespace(
                **{**self.current_item.__dict__, "superseded_at": NOW}
            )
        item = connection(
            connection_id=values["business_connection_id"],
            enabled=values["is_enabled"], can_reply=values["can_reply"],
        )
        self.items[item.business_connection_id] = item
        self.current_item = item
        return item
    def get_current(self, **_kwargs): return self.current_item
    def get_active(self, **_kwargs):
        return self.current_item if self.current_item and self.current_item.usable else None


def event(connection_id, *, enabled=True, can_reply=True):
    return SimpleNamespace(
        business_connection_id=connection_id, business_user_id=6432023689,
        is_enabled=enabled, rights={"can_reply": can_reply},
        connected_at=1700000000,
    )


def test_connection_lifecycle_replaces_and_disables_canonical_state():
    repository = ReconcileRepository()
    service = TelegramBusinessConnectionService(
        repository=repository, bot_telegram_user_id=8214690576,
    )
    assert service.capture(event("old")).business_connection_id == "old"
    assert service.capture(event("new")).business_connection_id == "new"
    assert service.active(business_owner_telegram_user_id=6432023689).business_connection_id == "new"
    service.capture(event("new", enabled=False))
    assert service.active(business_owner_telegram_user_id=6432023689) is None
