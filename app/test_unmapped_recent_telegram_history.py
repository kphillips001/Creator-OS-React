from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.conversation_gateway import (
    ConversationBrainContext, ConversationGatewayInput, ConversationGatewayOutput,
)
from app.models.ordinary_chat_reply_operation import OrdinaryChatReplyState
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.conversation_gateway import ConversationGateway
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


NOW = datetime(2026, 8, 26, tzinfo=timezone.utc)


def operation(number, *, state=OrdinaryChatReplyState.SENT_CONFIRMED,
              response=None, outbound=True, operation_id=None):
    return SimpleNamespace(
        operation_id=operation_id or uuid4(), state=state,
        inbound_telegram_message_id=number,
        inbound_message_text=f"customer {number}",
        response_text=(f"ava {number}" if response is None else response),
        outbound_telegram_message_id=(number + 1000 if outbound else None),
        inbound_received_at=NOW + timedelta(minutes=number), created_at=NOW,
    )


class HistoryRepository:
    def __init__(self, operations):
        self.operations = operations
        self.calls = []

    def list_confirmed_recent_for_prospect(self, **values):
        self.calls.append(values)
        return list(self.operations)


def test_recent_prospect_history_is_confirmed_chronological_bounded_and_deduped():
    duplicate_id = uuid4()
    rows = [operation(index) for index in range(1, 7)]
    rows.extend((
        operation(7, state=OrdinaryChatReplyState.SUPPRESSED),
        operation(8, state=OrdinaryChatReplyState.RETRYABLE),
        operation(9, state=OrdinaryChatReplyState.SEND_UNCERTAIN),
        operation(10, state=OrdinaryChatReplyState.TERMINAL_FAILED),
        operation(11, state=OrdinaryChatReplyState.GENERATED),
        operation(12, response=""),
        operation(13, outbound=False),
        operation(5, operation_id=duplicate_id),
        operation(5, operation_id=duplicate_id),
        operation(99),
    ))
    repository = HistoryRepository(reversed(rows))
    service = OrdinaryChatReplyService(repository=repository)

    history = service.recent_confirmed_history(
        creator_profile_id=3, fanvue_account_id=2,
        telegram_user_id=123, telegram_chat_id=123,
        exclude_inbound_message_id=99,
    )

    assert history == [
        {"role": "user", "content": "customer 3"},
        {"role": "assistant", "content": "ava 3"},
        {"role": "user", "content": "customer 4"},
        {"role": "assistant", "content": "ava 4"},
        {"role": "user", "content": "customer 5"},
        {"role": "assistant", "content": "ava 5"},
        {"role": "user", "content": "customer 6"},
        {"role": "assistant", "content": "ava 6"},
    ]
    assert repository.calls[0] == {
        "creator_profile_id": 3, "fanvue_account_id": 2,
        "telegram_user_id": 123, "telegram_chat_id": 123,
        "account_scope": "AVA_TELETHON_PRIVATE",
        "exclude_inbound_message_id": 99, "limit": 4,
    }


class Gateway:
    def __init__(self):
        self.calls = []

    def execute(self, value):
        self.calls.append(value)
        return ConversationGatewayOutput(
            correlation_id=value.correlation_id, response_text="next reply",
            offer_authorized=False, offer_link=None, blocked=False,
            error_code=None, diagnostic_metadata={"status": "ok"},
        )


def test_unmapped_adapter_reconstructs_history_after_recreation_without_current_turn():
    calls = []

    def load(**values):
        calls.append(values)
        return [
            {"role": "user", "content": "previous question"},
            {"role": "assistant", "content": "previous Ava reply"},
        ]

    gateway = Gateway()
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=gateway, creator_profile_id=3,
        fanvue_account_id=2, unmapped_conversation_history_loader=load,
        unmapped_telegram_prospect_service=SimpleNamespace(
            observe=lambda **_values: None,
        ),
    )
    payload = TelegramInboundPayload(
        telegram_user_id=123, telegram_chat_id=123,
        message_text="current message", message_id=44, chat_history=[],
    )
    result = adapter.execute(payload)

    assert gateway.calls[0].chat_history == [
        {"role": "user", "content": "previous question"},
        {"role": "assistant", "content": "previous Ava reply"},
    ]
    assert "current message" not in {
        item["content"] for item in gateway.calls[0].chat_history
    }
    assert calls[0]["exclude_inbound_message_id"] == 44
    assert result.diagnostic_metadata["recentHistorySource"] == (
        "TELEGRAM_DURABLE_PROSPECT"
    )
    assert result.diagnostic_metadata["recentHistoryTurnCount"] == 1

    restarted_gateway = Gateway()
    restarted = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=restarted_gateway, creator_profile_id=3,
        fanvue_account_id=2, unmapped_conversation_history_loader=load,
        unmapped_telegram_prospect_service=SimpleNamespace(
            observe=lambda **_values: None,
        ),
    )
    restarted.execute(payload)
    assert restarted_gateway.calls[0].chat_history == gateway.calls[0].chat_history


def test_mapped_canonical_history_has_precedence_over_prospect_fallback():
    gateway = Gateway()
    fallback_calls = []
    canonical = SimpleNamespace(
        engine_user_id="2:9", fanvue_account_id=2, local_fanvue_user_id=9,
        external_fanvue_user_uuid="00000000-0000-0000-0000-000000000009",
    )
    identities = SimpleNamespace(
        observe=lambda **_values: None,
        resolve_telegram_identity=lambda _telegram_user_id: canonical,
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=gateway, creator_profile_id=3,
        fanvue_account_id=2, telegram_identity_service=identities,
        conversation_thread_resolver=lambda **_values: {"id": 77},
        conversation_history_loader=lambda **_values: [
            {"role": "assistant", "content": "canonical history"},
        ],
        unmapped_conversation_history_loader=lambda **values: (
            fallback_calls.append(values) or []
        ),
    )
    result = adapter.execute(TelegramInboundPayload(
        telegram_user_id=123, telegram_chat_id=123,
        message_text="current", message_id=45, chat_history=[],
    ))

    assert gateway.calls[0].chat_history == [
        {"role": "assistant", "content": "canonical history"},
    ]
    assert fallback_calls == []
    assert result.diagnostic_metadata["recentHistorySource"] == (
        "CANONICAL_MAPPED_CONVERSATION"
    )


def test_empty_newly_mapped_thread_uses_explicit_non_merged_prospect_fallback():
    gateway = Gateway()
    canonical = SimpleNamespace(
        engine_user_id="2:9", fanvue_account_id=2, local_fanvue_user_id=9,
        external_fanvue_user_uuid="00000000-0000-0000-0000-000000000009",
    )
    identities = SimpleNamespace(
        observe=lambda **_values: None,
        resolve_telegram_identity=lambda _telegram_user_id: canonical,
    )
    adapter = TelegramInboundAdapter(
        identity_adapter=TelegramIdentityAdapter(engine_account_id=2),
        conversation_gateway=gateway, creator_profile_id=3,
        fanvue_account_id=2, telegram_identity_service=identities,
        conversation_thread_resolver=lambda **_values: {"id": 77},
        conversation_history_loader=lambda **_values: [],
        unmapped_conversation_history_loader=lambda **_values: [
            {"role": "user", "content": "pre-mapping customer"},
            {"role": "assistant", "content": "pre-mapping Ava"},
        ],
    )
    result = adapter.execute(TelegramInboundPayload(
        telegram_user_id=123, telegram_chat_id=123,
        message_text="first mapped turn", message_id=46, chat_history=[],
    ))

    assert gateway.calls[0].chat_history == [
        {"role": "user", "content": "pre-mapping customer"},
        {"role": "assistant", "content": "pre-mapping Ava"},
    ]
    assert result.diagnostic_metadata["recentHistorySource"] == (
        "TELEGRAM_DURABLE_PROSPECT_FALLBACK"
    )


def test_sales_brain_receives_recent_customer_requests_from_gateway_history(monkeypatch):
    monkeypatch.setenv("CONTROLLED_AUTONOMY_TEST_ENABLED", "false")
    captured = []
    brain = SimpleNamespace(evaluate_for_telegram_user=lambda **values: (
        captured.append(values) or SimpleNamespace(
            decision=SimpleNamespace(value="NO_SALE"),
            reason_code=SimpleNamespace(value="NO_ELIGIBLE_OFFERING"),
        )
    ))
    gateway = ConversationGateway.__new__(ConversationGateway)
    gateway._customer_sales_brain_service = brain
    gateway._chat_commerce_service = None
    gateway._creator_profile_id = 3
    gateway._brain_context = lambda _input: ConversationBrainContext(
        creator_profile_id=3, fanvue_account_id=2,
        telegram_user_id=123, telegram_chat_id=123,
        customer_identifier="2:-123", conversation_identifier="operation-3",
    )
    gateway._evaluate_customer_sales_brain(ConversationGatewayInput(
        engine_user_id="2:-123", message_text="current", correlation_id="operation-3",
        chat_history=[
            {"role": "user", "content": "first request"},
            {"role": "assistant", "content": "Ava reply"},
            {"role": "user", "content": "second request"},
        ],
    ))

    context = captured[0]["conversation_context"]
    assert context["recent_conversation_requests"] == (
        "first request", "second request",
    )
