import ast
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from app.models.conversation_gateway import ConversationGatewayInput
from app.repositories.runtime_control_repository import RuntimeControlRepository
from app.services.conversation_gateway import ConversationGateway
from app.services.runtime_control_service import RuntimeControlService


FANVUE_HOST = "share.fanvue.com"
FANVUE_LINK = "https://share.fanvue.com/ava/offer-1"


class FakeDecisionEngine:
    def __init__(self, result: Any = None, error: Exception | None = None):
        self.result = result
        self.error = error
        self.calls: list[dict[str, Any]] = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "chat_history": chat_history,
            }
        )
        if self.error:
            raise self.error
        return self.result


class FakeTelegramCommerceService:
    def __init__(self, result: Any):
        self.result = result
        self.calls: list[dict[str, Any]] = []

    def process_message(self, user_id, message, chat_history=None):
        self.calls.append(
            {
                "user_id": user_id,
                "message": message,
                "chat_history": chat_history,
            }
        )
        return self.result


def gateway_input(**overrides):
    values = {
        "engine_user_id": "1:-123456789",
        "message_text": "hello",
        "chat_history": [{"direction": "inbound", "text": "earlier"}],
        "correlation_id": "generation-123",
    }
    values.update(overrides)
    return ConversationGatewayInput(**values)


def engine_result(**overrides):
    values = {
        "response": "Hey you",
        "send_offer": False,
        "offer": {"offer_type": "none", "content": None},
        "route": {"route": "chat", "token": "must-not-leak"},
        "mode": "conversation",
    }
    values.update(overrides)
    return values


class ConversationGatewayTests(unittest.TestCase):
    def build_gateway(self, engine):
        return ConversationGateway(
            engine,
            allowed_fanvue_hostnames=[FANVUE_HOST],
        )

    def test_offline_runtime_blocks_replies_without_calling_engine(self):
        with TemporaryDirectory() as directory:
            runtime = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            runtime.stop(creator_profile_id=7)
            engine = FakeDecisionEngine(engine_result())
            gateway = ConversationGateway(
                engine,
                allowed_fanvue_hostnames=[FANVUE_HOST],
                runtime_control_service=runtime,
                creator_profile_id=7,
            )

            output = gateway.execute(gateway_input())

            self.assertTrue(output.blocked)
            self.assertEqual(output.error_code, "runtime_offline")
            self.assertEqual(output.response_text, "")
            self.assertEqual(engine.calls, [])

    def test_observe_runtime_records_recommendations_but_sends_nothing(self):
        with TemporaryDirectory() as directory:
            runtime = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            runtime.observe(creator_profile_id=7)
            engine = FakeDecisionEngine(
                engine_result(
                    response="Suggested reply",
                    send_offer=True,
                    offer={
                        "offer_type": "premium",
                        "content": {"fanvue_link": FANVUE_LINK},
                    },
                    telegram_delivery_payload={
                        "delivery_type": "FREE",
                        "message_text": "Here",
                    },
                )
            )
            gateway = ConversationGateway(
                engine,
                allowed_fanvue_hostnames=[FANVUE_HOST],
                runtime_control_service=runtime,
                creator_profile_id=7,
            )

            output = gateway.execute(gateway_input(message_text="Do you have pics?"))
            snapshot = runtime.build_snapshot(creator_profile_id=7)

            self.assertTrue(output.blocked)
            self.assertEqual(output.error_code, "runtime_observe_mode")
            self.assertEqual(output.response_text, "")
            self.assertFalse(output.offer_authorized)
            self.assertEqual(output.delivery_payload, {})
            self.assertEqual(len(engine.calls), 1)
            self.assertEqual(len(snapshot.observed_recommendations), 1)
            self.assertEqual(
                snapshot.observed_recommendations[0].suggested_reply,
                "Suggested reply",
            )

    def test_live_runtime_executes_normally(self):
        with TemporaryDirectory() as directory:
            runtime = RuntimeControlService(
                repository=RuntimeControlRepository(f"{directory}/runtime.json")
            )
            runtime.start(creator_profile_id=7)
            engine = FakeDecisionEngine(engine_result(response="Live reply"))
            gateway = ConversationGateway(
                engine,
                allowed_fanvue_hostnames=[FANVUE_HOST],
                runtime_control_service=runtime,
                creator_profile_id=7,
            )

            output = gateway.execute(gateway_input())

            self.assertFalse(output.blocked)
            self.assertEqual(output.response_text, "Live reply")
            self.assertEqual(len(engine.calls), 1)
            self.assertEqual(
                runtime.build_snapshot(creator_profile_id=7).active_conversations,
                1,
            )

    def test_valid_response_is_normalized_and_diagnostics_are_safe(self):
        engine = FakeDecisionEngine(engine_result())

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertEqual(output.response_text, "Hey you")
        self.assertFalse(output.offer_authorized)
        self.assertIsNone(output.offer_link)
        self.assertFalse(output.blocked)
        self.assertIsNone(output.error_code)
        self.assertEqual(output.diagnostic_metadata["status"], "ok")
        self.assertNotIn("token", output.diagnostic_metadata["route"])

    def test_engine_is_called_once_with_opaque_negative_key_and_history(self):
        engine = FakeDecisionEngine(engine_result())
        history = [{"role": "user", "content": "one"}]
        request = gateway_input(
            engine_user_id="1:-123456789",
            chat_history=history,
            correlation_id="keep-me",
        )

        output = self.build_gateway(engine).execute(request)

        self.assertEqual(len(engine.calls), 1)
        self.assertEqual(engine.calls[0]["user_id"], "1:-123456789")
        self.assertIs(engine.calls[0]["chat_history"], history)
        self.assertEqual(output.correlation_id, "keep-me")

    def test_optional_telegram_commerce_service_owns_orchestration(self):
        engine = FakeDecisionEngine(engine_result(response="direct engine"))
        commerce = FakeTelegramCommerceService(
            engine_result(response="commerce engine")
        )
        gateway = ConversationGateway(
            engine,
            allowed_fanvue_hostnames=[FANVUE_HOST],
            telegram_commerce_service=commerce,
        )
        request = gateway_input()

        output = gateway.execute(request)

        self.assertEqual(output.response_text, "commerce engine")
        self.assertEqual(engine.calls, [])
        self.assertEqual(len(commerce.calls), 1)
        self.assertEqual(commerce.calls[0]["user_id"], request.engine_user_id)
        self.assertIs(commerce.calls[0]["chat_history"], request.chat_history)

    def test_telegram_delivery_payload_passes_through_gateway(self):
        engine = FakeDecisionEngine(
            engine_result(
                telegram_delivery_payload={
                    "delivery_type": "FREE",
                    "message_text": "Here",
                    "asset_path": "C:/vault/free.jpg",
                    "next_suggested_action": "deliver_free_asset",
                    "token": "must-not-leak",
                }
            )
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertEqual(output.delivery_payload["delivery_type"], "FREE")
        self.assertEqual(output.delivery_payload["asset_path"], "C:/vault/free.jpg")
        self.assertNotIn("token", output.delivery_payload)
        self.assertTrue(
            output.diagnostic_metadata["telegram_delivery_payload_ready"]
        )

    def test_unauthorized_offer_suppresses_selected_link(self):
        engine = FakeDecisionEngine(
            engine_result(
                send_offer=False,
                offer={
                    "offer_type": "premium",
                    "content": {"fanvue_link": FANVUE_LINK},
                },
            )
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertFalse(output.offer_authorized)
        self.assertIsNone(output.offer_link)

    def test_authorized_engine_selected_fanvue_link_is_returned(self):
        engine = FakeDecisionEngine(
            engine_result(
                send_offer=True,
                offer={
                    "offer_type": "premium",
                    "delivery_type": "PAID",
                    "delivery_permission_mode": "paid",
                    "delivery_requires_payment": True,
                    "content": {
                        "fanvue_link": FANVUE_LINK,
                        "delivery_type": "PAID",
                        "delivery_permission_mode": "paid",
                        "delivery_requires_payment": True,
                    },
                },
            )
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertTrue(output.offer_authorized)
        self.assertEqual(output.offer_link, FANVUE_LINK)
        self.assertEqual(output.delivery_type, "PAID")
        self.assertEqual(output.delivery_mode, "paid")
        self.assertTrue(output.delivery_requires_payment)

    def test_free_delivery_uses_permission_without_checkout_link(self):
        engine = FakeDecisionEngine(
            engine_result(
                send_offer=True,
                offer={
                    "offer_type": "tease",
                    "delivery_type": "FREE",
                    "delivery_permission_mode": "included",
                    "delivery_requires_payment": False,
                    "content": {
                        "fanvue_link": FANVUE_LINK,
                        "delivery_type": "FREE",
                        "delivery_permission_mode": "included",
                        "delivery_requires_payment": False,
                    },
                },
            )
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertTrue(output.offer_authorized)
        self.assertIsNone(output.offer_link)
        self.assertEqual(output.delivery_type, "FREE")
        self.assertEqual(output.delivery_mode, "included")
        self.assertFalse(output.delivery_requires_payment)
        self.assertEqual(
            output.diagnostic_metadata["delivery_mode"],
            "included",
        )

    def test_unapproved_links_are_rejected(self):
        rejected_links = (
            "http://share.fanvue.com/ava/offer-1",
            "https://evil.example/offer-1",
            "https://share.fanvue.com.evil.example/offer-1",
            "https://share.fanvue.com:444/offer-1",
            "https://user:pass@share.fanvue.com/offer-1",
            "https://share.fanvue.com/bad link",
            "not a url",
        )

        for link in rejected_links:
            with self.subTest(link=link):
                engine = FakeDecisionEngine(
                    engine_result(
                        send_offer=True,
                        offer={
                            "offer_type": "premium",
                            "content": {"fanvue_link": link},
                        },
                    )
                )
                output = self.build_gateway(engine).execute(gateway_input())
                self.assertTrue(output.offer_authorized)
                self.assertIsNone(output.offer_link)

    def test_user_response_and_history_urls_are_never_extracted(self):
        engine = FakeDecisionEngine(
            engine_result(
                response=f"Try {FANVUE_LINK}",
                send_offer=True,
                offer={"offer_type": "premium", "content": None},
            )
        )
        request = gateway_input(
            message_text=FANVUE_LINK,
            chat_history=[{"text": FANVUE_LINK}],
        )

        output = self.build_gateway(engine).execute(request)

        self.assertTrue(output.offer_authorized)
        self.assertIsNone(output.offer_link)

    def test_blocked_result_is_normalized_and_cannot_authorize_offer(self):
        engine = FakeDecisionEngine(
            engine_result(
                response="Cannot respond",
                blocked=True,
                error="creator_profile_required",
                send_offer=True,
                offer={
                    "offer_type": "premium",
                    "content": {"fanvue_link": FANVUE_LINK},
                },
            )
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertTrue(output.blocked)
        self.assertEqual(output.error_code, "creator_profile_required")
        self.assertFalse(output.offer_authorized)
        self.assertIsNone(output.offer_link)

    def test_none_result_is_normalized_without_retry(self):
        engine = FakeDecisionEngine(None)

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertEqual(len(engine.calls), 1)
        self.assertTrue(output.blocked)
        self.assertEqual(output.error_code, "decision_engine_no_result")

    def test_malformed_results_are_normalized_without_retry(self):
        for result in ("bad", {}, {"response": 123}):
            with self.subTest(result=result):
                engine = FakeDecisionEngine(result)
                output = self.build_gateway(engine).execute(gateway_input())
                self.assertEqual(len(engine.calls), 1)
                self.assertTrue(output.blocked)
                self.assertEqual(
                    output.error_code,
                    "decision_engine_malformed_result",
                )

    def test_exception_is_normalized_without_retry_or_message_leak(self):
        engine = FakeDecisionEngine(
            error=RuntimeError("secret failure detail")
        )

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertEqual(len(engine.calls), 1)
        self.assertTrue(output.blocked)
        self.assertEqual(output.error_code, "decision_engine_exception")
        self.assertEqual(
            output.diagnostic_metadata["exception_type"],
            "RuntimeError",
        )
        self.assertNotIn("secret", str(output.diagnostic_metadata))

    def test_timeout_is_normalized_without_retry(self):
        engine = FakeDecisionEngine(error=TimeoutError("too slow"))

        output = self.build_gateway(engine).execute(gateway_input())

        self.assertEqual(len(engine.calls), 1)
        self.assertTrue(output.blocked)
        self.assertEqual(output.error_code, "decision_engine_timeout")
        self.assertEqual(
            output.diagnostic_metadata["status"],
            "engine_timeout",
        )

    def test_invalid_input_does_not_invoke_engine(self):
        engine = FakeDecisionEngine(engine_result())
        request = gateway_input(message_text="")

        output = self.build_gateway(engine).execute(request)

        self.assertEqual(engine.calls, [])
        self.assertEqual(output.error_code, "invalid_message_text")

    def test_gateway_modules_have_no_forbidden_imports(self):
        root = Path(__file__).resolve().parents[1]
        files = (
            root / "app" / "models" / "conversation_gateway.py",
            root / "app" / "services" / "conversation_gateway.py",
        )
        forbidden_roots = {
            "telegram",
            "telethon",
            "aiogram",
            "kviqa",
        }
        forbidden_modules = {
            "app.services.fanvue_api_service",
            "app.services.fanvue_message_sync_service",
            "app.services.fanvue_oauth_service",
        }

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
                    self.assertNotIn(module.split(".")[0], forbidden_roots)
                    self.assertNotIn(module, forbidden_modules)


if __name__ == "__main__":
    unittest.main()
