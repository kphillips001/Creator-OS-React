import ast
import asyncio
import inspect
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.integrations.telegram.telethon_runtime import (
    TelethonRuntime,
    TelethonRuntimeError,
    build_default_runtime_from_environment,
)
from app.models.telegram_inbound import TelegramInboundAttachment, TelegramInboundPayload, TelegramInboundResult
from app.services.conversation_gateway import ConversationGateway
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter
from app.services.telegram_delivery_executor import (
    TelegramDeliveryExecutionResult,
    TelegramDeliveryExecutor,
)
from app.services.telegram_response_pacing_service import TelegramResponsePacingDecision


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

    async def download_inbound_attachment(self, *_args, **_kwargs):
        return b""


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


class AllowMediaScope:
    def decide(self, **_):
        return SimpleNamespace(allowed=True, reason="TEST", mode="TEST")
    def audit_metadata(self):
        return {}


class BlockMediaScope:
    def decide(self, **_):
        return SimpleNamespace(allowed=False, reason="CONTROLLED_SCOPE_NOT_AUTHORIZED", mode="ONLY_CONTROLLED_IDENTITY")
    def audit_metadata(self):
        return {}


class TelethonRuntimeTests(unittest.IsolatedAsyncioTestCase):
    async def test_availability_loop_releases_due_generated_send_retry(self):
        payload=TelegramInboundPayload(telegram_user_id=1,telegram_chat_id=2,
            message_text="retry",message_id=3)
        class Replies:
            def pending_backlog_payloads(self): return []
            def due_availability_payloads(self,*,now): return []
            def due_generated_send_payloads(self,*,now): return [payload]
        class Safety:
            behavior_config={"global_automation_enabled":True,"global_sends_enabled":True}
            def refresh(self): return None
        runtime=TelethonRuntime(transport=FakeTransport(),inbound_adapter=SimpleNamespace(),
            heartbeat_service=FakeHeartbeat(),ordinary_reply_service=Replies(),
            global_safety_service=Safety())
        runtime._transport_connected=True
        runtime._resume_available_payload=AsyncMock(return_value=None)
        with self.assertRaises(asyncio.TimeoutError):
            await asyncio.wait_for(runtime._availability_loop(),timeout=.05)
        runtime._resume_available_payload.assert_awaited_once_with(payload)

    async def test_blocked_captioned_image_uses_text_only_path_before_media_persistence(self):
        class Adapter:
            _creator_profile_id=2;_fanvue_account_id=2
            def __init__(self): self.calls=[]
            def execute(self,payload,*,observe_only=False):
                self.calls.append((payload,observe_only))
                return TelegramInboundResult(correlation_id="caption",telegram_chat_id=2,
                    telegram_user_id=1,message_id=3,engine_user_id="2:-1",response_text="",
                    offer_authorized=False,offer_link=None,blocked=False,error_code=None)
        class Media:
            async def process(self,**_): raise AssertionError("blocked media must not persist")
        adapter=Adapter()
        runtime=TelethonRuntime(transport=FakeTransport(),inbound_adapter=adapter,
            heartbeat_service=FakeHeartbeat(),inbound_media_service=Media(),
            media_processing_scope_service=BlockMediaScope(),
            global_safety_service=type("Allowed",(),{"check_global_safety":lambda self:{"allowed":True}})())
        item=TelegramInboundAttachment(attachment_id="a",telegram_message_id=3,
            telegram_chat_id=2,telegram_user_id=1,media_kind="PHOTO",telegram_media_id="9")
        await runtime._handle_payload_observed(TelegramInboundPayload(telegram_user_id=1,
            telegram_chat_id=2,message_text="How's your day?",message_id=3,attachments=(item,)))
        self.assertEqual(len(adapter.calls),1)
        self.assertEqual(adapter.calls[0][0].message_text,"How's your day?")
        self.assertEqual(adapter.calls[0][0].attachments,())

    async def test_blocked_media_only_and_album_create_nothing_and_send_nothing(self):
        class Adapter:
            _creator_profile_id=2;_fanvue_account_id=2
            def execute(self,*_,**__): raise AssertionError("media-only must retain historical silence")
        class Media:
            async def process(self,**_): raise AssertionError("blocked media must not persist")
        transport=FakeTransport()
        runtime=TelethonRuntime(transport=transport,inbound_adapter=Adapter(),
            heartbeat_service=FakeHeartbeat(),inbound_media_service=Media(),
            media_processing_scope_service=BlockMediaScope())
        items=tuple(TelegramInboundAttachment(attachment_id=str(i),telegram_message_id=i,
            telegram_chat_id=2,telegram_user_id=1,media_kind="PHOTO",telegram_media_id=str(i),grouped_id="g") for i in (3,4))
        self.assertIsNone(await runtime._handle_payload_observed(TelegramInboundPayload(
            telegram_user_id=1,telegram_chat_id=2,message_text="",message_id=3,attachments=items)))
        self.assertEqual(transport.sent,[])

    async def test_ordinary_text_bypasses_media_scope_and_remains_unchanged(self):
        class Adapter:
            _creator_profile_id=2;_fanvue_account_id=2
            def __init__(self): self.calls=[]
            def execute(self,payload,*,observe_only=False):
                self.calls.append(payload)
                return TelegramInboundResult(correlation_id="text",telegram_chat_id=2,
                    telegram_user_id=1,message_id=3,engine_user_id="2:-1",response_text="",
                    offer_authorized=False,offer_link=None,blocked=False,error_code=None)
        adapter=Adapter()
        runtime=TelethonRuntime(transport=FakeTransport(),inbound_adapter=adapter,
            heartbeat_service=FakeHeartbeat(),media_processing_scope_service=BlockMediaScope(),
            global_safety_service=type("Allowed",(),{"check_global_safety":lambda self:{"allowed":True}})())
        await runtime._handle_payload_observed(TelegramInboundPayload(
            telegram_user_id=1,telegram_chat_id=2,message_text="hello",message_id=3))
        self.assertEqual(adapter.calls[0].message_text,"hello")

    async def test_media_turn_persists_and_observes_without_generation_or_send(self):
        class Adapter:
            _creator_profile_id=2
            _fanvue_account_id=2
            def __init__(self): self.calls=[]
            def execute(self,payload,*,observe_only=False):
                self.calls.append((payload,observe_only))
                return TelegramInboundResult(correlation_id="media",telegram_chat_id=2,telegram_user_id=1,message_id=3,engine_user_id="2:-1",response_text="",offer_authorized=False,offer_link=None,blocked=True,error_code="GLOBAL_AUTOMATION_DISABLED")
        class Media:
            def __init__(self): self.calls=[]
            async def process(self,**values): self.calls.append(values);return {"operation_id":"op","state":"READY_FOR_ANALYSIS"}
        class ImageSafety:
            def __init__(self): self.calls=[]
            async def process_operation(self,operation,**context):self.calls.append((operation,context));return {"policy":"POLITE_EXPLICIT_BOUNDARY","generation_allowed":False}
        adapter=Adapter();media=Media();image_safety=ImageSafety();transport=FakeTransport()
        runtime=TelethonRuntime(transport=transport,inbound_adapter=adapter,heartbeat_service=FakeHeartbeat(),inbound_media_service=media,inbound_image_safety_service=image_safety,media_processing_scope_service=AllowMediaScope())
        runtime._image_response_enabled=False
        item=TelegramInboundAttachment(attachment_id="00000000-0000-0000-0000-000000000001",telegram_message_id=3,telegram_chat_id=2,telegram_user_id=1,media_kind="PHOTO",telegram_media_id="9")
        await runtime._handle_payload_observed(TelegramInboundPayload(telegram_user_id=1,telegram_chat_id=2,message_text="",message_id=3,attachments=(item,)))
        self.assertEqual(len(media.calls),1)
        self.assertEqual(len(image_safety.calls),1)
        self.assertTrue(adapter.calls[0][1])
        self.assertEqual(transport.sent,[])

    async def test_enabled_media_response_rechecks_authority_then_uses_one_logical_turn(self):
        class Adapter:
            _creator_profile_id=2;_fanvue_account_id=2
            def __init__(self):self.calls=[]
            def execute(self,payload,*,observe_only=False):
                self.calls.append((payload,observe_only))
                return TelegramInboundResult(correlation_id='media',telegram_chat_id=2,
                  telegram_user_id=1,message_id=payload.message_id,engine_user_id='2:-1',
                  response_text='',offer_authorized=False,offer_link=None,blocked=True,
                  error_code='RELATIONSHIP_HUMAN_OPERATOR_ACTIVE')
        class Media:
            async def process(self,**_):return {'operation_id':'op','state':'READY_FOR_ANALYSIS'}
        class ImageSafety:
            async def process_operation(self,*_,**__):return SimpleNamespace(policy=SimpleNamespace(value='SELFIE_COMPLIMENT_ELIGIBLE'))
            async def response_context(self,*_):return {'operation_id':'op','response_policy':'SELFIE_COMPLIMENT_ELIGIBLE'}
        allowed=type('Allowed',(),{'check_global_safety':lambda self:{'allowed':True}})()
        adapter=Adapter();transport=FakeTransport()
        with patch.dict('os.environ',{'TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED':'true'}):
            runtime=TelethonRuntime(transport=transport,inbound_adapter=adapter,
              heartbeat_service=FakeHeartbeat(),inbound_media_service=Media(),
              inbound_image_safety_service=ImageSafety(),global_safety_service=allowed,
              media_processing_scope_service=AllowMediaScope())
        items=tuple(TelegramInboundAttachment(attachment_id=str(i),telegram_message_id=i,
          telegram_chat_id=2,telegram_user_id=1,media_kind='PHOTO',telegram_media_id=str(i),grouped_id='g') for i in (9,8))
        result=await runtime._handle_payload_observed(TelegramInboundPayload(
          telegram_user_id=1,telegram_chat_id=2,message_text='',message_id=9,attachments=items))
        self.assertEqual(result.error_code,'RELATIONSHIP_HUMAN_OPERATOR_ACTIVE')
        self.assertEqual(adapter.calls[0][0].message_id,8)
        self.assertFalse(adapter.calls[0][1])
        self.assertEqual(transport.sent,[])

    async def test_existing_pacing_wait_is_overlaid_with_native_typing_once(self):
        events = []

        class Transport(FakeTransport):
            async def show_typing_while(self, *, chat_id, operation, **_context):
                events.append(("typing_start", chat_id))
                await operation
                events.append(("typing_stop", chat_id))

        class Pacing:
            async def wait(self, decision):
                events.append(("pacing_wait", decision.applied_delay_ms))

        runtime = TelethonRuntime(
            transport=Transport(), inbound_adapter=object(),
            response_pacing_service=Pacing(),
        )
        await runtime._wait_with_typing(
            chat_id=123456789,
            decision=TelegramResponsePacingDecision(
                mode="APPLIED", policy="AVA_PRIVATE_CHAT_HUMANIZED_V1",
                calculated_delay_ms=2500, applied_delay_ms=2500,
                reason="test",
            ),
        )

        self.assertEqual(events, [
            ("typing_start", 123456789),
            ("pacing_wait", 2500),
            ("typing_stop", 123456789),
        ])

    async def test_short_certified_pacing_gets_two_second_visible_typing_floor(self):
        events = []

        class Transport(FakeTransport):
            async def show_typing_while(self, *, operation, **_context):
                await operation

        class Pacing:
            async def wait(self, decision):
                events.append(decision.applied_delay_ms)

        runtime = TelethonRuntime(
            transport=Transport(), inbound_adapter=object(),
            response_pacing_service=Pacing(),
        )
        await runtime._wait_with_typing(
            chat_id=123456789,
            decision=TelegramResponsePacingDecision(
                mode="APPLIED", policy="AVA_PRIVATE_CHAT_HUMANIZED_V1",
                calculated_delay_ms=1428, applied_delay_ms=1428, reason="test",
            ),
        )
        self.assertEqual(events, [2000])

    async def test_three_second_pacing_is_not_extended(self):
        events = []

        class Transport(FakeTransport):
            async def show_typing_while(self, *, operation, **_context):
                await operation

        class Pacing:
            async def wait(self, decision):
                events.append(decision.applied_delay_ms)

        runtime = TelethonRuntime(
            transport=Transport(), inbound_adapter=object(),
            response_pacing_service=Pacing(),
        )
        await runtime._wait_with_typing(
            chat_id=123456789,
            decision=TelegramResponsePacingDecision(
                mode="APPLIED", policy="AVA_PRIVATE_CHAT_HUMANIZED_V1",
                calculated_delay_ms=3000, applied_delay_ms=3000, reason="test",
            ),
        )
        self.assertEqual(events, [3000])

    async def test_zero_delay_bypass_does_not_publish_typing(self):
        events = []

        class Transport(FakeTransport):
            async def show_typing_while(self, **_kwargs):
                events.append("typing")

        class Pacing:
            async def wait(self, decision):
                events.append(("wait", decision.applied_delay_ms))

        runtime = TelethonRuntime(
            transport=Transport(), inbound_adapter=object(),
            response_pacing_service=Pacing(),
        )
        await runtime._wait_with_typing(
            chat_id=123456789,
            decision=TelegramResponsePacingDecision(
                mode="SHADOW", policy="AVA_PRIVATE_CHAT_HUMANIZED_V1",
                calculated_delay_ms=2500, applied_delay_ms=0,
                reason="test", bypass_reason="SHADOW_MODE",
            ),
        )

        self.assertEqual(events, [("wait", 0)])

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

    async def test_disabled_replies_observe_inbound_without_gateway_or_send(self):
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
            self.assertLogs("telethon-runtime", level="INFO") as logs,
        ):
            result = await runtime.handle_payload(payload)

        self.assertTrue(result.blocked)
        self.assertEqual(result.error_code, "GLOBAL_AUTOMATION_DISABLED")
        self.assertTrue(result.diagnostic_metadata["observation_only"])
        self.assertEqual(result.diagnostic_metadata["ai_generation_count"], 0)
        self.assertEqual(engine.calls, [])
        self.assertEqual(transport.sent, [])
        self.assertIn(
            "[TELEGRAM PAUSED] inbound message observed without automation "
            "chat_id=123456789 user_id=123456789",
            "\n".join(logs.output),
        )

    async def test_global_automation_off_observes_once_without_generation_or_send(self):
        runtime, transport, engine = self.build_runtime()
        class Prospects:
            def __init__(self): self.calls = []
            def observe(self, **values):
                self.calls.append(values)
                return type("Prospect", (), {"relationship_state": {}})()
        prospects = Prospects()
        runtime._inbound_adapter._creator_profile_id = 2
        runtime._inbound_adapter._fanvue_account_id = 7
        runtime._inbound_adapter._unmapped_prospects = prospects
        runtime._global_safety_service = type(
            "BlockedSafety", (), {"check_global_safety": lambda self: {
                "allowed": False, "reason": "global_automation_disabled"}}
        )()
        payload = TelegramInboundPayload(
            telegram_user_id=123456789, telegram_chat_id=123456789,
            message_text="observe me", message_id=43,
        )
        with patch.dict("os.environ", {
            "TELEGRAM_REPLIES_ENABLED": "true",
            "CONTROLLED_AUTONOMY_TEST_ENABLED": "false",
        }, clear=False):
            result = await runtime.handle_payload(payload)
        self.assertTrue(result.diagnostic_metadata["durable_inbound_observed"])
        self.assertEqual(len(prospects.calls), 1)
        self.assertEqual(result.diagnostic_metadata["ai_generation_count"], 0)
        self.assertEqual(result.diagnostic_metadata["commercial_execution_count"], 0)
        self.assertEqual(engine.calls, [])
        self.assertEqual(transport.sent, [])

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

    async def test_ignored_inbound_is_captured_then_stops_before_media_memory_and_generation(self):
        class Controls:
            HOLD_REASON="RELATIONSHIP_HUMAN_OPERATOR_ACTIVE"
            def autonomous_allowed(self, **_):
                return False, SimpleNamespace(ignored=True)
        class Adapter:
            _creator_profile_id=2;_fanvue_account_id=3;_relationship_controls=Controls()
            def execute(self, *_args, **_kwargs):
                raise AssertionError("ignored inbound must not enter the gateway")
        class Backlog:
            def __init__(self): self.items=[]
            def capture(self,payload,**_): self.items.append(payload)
        operation=SimpleNamespace(operation_id="ignored-op")
        class Replies:
            def __init__(self): self.suppressed=[]
            def begin(self,_payload): return operation,True
            def suppress_ignored(self,item): self.suppressed.append(item.operation_id)
        class Media:
            async def process(self,**_):
                raise AssertionError("ignored media must not be downloaded or classified")
        class Safety:
            behavior_config={"global_automation_enabled":True}
            def refresh(self): return None
            def check_global_safety(self): return {"allowed":True}
        backlog=Backlog();replies=Replies()
        runtime=TelethonRuntime(transport=FakeTransport(),inbound_adapter=Adapter(),
            heartbeat_service=FakeHeartbeat(),private_inbound_backlog_service=backlog,
            ordinary_reply_service=replies,inbound_media_service=Media(),
            media_processing_scope_service=AllowMediaScope(),global_safety_service=Safety())
        attachment=TelegramInboundAttachment(attachment_id="a",telegram_message_id=3,
            telegram_chat_id=2,telegram_user_id=1,media_kind="PHOTO",telegram_media_id="9")
        result=await runtime._handle_payload_observed(TelegramInboundPayload(
            telegram_user_id=1,telegram_chat_id=2,message_text="price?",message_id=3,
            attachments=(attachment,)))
        self.assertIsNone(result)
        self.assertEqual(len(backlog.items),1)
        self.assertEqual(replies.suppressed,["ignored-op"])


async def _async_result(value):
    return value


if __name__ == "__main__":
    unittest.main()
