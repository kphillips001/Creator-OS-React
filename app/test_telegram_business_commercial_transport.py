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


class Sender:
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


def transport(item=None, *, enabled=True):
    sender = Sender()
    return TelegramBusinessCommercialTransport(
        enabled=enabled, owner_user_id=6432023689, bot_id=8214690576,
        connection_service=Connections(item), sender=sender,
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
        "expected_business_owner_user_id": 6432023689,
        "expected_business_bot_id": 8214690576,
    }]
    assert "https://" not in sender.calls[0]["message_text"]


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


def test_peer_usage_missing_is_explicit_and_never_retried():
    http = Http(Response({"ok": False, "description": "Bad Request: BUSINESS_PEER_USAGE_MISSING"}, 400))
    sender = TelegramBotApiSender(bot_token="token", session=http)
    with pytest.raises(TelegramBusinessPeerUsageMissingError):
        sender.send_text(chat_id=7857064998, message_text="offer")
    assert len(http.calls) == 1


class Allow:
    def check_global_safety(self): return {"allowed": True}


class OrdinarySender:
    def __init__(self): self.calls=[]
    async def send_text(self, **kwargs): self.calls.append(kwargs); return 99


def test_executor_uses_business_only_for_unlock_and_telethon_for_ordinary():
    business, business_sender = transport(connection())
    ordinary = OrdinarySender()
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    ordinary_result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(message_text="hello", delivery_method="text"),
        context={"chat_id": 7857064998, "transport": ordinary},
    ))
    commercial_result = asyncio.run(executor.execute_async(
        TelegramDeliveryPayload(
            message_text="Natural Ava offer", delivery_method="text",
            metadata={"private_chat_unlock_button": {
                "label": "🔓 Unlock", "url": "https://creator.example/unlock/opaque",
            }},
        ), context={"chat_id": 7857064998, "transport": ordinary},
    ))
    assert ordinary_result.metadata["telegram_message_id"] == 99
    assert len(ordinary.calls) == 1
    assert len(business_sender.calls) == 1
    assert commercial_result.metadata["attachment_mode"] == "TELEGRAM_BUSINESS_INLINE_BUTTON"


def test_executor_rejects_local_destination_before_business_send():
    business, sender = transport(connection())
    executor = TelegramDeliveryExecutor(
        global_safety_service=Allow(), business_commercial_transport=business,
    )
    with pytest.raises(ValueError, match="CUSTOMER_FACING_DESTINATION_NOT_PUBLIC"):
        asyncio.run(executor.execute_async(
            TelegramDeliveryPayload(
                message_text="offer", delivery_method="text",
                metadata={"private_chat_unlock_button": {
                    "label": "🔓 Unlock", "url": "http://127.0.0.1:8001/unlock/x",
                }},
            ), context={"chat_id": 7857064998, "transport": OrdinarySender(),
                        "raise_on_failure": True},
        ))
    assert sender.calls == []


class Lifecycle:
    def __init__(self): self.events=[]
    def capture(self, event): self.events.append(event); return event


class GetSession:
    def __init__(self, updates): self.updates=updates; self.calls=[]
    def get(self, url, **kwargs):
        self.calls.append((url,kwargs)); return Response({"ok":True,"result":self.updates})


def test_lifecycle_worker_ignores_business_messages_and_captures_connection_only():
    lifecycle=Lifecycle()
    session=GetSession([
        {"update_id":1,"business_message":{"text":"do not route"}},
        {"update_id":2,"business_connection":{
            "id":"bc-2","user":{"id":6432023689,"first_name":"Ava"},
            "user_chat_id":6432023689,"date":1700000000,"is_enabled":True,
            "rights":{"can_reply":True},
        }},
    ])
    worker=TelegramBusinessConnectionWorker(
        bot_token="token",lifecycle_service=lifecycle,session=session,timeout_seconds=0,
    )
    assert len(worker.poll_once()) == 1
    assert len(lifecycle.events) == 1
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
