import ast
import os
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

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
    def setUp(self):
        self._feature_flags = patch.dict(os.environ, {
            "PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED": "false",
            "CONTROLLED_AUTONOMY_TEST_ENABLED": "false",
        })
        self._feature_flags.start()

    def tearDown(self):
        self._feature_flags.stop()

    def test_purchase_acknowledgement_lookup_uses_supported_identity_contract(self):
        calls = []

        class Purchases:
            def get_unacknowledged_purchase(
                self, *, creator_profile_id, fanvue_account_id, telegram_user_id,
            ):
                calls.append((creator_profile_id, fanvue_account_id, telegram_user_id))
                return None

        observations = []
        identities = SimpleNamespace(
            observe=lambda **values: observations.append(values),
            resolve_telegram_identity=lambda _user_id: None,
        )
        adapter = TelegramInboundAdapter(
            identity_adapter=RecordingIdentityAdapter(),
            conversation_gateway=RecordingConversationGateway(),
            creator_profile_id=3, fanvue_account_id=2,
            purchase_intent_service=Purchases(),
            telegram_identity_service=identities,
            unmapped_telegram_prospect_service=SimpleNamespace(
                observe=lambda **_values: None,
            ),
        )

        adapter.execute(inbound_payload())

        self.assertEqual(calls, [(3, 2, 123456789)])
        self.assertEqual(len(observations), 1)

    def test_explicit_more_is_persisted_before_purchase_acknowledgement_reply(self):
        intent_id = "00000000-0000-0000-0000-000000000123"
        prospect_calls = []
        prospects = SimpleNamespace(
            observe=lambda **values: prospect_calls.append(("observe", values)),
            record_deferred_continuation=lambda **values: prospect_calls.append(
                ("defer", values)
            ),
        )
        purchases = SimpleNamespace(
            identities=SimpleNamespace(
                get_by_telegram_user_id=lambda _user_id: None,
            ),
            get_unacknowledged_purchase=lambda **_values: SimpleNamespace(
                purchase_intent_id=intent_id,
            ),
        )
        adapter = TelegramInboundAdapter(
            identity_adapter=RecordingIdentityAdapter(),
            conversation_gateway=RecordingConversationGateway(),
            creator_profile_id=3, fanvue_account_id=2,
            purchase_intent_service=purchases,
            unmapped_telegram_prospect_service=prospects,
        )

        adapter.execute(inbound_payload(
            message_text="send another", message_id=77,
        ))

        deferred = [values for action, values in prospect_calls if action == "defer"]
        self.assertEqual(len(deferred), 1)
        self.assertEqual(deferred[0]["source_inbound_message_id"], 77)
        self.assertEqual(deferred[0]["purchase_intent_id"], intent_id)
        self.assertEqual(deferred[0]["continuation_type"], "DISCRETE_ITEM")
        self.assertEqual(
            deferred[0]["source_correlation_id"], "telegram:123456789:77",
        )

    def test_verified_mapping_uses_canonical_engine_identity_after_chat_metadata_changes(self):
        gateway = RecordingConversationGateway()
        observations = []
        canonical = SimpleNamespace(
            engine_user_id="2:9", fanvue_account_id=2, local_fanvue_user_id=9,
            external_fanvue_user_uuid="00000000-0000-0000-0000-000000000009",
        )
        identities = SimpleNamespace(
            observe=lambda **values: observations.append(values),
            resolve_telegram_identity=lambda _user_id: canonical,
        )
        adapter = TelegramInboundAdapter(
            identity_adapter=RecordingIdentityAdapter(), conversation_gateway=gateway,
            telegram_identity_service=identities,
        )

        result = adapter.execute(inbound_payload(
            telegram_chat_id=987654321, telegram_username="renamed_customer",
            telegram_display_name="Renamed Customer",
        ))

        self.assertEqual(result.engine_user_id, "2:9")
        self.assertEqual(gateway.calls[0].engine_user_id, "2:9")
        self.assertEqual(observations[0]["telegram_user_id"], 123456789)
        self.assertEqual(observations[0]["telegram_chat_id"], 987654321)

    def test_unmapped_customer_can_chat_but_paid_offer_is_removed(self):
        from app.services.telegram_identity_service import TelegramIdentityNotFoundError
        gateway = RecordingConversationGateway(ConversationGatewayOutput(
            correlation_id="paid", response_text="Buy this", offer_authorized=True,
            offer_link="https://fanvue.com/offer", blocked=False, error_code=None,
            delivery_requires_payment=True,
            delivery_payload={"message_text": "Buy this", "media_link": "secret"},
        ))
        identities = SimpleNamespace(
            observe=lambda **_values: None,
            resolve_telegram_identity=lambda _user_id: (_ for _ in ()).throw(
                TelegramIdentityNotFoundError("unmapped")
            ),
        )
        adapter = TelegramInboundAdapter(
            identity_adapter=RecordingIdentityAdapter(), conversation_gateway=gateway,
            telegram_identity_service=identities,
        )

        result = adapter.execute(inbound_payload())

        self.assertEqual(len(gateway.calls), 1)
        self.assertFalse(result.offer_authorized)
        self.assertIsNone(result.offer_link)
        self.assertFalse(result.delivery_requires_payment)
        self.assertNotIn("media_link", result.delivery_payload)
        self.assertEqual(
            result.diagnostic_metadata["paid_offer_blocked_reason"],
            "TELEGRAM_IDENTITY_UNVERIFIED",
        )

    def test_canonical_transcript_survives_adapter_recreation_without_current_duplication(self):
        thread = {"id": 77}
        messages = {}
        gateway_one = RecordingConversationGateway()
        gateway_two = RecordingConversationGateway()
        canonical_identity = SimpleNamespace(
            fanvue_account_id=2, local_fanvue_user_id=9,
            external_fanvue_user_uuid="00000000-0000-0000-0000-000000000009",
        )
        purchases = SimpleNamespace(
            identities=SimpleNamespace(
                get_by_telegram_user_id=lambda _user_id: canonical_identity
            ),
            get_unacknowledged_purchase=lambda **_kwargs: None,
        )

        def save(**values):
            messages.setdefault(values["fanvue_message_uuid"], dict(values))

        def history(**values):
            excluded = values["exclude_message_uuid"]
            rows = [row for key, row in messages.items() if key != excluded]
            rows = rows[-values["limit"]:]
            return [
                {"role": "user" if row["sender_type"] == "user" else "assistant",
                 "content": row["text"]}
                for row in rows
            ]

        dependencies = dict(
            identity_adapter=RecordingIdentityAdapter(), creator_profile_id=3,
            fanvue_account_id=2, purchase_intent_service=purchases,
            conversation_thread_resolver=lambda **_kwargs: thread,
            conversation_message_saver=save, conversation_history_loader=history,
        )
        first = TelegramInboundAdapter(
            conversation_gateway=gateway_one, **dependencies
        )
        first_result = first.execute(inbound_payload(
            message_text="first message", message_id=1, chat_history=[]
        ))
        save(
            fanvue_account_id=2, thread_id=77, fanvue_user_id=9,
            direction="outbound", sender_type="bot", text="first reply",
            fanvue_message_uuid="outbound-1", raw_payload={},
        )

        restarted = TelegramInboundAdapter(
            conversation_gateway=gateway_two, **dependencies
        )
        second_payload = inbound_payload(
            message_text="second message", message_id=2, chat_history=[]
        )
        second_result = restarted.execute(second_payload)
        restarted.execute(second_payload)

        self.assertEqual(first_result.diagnostic_metadata["conversation_thread_id"], 77)
        self.assertEqual(second_result.diagnostic_metadata["conversation_thread_id"], 77)
        self.assertEqual(gateway_one.calls[0].chat_history, [])
        self.assertEqual(gateway_two.calls[0].chat_history, [
            {"role": "user", "content": "first message"},
            {"role": "assistant", "content": "first reply"},
        ])
        self.assertNotIn("second message", [
            item["content"] for item in gateway_two.calls[0].chat_history
        ])
        inbound_rows = [
            row for row in messages.values()
            if row["direction"] == "inbound" and row["text"] == "second message"
        ]
        self.assertEqual(len(inbound_rows), 1)
        self.assertEqual(
            gateway_two.calls[0].brain_context.conversation_thread_id, 77
        )

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
            {
                **gateway_output.diagnostic_metadata,
                "recentHistorySource": "NONE",
                "recentHistoryTurnCount": 0,
            },
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
