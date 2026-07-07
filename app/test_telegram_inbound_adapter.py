import ast
import unittest
from pathlib import Path

from app.models.conversation_gateway import ConversationGatewayOutput
from app.models.telegram_identity import TelegramMvpIdentityInput
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import (
    InvalidTelegramInboundError,
    TelegramInboundAdapter,
)


class RecordingIdentityAdapter:
    def __init__(self):
        self.real_adapter = TelegramIdentityAdapter(engine_account_id=7)
        self.calls = []

    def adapt(self, identity: TelegramMvpIdentityInput):
        self.calls.append(identity)
        return self.real_adapter.adapt(identity)


class RecordingConversationGateway:
    def __init__(self, output=None):
        self.calls = []
        self.output = output

    def execute(self, gateway_input):
        self.calls.append(gateway_input)
        if self.output is not None:
            return self.output
        return ConversationGatewayOutput(
            correlation_id=gateway_input.correlation_id,
            response_text="Normalized Ava reply",
            offer_authorized=False,
            offer_link=None,
            blocked=False,
            error_code=None,
            diagnostic_metadata={"status": "ok"},
        )


def inbound_payload(**overrides):
    values = {
        "telegram_user_id": 123456789,
        "telegram_chat_id": 123456789,
        "message_text": "hello Ava",
        "message_id": 42,
        "chat_history": [{"role": "user", "content": "earlier"}],
        "correlation_id": None,
    }
    values.update(overrides)
    return TelegramInboundPayload(**values)


class TelegramInboundAdapterTests(unittest.TestCase):
    def build_adapter(self, *, gateway_output=None):
        identity_adapter = RecordingIdentityAdapter()
        gateway = RecordingConversationGateway(gateway_output)
        adapter = TelegramInboundAdapter(
            identity_adapter=identity_adapter,
            conversation_gateway=gateway,
        )
        return adapter, identity_adapter, gateway

    def test_valid_payload_uses_identity_and_reaches_gateway_once(self):
        adapter, identity_adapter, gateway = self.build_adapter()
        payload = inbound_payload(correlation_id="supplied-correlation")

        result = adapter.execute(payload)

        self.assertEqual(len(identity_adapter.calls), 1)
        self.assertEqual(
            identity_adapter.calls[0],
            TelegramMvpIdentityInput(
                telegram_user_id=123456789,
                telegram_chat_id=123456789,
            ),
        )
        self.assertEqual(len(gateway.calls), 1)
        request = gateway.calls[0]
        self.assertEqual(request.engine_user_id, "7:-123456789")
        self.assertEqual(request.message_text, payload.message_text)
        self.assertIs(request.chat_history, payload.chat_history)
        self.assertEqual(request.correlation_id, "supplied-correlation")
        self.assertEqual(result.engine_user_id, "7:-123456789")

    def test_supplied_correlation_id_is_preserved(self):
        adapter, _, gateway = self.build_adapter()

        result = adapter.execute(
            inbound_payload(correlation_id="caller-owned-id")
        )

        self.assertEqual(gateway.calls[0].correlation_id, "caller-owned-id")
        self.assertEqual(result.correlation_id, "caller-owned-id")

    def test_missing_correlation_id_is_generated_deterministically(self):
        adapter, _, gateway = self.build_adapter()
        payload = inbound_payload(
            telegram_chat_id=-100987654321,
            message_id=314,
        )

        first = adapter.execute(payload)
        second = adapter.execute(payload)

        expected = "telegram:-100987654321:314"
        self.assertEqual(first.correlation_id, expected)
        self.assertEqual(second.correlation_id, expected)
        self.assertEqual(gateway.calls[0].correlation_id, expected)
        self.assertEqual(gateway.calls[1].correlation_id, expected)

    def test_response_and_offer_fields_pass_through_gateway_only(self):
        gateway_output = ConversationGatewayOutput(
            correlation_id="offer-correlation",
            response_text="Gateway-approved response",
            offer_authorized=True,
            offer_link="https://fanvue.com/ava/offer",
            blocked=False,
            error_code=None,
            diagnostic_metadata={
                "status": "ok",
                "offer_link_accepted": True,
            },
        )
        adapter, _, _ = self.build_adapter(gateway_output=gateway_output)

        result = adapter.execute(
            inbound_payload(
                message_text="this text must not decide the offer",
                correlation_id="input-correlation",
            )
        )

        self.assertEqual(result.correlation_id, "offer-correlation")
        self.assertEqual(result.response_text, "Gateway-approved response")
        self.assertTrue(result.offer_authorized)
        self.assertEqual(
            result.offer_link,
            "https://fanvue.com/ava/offer",
        )
        self.assertFalse(result.blocked)
        self.assertIsNone(result.error_code)
        self.assertEqual(
            result.diagnostic_metadata,
            gateway_output.diagnostic_metadata,
        )
        self.assertIsNot(
            result.diagnostic_metadata,
            gateway_output.diagnostic_metadata,
        )

    def test_metadata_and_gateway_block_are_normalized(self):
        gateway_output = ConversationGatewayOutput(
            correlation_id="blocked-correlation",
            response_text="Blocked response",
            offer_authorized=False,
            offer_link=None,
            blocked=True,
            error_code="creator_profile_required",
            diagnostic_metadata={"status": "blocked"},
        )
        adapter, _, _ = self.build_adapter(gateway_output=gateway_output)

        result = adapter.execute(inbound_payload())

        self.assertEqual(result.telegram_user_id, 123456789)
        self.assertEqual(result.telegram_chat_id, 123456789)
        self.assertEqual(result.message_id, 42)
        self.assertTrue(result.blocked)
        self.assertEqual(result.error_code, "creator_profile_required")

    def test_invalid_or_empty_message_never_calls_gateway(self):
        for message_text in (None, "", "   ", 123):
            with self.subTest(message_text=message_text):
                adapter, identity_adapter, gateway = self.build_adapter()
                with self.assertRaises(InvalidTelegramInboundError):
                    adapter.execute(
                        inbound_payload(message_text=message_text)
                    )
                self.assertEqual(identity_adapter.calls, [])
                self.assertEqual(gateway.calls, [])

    def test_other_invalid_payload_fields_never_call_gateway(self):
        invalid_overrides = (
            {"message_id": 0},
            {"message_id": True},
            {"chat_history": "not-a-list"},
            {"correlation_id": ""},
            {"telegram_user_id": 0},
            {"telegram_chat_id": 0},
        )
        for overrides in invalid_overrides:
            with self.subTest(overrides=overrides):
                adapter, _, gateway = self.build_adapter()
                with self.assertRaises(InvalidTelegramInboundError):
                    adapter.execute(inbound_payload(**overrides))
                self.assertEqual(gateway.calls, [])

    def test_adapter_has_no_forbidden_imports(self):
        root = Path(__file__).resolve().parents[1]
        files = (
            root / "app" / "models" / "telegram_inbound.py",
            root / "app" / "services" / "telegram_inbound_adapter.py",
        )
        forbidden_fragments = (
            "telegram.ext",
            "telegram.bot",
            "telethon",
            "aiogram",
            "kviqa",
            "fanvue_api",
            "sender",
            "listener",
            "polling",
            "repositories",
            "database",
            "psycopg",
            "sqlalchemy",
            "requests",
            "httpx",
        )

        for path in files:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            imports = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imports.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imports.append(node.module)

            for module in imports:
                with self.subTest(path=path.name, module=module):
                    self.assertFalse(
                        any(
                            fragment in module.lower()
                            for fragment in forbidden_fragments
                        ),
                        module,
                    )


if __name__ == "__main__":
    unittest.main()
