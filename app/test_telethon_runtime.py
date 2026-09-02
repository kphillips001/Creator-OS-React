import ast
import inspect
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from app.integrations.telegram.telethon_runtime import (
    TelethonRuntime,
    TelethonRuntimeError,
    build_default_runtime_from_environment,
)
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.services.telegram_delivery_executor import (
    TelegramDeliveryExecutionResult,
    TelegramDeliveryExecutor,
)


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


class FakeHeartbeat:
    def now(self): return datetime.now(timezone.utc)
    def register_startup(self): return None
    def heartbeat(self, **_): return None
    def record_poll(self): return None
    def record_success(self, **_): return None
    def record_failure(self, _): return None
    def record_terminal_failure(self, _, **__): return None
    def record_stopping(self): return None
    def record_shutdown(self): return None


class TelethonRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_unmapped_commercial_turn_uses_durable_reply_and_confirms_intent(self):
        result = TelegramInboundResult(
            correlation_id="telegram:7857064998:5459",
            telegram_chat_id=7857064998,
            telegram_user_id=7857064998,
            message_id=5459,
            engine_user_id="telegram:7857064998",
            response_text="Okay, here you go.",
            offer_authorized=True,
            offer_link=None,
            blocked=False,
            error_code=None,
            delivery_type="SINGLE_IMAGE",
            delivery_mode="unlock_gateway",
            delivery_requires_payment=True,
            delivery_payload={"message_text": "Okay, here you go.", "metadata": {}},
            diagnostic_metadata={
                "final_offer_authorized": True,
                "telegram_identity_eligibility": "UNMAPPED_BOOTSTRAP",
                "paid_presentation_validated": True,
            },
        )
        inbound = type(
            "Inbound", (), {"execute": lambda self, _payload: result}
        )()
        operation = type("Operation", (), {
            "operation_id": "ordinary-op",
            "correlation_id": "ordinary_reply:AVA_TELETHON_PRIVATE:7857064998:5459",
            "state": type("State", (), {"value": "RECEIVED"})(),
            "response_payload": None,
        })()

        class OrdinaryReplies:
            def __init__(self):
                self.stored = None
                self.confirmed_id = None
            def begin(self, _payload): return operation, self.stored is None
            def result(self, _operation): return self.stored
            def claim_generation(self, _operation): return operation
            def generated(self, _operation, generated):
                self.stored = generated
                operation.state = type("State", (), {"value": "GENERATED"})()
                return operation
            def enrich_commercial(self, _operation, enriched, intent):
                enriched.diagnostic_metadata["purchase_intent_id"] = str(
                    intent.purchase_intent_id
                )
                self.stored = enriched
                return operation
            def claim_send(self, _operation):
                operation.state = type("State", (), {"value": "SENDING"})()
                return operation
            def confirmed(self, _operation, message_id):
                self.confirmed_id = message_id
                operation.outbound_telegram_message_id = message_id
                operation.state = type("State", (), {"value": "SENT_CONFIRMED"})()
                return operation
            def suppress_commercial(self, _operation):
                raise AssertionError("unmapped durable operation must not be suppressed")

        intent = type("Intent", (), {
            "purchase_intent_id": "intent-1",
            "creator_profile_id": 2,
            "commercial_offering_id": "offering-1",
            "commercial_publication_id": "publication-1",
        })()

        class Purchases:
            def __init__(self):
                self.create_calls = 0
                self.confirmed = []
            def create_before_delivery(self, generated, _payload):
                self.create_calls += 1
                generated.delivery_payload["media_link"] = "https://creator.example/unlock"
                generated.delivery_payload["metadata"]["private_chat_unlock_button"] = {
                    "label": "Unlock", "url": "https://creator.example/unlock",
                }
                return intent
            def confirm_delivery(self, received, **values):
                self.confirmed.append((received, values["telegram_message_id"]))

        class SalesDeliveries:
            def get(self, _correlation): return None
            def prepare(self, **values):
                return __import__(
                    "app.services.telegram_sales_delivery_service",
                    fromlist=["TelegramSalesDeliveryService"],
                ).TelegramSalesDeliveryService().prepare(**values)

        delivered = []

        class Delivery:
            async def execute_async(self, payload, **_kwargs):
                delivered.append(dict(payload))
                return TelegramDeliveryExecutionResult(
                    status="SENT", executed=True,
                    metadata={
                        "telegram_message_id": 9901,
                        "actionable_destination_attached": True,
                        "provider_action_verified": True,
                        "provider_markup_included": True,
                        "provider_markup_verified": True,
                        "customer_facing_destination_valid": True,
                    },
                )

        replies = OrdinaryReplies()
        purchases = Purchases()
        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=Delivery(), ordinary_reply_service=replies,
            purchase_intent_service=purchases,
            sales_delivery_service=SalesDeliveries(),
            global_safety_service=type("Safety", (), {
                "check_global_safety": lambda self: {"allowed": True},
            })(),
        )
        payload = TelegramInboundPayload(
            telegram_user_id=7857064998,
            telegram_chat_id=7857064998,
            message_text="Okay then, show me",
            message_id=5459,
        )
        await runtime.handle_payload(payload)
        await runtime.handle_payload(payload)

        self.assertEqual(len(delivered), 1)
        self.assertEqual(
            delivered[0]["metadata"]["private_chat_unlock_button"]["url"],
            "https://creator.example/unlock",
        )
        self.assertEqual(replies.confirmed_id, 9901)
        self.assertEqual(purchases.confirmed, [(intent, 9901)])

    async def test_accepted_offer_is_recovered_after_confirmation_crash_without_resend(self):
        result = TelegramInboundResult(
            correlation_id="telegram:12:56", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:34",
            response_text="Offer", offer_authorized=True,
            offer_link="https://fanvue.com/example", blocked=False,
            error_code=None, delivery_payload={"message_text": "Offer"},
            diagnostic_metadata={"final_offer_authorized": True},
        )
        inbound = type("Inbound", (), {"execute": lambda self, _: result})()
        sends = []

        class Delivery:
            async def execute_async(self, *_args, **_kwargs):
                sends.append("sent")
                return TelegramDeliveryExecutionResult(
                    status="SENT", executed=True,
                    metadata={"telegram_message_id": 901},
                )

        class SalesDeliveries:
            def __init__(self):
                self.operation = None
                self.confirm_attempts = 0
            def get(self, _): return self.operation
            def prepare(self, **_):
                self.operation = type("Operation", (), {
                    "state": type("State", (), {"value": "CREATED"})(),
                    "operation_id": "op", "purchase_intent_id": "intent",
                })()
                return self.operation, True
            def claim(self, operation):
                operation.state = type("State", (), {"value": "SENDING"})()
                return operation
            def accepted(self, operation, message_id):
                self.events.append(("accepted", message_id))
                operation.state = type("State", (), {"value": "TELEGRAM_ACCEPTED"})()
                return operation
            def confirm(self, operation):
                self.confirm_attempts += 1
                if self.confirm_attempts == 1:
                    raise RuntimeError("simulated crash after acceptance persistence")
                self.events.append(("confirmed", operation.operation_id))
            events = []

        class Purchases:
            def create_before_delivery(self, *_):
                return type("Intent", (), {
                    "purchase_intent_id": "intent", "creator_profile_id": 3,
                    "commercial_offering_id": "offering",
                    "commercial_publication_id": "publication",
                })()
            def get(self, _): return None

        sales = SalesDeliveries()
        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=Delivery(), purchase_intent_service=Purchases(),
            sales_delivery_service=sales,
            global_safety_service=type("Safety", (), {
                "check_global_safety": lambda self: {"allowed": True}
            })(),
        )
        payload = TelegramInboundPayload(
            telegram_user_id=34, telegram_chat_id=12,
            message_text="show me", message_id=56,
        )
        self.assertIsNone(await runtime.handle_payload(payload))
        self.assertEqual(sends, ["sent"])
        await runtime.handle_payload(payload)
        self.assertEqual(sends, ["sent"])
        self.assertEqual(sales.events, [("accepted", 901), ("confirmed", "op")])

    async def test_outbound_transcript_is_saved_only_after_confirmed_send(self):
        saved = []
        diagnostics = {
            "conversation_thread_id": 77,
            "conversation_fanvue_account_id": 2,
            "conversation_fanvue_user_id": 9,
        }
        result = TelegramInboundResult(
            correlation_id="telegram:12:56", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:-34",
            response_text="Confirmed response", offer_authorized=False,
            offer_link=None, blocked=False, error_code=None,
            delivery_payload={"message_text": "Confirmed response"},
            diagnostic_metadata=diagnostics,
        )
        inbound = type("Inbound", (), {"execute": lambda self, _payload: result})()
        safety = type("Safety", (), {
            "check_global_safety": lambda self: {"allowed": True}
        })()

        for executed, message_id in ((False, None), (True, 901)):
            delivery = type("Delivery", (), {
                "execute_async": lambda self, *_args, _executed=executed,
                _message_id=message_id, **_kwargs: _async_result(
                    TelegramDeliveryExecutionResult(
                        status="SENT" if _executed else "FAILED",
                        executed=_executed,
                        metadata=({"telegram_message_id": _message_id}
                                  if _message_id is not None else {}),
                    )
                )
            })()
            runtime = TelethonRuntime(
                transport=FakeTransport(), inbound_adapter=inbound,
                delivery_executor=delivery, global_safety_service=safety,
                conversation_message_saver=lambda **values: saved.append(values),
            )
            await runtime.handle_payload(TelegramInboundPayload(
                telegram_user_id=34, telegram_chat_id=12,
                message_text="hello", message_id=56,
            ))

        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0]["direction"], "outbound")
        self.assertEqual(saved[0]["text"], "Confirmed response")
        self.assertEqual(saved[0]["raw_payload"]["telegram_message_id"], 901)
        self.assertEqual(saved[0]["thread_id"], 77)

    def test_production_builder_wires_thread_resolver_to_inbound_adapter(self):
        source = inspect.getsource(build_default_runtime_from_environment)
        tree = ast.parse(source)
        calls = {
            node.func.id: node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id in {"TelegramInboundAdapter", "TelethonRuntime"}
        }

        adapter_keywords = {
            keyword.arg: keyword.value for keyword in calls["TelegramInboundAdapter"].keywords
        }
        runtime_keywords = {
            keyword.arg: keyword.value for keyword in calls["TelethonRuntime"].keywords
        }
        resolver = adapter_keywords.get("conversation_thread_resolver")

        self.assertIsInstance(resolver, ast.Name)
        self.assertEqual(resolver.id, "get_or_create_chat_thread")
        self.assertEqual(
            adapter_keywords["conversation_message_saver"].id,
            "save_chat_message",
        )
        self.assertEqual(
            adapter_keywords["conversation_history_loader"].id,
            "get_recent_messages_for_gpt",
        )
        self.assertNotIn("conversation_thread_resolver", runtime_keywords)
        self.assertEqual(
            runtime_keywords["conversation_message_saver"].id,
            "save_chat_message",
        )

    def test_production_worker_composition_wires_conversational_memory(self):
        source = inspect.getsource(build_default_runtime_from_environment)
        tree = ast.parse(source)
        adapter_call = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == "TelegramInboundAdapter"
        )
        keywords = {keyword.arg: keyword.value for keyword in adapter_call.keywords}
        memory = keywords.get("conversational_memory_service")
        self.assertIsInstance(memory, ast.Call)
        self.assertIsInstance(memory.func, ast.Name)
        self.assertEqual(memory.func.id, "ConversationalMemoryService")

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
        safety = type(
            "AllowedSafety",
            (),
            {"check_global_safety": lambda self: {"allowed": True}},
        )()
        runtime = TelethonRuntime(
            transport=transport,
            inbound_adapter=adapter,
            heartbeat_service=FakeHeartbeat(),
            global_safety_service=safety,
            delivery_executor=TelegramDeliveryExecutor(
                global_safety_service=safety
            ),
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
        safety = type(
            "AllowedSafety",
            (),
            {"check_global_safety": lambda self: {"allowed": True}},
        )()
        runtime = TelethonRuntime(
            transport=transport,
            inbound_adapter=adapter,
            global_safety_service=safety,
            delivery_executor=TelegramDeliveryExecutor(
                global_safety_service=safety
            ),
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

        async def intentional_disconnect():
            runtime.request_shutdown("test_complete")

        transport.run_until_disconnected = intentional_disconnect

        await runtime.run()

        self.assertTrue(transport.started)
        self.assertTrue(transport.disconnected)

    async def test_purchase_acknowledgement_is_written_only_after_delivery(self):
        result = TelegramInboundResult(
            correlation_id="correlation-1", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:34",
            response_text="Thank you.", offer_authorized=False,
            offer_link=None, blocked=False, error_code=None,
            delivery_payload={"message_text": "Thank you."},
            diagnostic_metadata={
                "customer_sales_decision": "CONGRATULATE_PURCHASE",
                "purchase_acknowledgement_intent_id": "intent-1",
            },
        )
        inbound = type(
            "Inbound", (), {"execute": lambda self, _payload: result}
        )()
        successful_delivery = type(
            "Delivery", (), {
                "execute_async": lambda self, *_args, **_kwargs:
                    _async_result(TelegramDeliveryExecutionResult(
                        status="SENT", executed=True,
                        metadata={"telegram_message_id": 91},
                    ))
            },
        )()

        class PurchaseIntents:
            def __init__(self):
                self.acknowledged = []

            def create_before_delivery(self, *_args):
                return None

            def confirm_delivery(self, *_args, **_kwargs):
                return None

            def acknowledge_purchase(self, intent_id):
                self.acknowledged.append(intent_id)

        purchases = PurchaseIntents()
        operation = type("Operation", (), {
            "operation_id": "ack-op",
            "correlation_id": "ordinary_reply:AVA_TELETHON_PRIVATE:12:56",
            "state": type("State", (), {"value": "RECEIVED"})(),
            "response_payload": None,
            "outbound_telegram_message_id": None,
        })()

        class OrdinaryReplies:
            def __init__(self):
                self.stored = None
            def begin(self, _payload): return operation, self.stored is None
            def result(self, _operation): return self.stored
            def claim_generation(self, _operation): return operation
            def generated(self, _operation, generated):
                self.stored = generated
                operation.state = type("State", (), {"value": "GENERATED"})()
                return operation
            def claim_send(self, _operation):
                operation.state = type("State", (), {"value": "SENDING"})()
                return operation
            def confirmed(self, _operation, message_id):
                operation.state = type("State", (), {"value": "SENT_CONFIRMED"})()
                return operation

        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=successful_delivery,
            ordinary_reply_service=OrdinaryReplies(),
            global_safety_service=type(
                "Safety", (), {
                    "check_global_safety": lambda self: {"allowed": True}
                },
            )(),
            purchase_intent_service=purchases,
        )
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=34, telegram_chat_id=12,
            message_text="hello", message_id=56,
        ))
        self.assertEqual(purchases.acknowledged, ["intent-1"])
        self.assertEqual(operation.state.value, "SENT_CONFIRMED")

    async def test_failed_delivery_does_not_acknowledge_purchase(self):
        result = TelegramInboundResult(
            correlation_id="correlation-1", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:34",
            response_text="Thank you.", offer_authorized=False,
            offer_link=None, blocked=False, error_code=None,
            delivery_payload={"message_text": "Thank you."},
            diagnostic_metadata={
                "customer_sales_decision": "CONGRATULATE_PURCHASE",
                "purchase_acknowledgement_intent_id": "intent-1",
            },
        )
        inbound = type(
            "Inbound", (), {"execute": lambda self, _payload: result}
        )()
        failed_delivery = type(
            "Delivery", (), {
                "execute_async": lambda self, *_args, **_kwargs:
                    _async_result(TelegramDeliveryExecutionResult(
                        status="FAILED", executed=False,
                    ))
            },
        )()

        class PurchaseIntents:
            acknowledged = []
            abandoned = []

            def create_before_delivery(self, *_args):
                return None

            def abandon_delivery(self, intent):
                self.abandoned.append(intent)

            def acknowledge_purchase(self, intent_id):
                self.acknowledged.append(intent_id)

        purchases = PurchaseIntents()
        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=failed_delivery,
            global_safety_service=type(
                "Safety", (), {
                    "check_global_safety": lambda self: {"allowed": True}
                },
            )(),
            purchase_intent_service=purchases,
        )
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=34, telegram_chat_id=12,
            message_text="hello", message_id=56,
        ))
        self.assertEqual(purchases.acknowledged, [])
        self.assertEqual(purchases.abandoned, [None])

    async def test_bundle_complete_presentation_confirms_one_intent_and_both_events(self):
        result = TelegramInboundResult(
            correlation_id="bundle-correlation", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:34",
            response_text="Natural Bundle copy\n\nBundle — USD 25.00: https://fanvue.com/bundle",
            offer_authorized=True, offer_link="https://fanvue.com/bundle",
            blocked=False, error_code=None,
            delivery_payload={
                "delivery_type": "BUNDLE",
                "message_text": "Natural Bundle copy\n\nBundle — USD 25.00: https://fanvue.com/bundle",
                "asset_path": "C:/test/blurred.png",
                "media_link": "https://fanvue.com/bundle",
                "delivery_method": "free_asset",
                "metadata": {
                    "bundle_complete_presentation": True,
                    "bundle_teaser_delivery": {
                        "lifecycle_id": "lifecycle-1",
                        "photoshoot_session_id": "shoot-1",
                        "asset_id": 90, "source_asset_id": 11,
                    },
                },
            },
            diagnostic_metadata={"final_offer_authorized": True},
        )
        inbound = type("Inbound", (), {"execute": lambda self, _payload: result})()
        successful_delivery = type(
            "Delivery", (), {
                "execute_async": lambda self, *_args, **_kwargs:
                    _async_result(TelegramDeliveryExecutionResult(
                        status="SENT", executed=True, delivery_method="free_asset",
                        metadata={"execution_state": "asset_sent", "telegram_message_id": 91},
                    ))
            },
        )()
        events = []

        class PurchaseIntents:
            def __init__(self):
                self.created = 0

            def create_before_delivery(self, *_args):
                self.created += 1
                return "bundle-intent"

            def confirm_delivery(self, intent, **kwargs):
                events.append(("BUNDLE_OFFER_PRESENTED", intent, kwargs["telegram_message_id"]))

            def abandon_delivery(self, intent):
                events.append(("ABANDONED", intent))

        class Lifecycles:
            def record_bundle_teaser_delivery(self, **kwargs):
                events.append(("BUNDLE_TEASER_PRESENTED", kwargs["asset_id"], kwargs["provider_delivery_id"]))

        purchases = PurchaseIntents()
        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=successful_delivery,
            global_safety_service=type("Safety", (), {
                "check_global_safety": lambda self: {"allowed": True}
            })(),
            purchase_intent_service=purchases,
            photoshoot_lifecycle_service=Lifecycles(),
        )
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=34, telegram_chat_id=12,
            message_text="show me", message_id=56,
        ))
        self.assertEqual(purchases.created, 1)
        self.assertEqual(events, [
            ("BUNDLE_OFFER_PRESENTED", "bundle-intent", 91),
            ("BUNDLE_TEASER_PRESENTED", 90, "91"),
        ])

    async def test_failed_bundle_presentation_is_retryable_not_customer_declined(self):
        result = TelegramInboundResult(
            correlation_id="bundle-failure", telegram_chat_id=12,
            telegram_user_id=34, message_id=56, engine_user_id="2:34",
            response_text="Bundle", offer_authorized=True,
            offer_link="https://fanvue.com/bundle", blocked=False,
            error_code=None,
            delivery_payload={
                "message_text": "Bundle", "asset_path": "C:/test/blurred.png",
                "metadata": {"bundle_complete_presentation": True},
            },
            diagnostic_metadata={"final_offer_authorized": True},
        )
        inbound = type("Inbound", (), {"execute": lambda self, _payload: result})()
        failed_delivery = type("Delivery", (), {
            "execute_async": lambda self, *_args, **_kwargs:
                _async_result(TelegramDeliveryExecutionResult(
                    status="FAILED", executed=False,
                ))
        })()

        class PurchaseIntents:
            failed = []
            abandoned = []
            def create_before_delivery(self, *_args): return "bundle-intent"
            def fail_delivery(self, intent): self.failed.append(intent)
            def abandon_delivery(self, intent): self.abandoned.append(intent)

        purchases = PurchaseIntents()
        runtime = TelethonRuntime(
            transport=FakeTransport(), inbound_adapter=inbound,
            delivery_executor=failed_delivery,
            global_safety_service=type("Safety", (), {
                "check_global_safety": lambda self: {"allowed": True}
            })(), purchase_intent_service=purchases,
        )
        await runtime.handle_payload(TelegramInboundPayload(
            telegram_user_id=34, telegram_chat_id=12,
            message_text="show me", message_id=56,
        ))
        self.assertEqual(purchases.failed, ["bundle-intent"])
        self.assertEqual(purchases.abandoned, [])


async def _async_result(value):
    return value


if __name__ == "__main__":
    unittest.main()
