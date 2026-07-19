from types import SimpleNamespace

from app.api import test_chat as api
from app.services import test_chat_service as service_module
from app.services.test_chat_service import TestChatService as DeveloperTestChatService
from app.services.test_chat_service import TestChatExecutionError


class FakeMemory:
    def __init__(self):
        self.data = {"relationship_stage": "warm", "buyer_tier": "new_buyer"}
        self.resets = []

    def get_user_memory(self, user_id):
        return dict(self.data)

    def clear_user_memory(self, user_id):
        self.resets.append(user_id)
        self.data = {}


class FakeDecisionEngine:
    def __init__(self):
        self.calls = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append((user_id, message, chat_history))
        return {
            "response": "I can help with that.",
            "route": {
                "route": "sales",
                "reason": "Buying intent detected",
                "classifier_result": {"buying_intent": True},
            },
            "intent": {"tier": "high"},
            "send_offer": False,
            "selected_content": None,
        }


def _service(monkeypatch):
    memory = FakeMemory()
    engine = FakeDecisionEngine()
    monkeypatch.setattr(service_module, "memory_service", memory)
    monkeypatch.setattr(
        service_module,
        "get_account_by_id",
        lambda account_id: {"id": account_id, "username": "creator"},
    )
    monkeypatch.setattr(
        service_module,
        "get_or_create_user_with_memory",
        lambda **kwargs: {
            "user": {"id": 9, "display_name": "Test User", "relationship_status": "follower"}
        },
    )
    return DeveloperTestChatService(account_id=4, engine=engine), memory, engine


def test_real_gateway_path_returns_narrow_summary_without_transport(monkeypatch):
    service, _, engine = _service(monkeypatch)
    session = service.new_session()

    result = service.process(session["session_id"], "What can I buy?")

    assert engine.calls == [("4:9", "What can I buy?", [])]
    assert result == {
        "reply": "I can help with that.",
        "intent": "high",
        "relationship": "sales",
        "sell": True,
        "reason": "No eligible products",
        "product": None,
        "asset": None,
    }
    assert not hasattr(service._gateway, "telegram_transport")
    assert not hasattr(service._gateway, "fanvue_transport")


def test_clear_chat_and_reset_memory_keep_persistent_test_user(monkeypatch):
    service, memory, _ = _service(monkeypatch)
    session_id = service.new_session()["session_id"]
    service.process(session_id, "Hello")

    assert service.clear_chat(session_id)["messages"] == []
    reset = service.reset_memory(session_id)

    assert memory.resets == ["4:9"]
    assert reset["test_user"]["name"] == "Test User"


def test_api_accepts_session_id_and_customer_message(monkeypatch):
    stub = SimpleNamespace(
        process=lambda session_id, message: {
            "session_id": session_id,
            "reply": f"reply:{message}",
        }
    )
    monkeypatch.setattr(api, "_service", lambda: stub)

    result = api.process_test_chat_turn(
        api.TestChatTurnRequest(session_id="session-1", customer_message="hello")
    )

    assert result == {"session_id": "session-1", "reply": "reply:hello"}


def test_engine_exception_preserves_developer_traceback(monkeypatch):
    service, _, engine = _service(monkeypatch)
    session_id = service.new_session()["session_id"]

    def fail(*args, **kwargs):
        raise RuntimeError("composition failed")

    engine.process_message = fail
    try:
        service.process(session_id, "Hello")
        raise AssertionError("Expected TestChatExecutionError")
    except TestChatExecutionError as error:
        assert error.diagnostics["exception_type"] == "RuntimeError"
        assert error.diagnostics["exception_message"] == "composition failed"
        assert error.diagnostics["file"].endswith("test_test_chat.py")
        assert "RuntimeError: composition failed" in error.diagnostics["stack_trace"]
