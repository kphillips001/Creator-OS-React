import unittest
from unittest.mock import patch

from app.integrations.telegram.telethon_runtime import (
    TelethonRuntime,
    TelethonRuntimeError,
    build_default_runtime_from_environment,
)
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


class EchoDecisionEngine:
    def __init__(self):
        self.calls = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append((user_id, message, chat_history))
        return {
            "response": message,
            "blocked": False,
            "send_offer": False,
        }


class FakeTransport:
    def __init__(self):
        self.handler = None
        self.sent = []
        self.started = False
        self.disconnected = False

    def set_inbound_handler(self, handler):
        self.handler = handler

    async def start(self):
        self.started = True

    async def run_until_disconnected(self):
        return None

    async def disconnect(self):
        self.disconnected = True

    async def send_text(self, *, chat_id, message_text):
        self.sent.append((chat_id, message_text))


class TelethonRuntimeTests(unittest.IsolatedAsyncioTestCase):
    def test_builder_loads_repository_env_before_validation(self):
        loaded_paths = []

        def load_test_env(*, dotenv_path, override):
            loaded_paths.append((dotenv_path, override))

        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "app.integrations.telegram.telethon_runtime.load_dotenv",
                side_effect=load_test_env,
            ),
            patch(
                "app.integrations.telegram.telethon_runtime._required_positive_int",
                side_effect=TelethonRuntimeError("missing test configuration"),
            ),
        ):
            with self.assertRaises(TelethonRuntimeError):
                build_default_runtime_from_environment()

        self.assertEqual(len(loaded_paths), 1)
        self.assertTrue(loaded_paths[0][1])

    def build_runtime(self):
        engine = EchoDecisionEngine()
        gateway = ConversationGateway(
            engine,
            allowed_fanvue_hostnames=["fanvue.com"],
        )
        adapter = TelegramInboundAdapter(
            identity_adapter=TelegramIdentityAdapter(engine_account_id=7),
            conversation_gateway=gateway,
        )
        transport = FakeTransport()
        runtime = TelethonRuntime(
            transport=transport,
            inbound_adapter=adapter,
        )
        return runtime, transport, engine

    async def test_hello_runs_gateway_in_thread_and_replies_hello(self):
        runtime, transport, engine = self.build_runtime()
        payload = TelegramInboundPayload(
            telegram_user_id=123456789,
            telegram_chat_id=123456789,
            message_text="hello",
            message_id=42,
        )
        thread_calls = []

        async def recording_to_thread(function, *args):
            thread_calls.append((function, args))
            return function(*args)

        with (
            patch.dict("os.environ", {}, clear=True),
            patch(
                "app.integrations.telegram.telethon_runtime.asyncio.to_thread",
                new=recording_to_thread,
            ),
        ):
            result = await runtime.handle_payload(payload)

        self.assertEqual(len(thread_calls), 1)
        self.assertEqual(
            engine.calls,
            [("7:-123456789", "hello", [])],
        )
        self.assertEqual(result.response_text, "hello")
        self.assertFalse(result.offer_authorized)
        self.assertEqual(transport.sent, [(123456789, "hello")])

    async def test_disabled_replies_return_before_gateway_and_send(self):
        runtime, transport, engine = self.build_runtime()
        payload = TelegramInboundPayload(
            telegram_user_id=123456789,
            telegram_chat_id=123456789,
            message_text="hello",
            message_id=42,
        )

        with (
            patch.dict(
                "os.environ",
                {"TELEGRAM_REPLIES_ENABLED": "false"},
                clear=False,
            ),
            patch(
                "app.integrations.telegram.telethon_runtime.asyncio.to_thread"
            ) as to_thread,
            self.assertLogs("telethon-runtime", level="INFO") as logs,
        ):
            result = await runtime.handle_payload(payload)

        self.assertIsNone(result)
        to_thread.assert_not_called()
        self.assertEqual(engine.calls, [])
        self.assertEqual(transport.sent, [])
        self.assertIn(
            "[TELEGRAM PAUSED] inbound message suppressed "
            "chat_id=123456789 user_id=123456789",
            "\n".join(logs.output),
        )

    async def test_offer_metadata_is_never_appended_to_response(self):
        class OfferEngine(EchoDecisionEngine):
            def process_message(self, user_id, message, chat_history=None):
                return {
                    "response": "plain response",
                    "blocked": False,
                    "send_offer": True,
                    "offer": {
                        "content": {"fanvue_link": "https://fanvue.com/offer"}
                    },
                }

        engine = OfferEngine()
        adapter = TelegramInboundAdapter(
            identity_adapter=TelegramIdentityAdapter(engine_account_id=7),
            conversation_gateway=ConversationGateway(
                engine,
                allowed_fanvue_hostnames=["fanvue.com"],
            ),
        )
        transport = FakeTransport()
        runtime = TelethonRuntime(
            transport=transport,
            inbound_adapter=adapter,
        )

        await runtime.handle_payload(
            TelegramInboundPayload(
                telegram_user_id=123456789,
                telegram_chat_id=123456789,
                message_text="hello",
                message_id=42,
            )
        )

        self.assertEqual(transport.sent, [(123456789, "plain response")])

    async def test_run_connects_and_disconnects_transport(self):
        runtime, transport, _ = self.build_runtime()

        await runtime.run()

        self.assertTrue(transport.started)
        self.assertTrue(transport.disconnected)


if __name__ == "__main__":
    unittest.main()
