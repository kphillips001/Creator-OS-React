import ast
import json

from app.integrations.telegram.business_connection_capture import (
    BOT_API_ALLOWED_UPDATES,
    TelegramBusinessConnectionCapture,
)


class Response:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class Session:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return Response(self.payload)


def test_capture_filter_includes_business_peer_observability_updates():
    session = Session({"ok": True, "result": []})
    capture = TelegramBusinessConnectionCapture(bot_token="token", session=session)

    assert capture.configure_and_peek() == ()

    allowed = json.loads(session.calls[0][1]["params"]["allowed_updates"])
    assert allowed == list(BOT_API_ALLOWED_UPDATES)
    assert "business_connection" in allowed
    assert "business_message" in allowed
    assert "edited_business_message" in allowed
    assert "deleted_business_messages" in allowed


def test_business_message_metadata_is_captured_without_content_routing():
    events = TelegramBusinessConnectionCapture.parse({
        "update_id": 101,
        "business_message": {
            "business_connection_id": "bc-1", "message_id": 700,
            "date": 1700000000, "text": "must not be persisted here",
            "from": {"id": 789}, "chat": {"id": 789, "type": "private"},
        },
    })
    assert len(events) == 1
    event = events[0]
    assert event.business_connection_id == "bc-1"
    assert event.telegram_peer_user_id == 789
    assert event.telegram_chat_id == 789
    assert event.telegram_message_id == 700
    assert event.provider_timestamp == 1700000000
    assert event.sender_telegram_user_id == 789
    assert not hasattr(event, "text")


def test_edited_and_deleted_business_message_metadata_is_captured():
    edited = TelegramBusinessConnectionCapture.parse({
        "update_id": 102,
        "edited_business_message": {
            "business_connection_id": "bc-1", "message_id": 700,
            "date": 1700000000, "edit_date": 1700000100,
            "from": {"id": 789}, "chat": {"id": 789, "type": "private"},
        },
    })
    deleted = TelegramBusinessConnectionCapture.parse({
        "update_id": 103,
        "deleted_business_messages": {
            "business_connection_id": "bc-1",
            "chat": {"id": 789}, "message_ids": [700, 701],
        },
    })
    assert edited[0].event_type == "edited_business_message"
    assert edited[0].provider_timestamp == 1700000100
    assert [event.telegram_message_id for event in deleted] == [700, 701]
    assert all(event.event_type == "deleted_business_messages" for event in deleted)


def test_connection_event_is_safely_captured_without_message_routing():
    session = Session({"ok": True, "result": [
        {"update_id": 91, "message": {"text": "must be ignored"}},
        {"update_id": 92, "business_connection": {
            "id": "connection-id", "user": {
                "id": 123, "first_name": "Ava", "last_name": "Blackthorne",
                "username": "ava",
            }, "user_chat_id": 456, "date": 1700000000,
            "is_enabled": True,
            "rights": {"can_reply": True, "can_read_messages": True},
        }},
    ]})
    capture = TelegramBusinessConnectionCapture(bot_token="token", session=session)

    events = capture.configure_and_peek()

    assert len(events) == 1
    event = events[0]
    assert event.business_connection_id == "connection-id"
    assert event.business_user_id == 123
    assert event.user_chat_id == 456
    assert event.is_enabled is True
    assert event.rights == {"can_reply": True, "can_read_messages": True}


def test_capture_module_has_no_conversation_or_commerce_dependencies():
    source = open(
        "app/integrations/telegram/business_connection_capture.py",
        encoding="utf-8",
    ).read()
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    for forbidden in (
        "ConversationGateway", "SalesBrain", "OrdinaryChatReply",
        "PurchaseIntent",
    ):
        assert all(forbidden not in name for name in imported)
    assert "sendMessage" not in source
