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


def test_capture_filter_adds_only_business_connection_lifecycle():
    session = Session({"ok": True, "result": []})
    capture = TelegramBusinessConnectionCapture(bot_token="token", session=session)

    assert capture.configure_and_peek() == ()

    allowed = json.loads(session.calls[0][1]["params"]["allowed_updates"])
    assert allowed == list(BOT_API_ALLOWED_UPDATES)
    assert "business_connection" in allowed
    assert "business_message" not in allowed
    assert "edited_business_message" not in allowed
    assert "deleted_business_messages" not in allowed


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
