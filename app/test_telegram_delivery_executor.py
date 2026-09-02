import asyncio
import unittest
from pathlib import Path

from app.models.commerce_execution import (
    RuntimeExecutionAction,
    RuntimeExecutionIntent,
)
from app.models.telegram_commerce import TelegramDeliveryPayload
from app.services.telegram_delivery_executor import TelegramDeliveryExecutor


class AllowingSafetyService:
    def check_global_safety(self):
        return {"allowed": True, "reason": None, "source": "isolated_test"}


class RecordingTextSender:
    def __init__(self):
        self.calls = []

    def send_text(self, *, chat_id, message_text):
        self.calls.append({"chat_id": chat_id, "message_text": message_text})


class AsyncRecordingTextSender:
    def __init__(self):
        self.calls = []

    async def send_text(self, *, chat_id, message_text):
        self.calls.append({"chat_id": chat_id, "message_text": message_text})


class AsyncRecordingAssetSender:
    def __init__(self):
        self.calls = []

    async def send_asset(self, *, chat_id, asset_path, message_text):
        self.calls.append({
            "chat_id": chat_id, "asset_path": asset_path, "message_text": message_text,
        })
        return 778


class VerifiedCommercialSender:
    async def send_text(self, **kwargs):
        return type("Receipt", (), {
            "id": 779,
            "final_text": kwargs["message_text"],
            "actionable_destination_attached": True,
            "provider_action_verified": True,
            "provider_markup_included": True,
            "provider_markup_verified": True,
            "attachment_mode": "TELEGRAM_BUSINESS_INLINE_BUTTON",
        })()


class TelegramDeliveryExecutorTests(unittest.TestCase):
    def test_execute_defers_runtime_transport_for_normalized_payload(self):
        executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())

        result = executor.execute(
            TelegramDeliveryPayload(
                delivery_type="FREE",
                message_text="Here",
                asset_path="C:/vault/free.jpg",
                delivery_method="free_asset",
            ),
            context={
                "correlation_id": "telegram:1:2",
                "engine_user_id": "7:-123456789",
                "token": "must-not-leak",
            },
        )

        self.assertEqual(result.status, "deferred")
        self.assertFalse(result.executed)
        self.assertEqual(result.delivery_method, "free_asset")
        self.assertEqual(
            result.metadata["execution_owner"],
            "TelegramDeliveryExecutor",
        )
        self.assertEqual(
            result.metadata["context"],
            {
                "correlation_id": "telegram:1:2",
                "engine_user_id": "7:-123456789",
            },
        )

    def test_execute_sends_existing_text_capability_through_sender(self):
        sender = RecordingTextSender()
        executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())

        result = executor.execute(
            TelegramDeliveryPayload(
                message_text="Brain result sent",
                delivery_method="text",
            ),
            context={
                "chat_id": 123456789,
                "text_sender": sender,
            },
        )

        self.assertTrue(result.executed)
        self.assertEqual(result.status, "success")
        self.assertEqual(
            sender.calls,
            [{"chat_id": 123456789, "message_text": "Brain result sent"}],
        )
        self.assertEqual(result.metadata["execution_state"], "text_sent")

    def test_execute_accepts_provider_neutral_runtime_intent(self):
        sender = RecordingTextSender()
        executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())

        result = executor.execute(
            RuntimeExecutionIntent(
                actions=(RuntimeExecutionAction.CONTINUE_CONVERSATION,),
                provider="telegram",
                payload=TelegramDeliveryPayload(
                    message_text="Intent text",
                    delivery_method="text",
                ),
            ),
            context={
                "chat_id": 123456789,
                "text_sender": sender,
            },
        )

        self.assertTrue(result.executed)
        self.assertEqual(result.status, "success")
        self.assertEqual(
            sender.calls,
            [{"chat_id": 123456789, "message_text": "Intent text"}],
        )

    def test_execute_async_sends_existing_text_capability(self):
        async def run():
            sender = AsyncRecordingTextSender()
            executor = TelegramDeliveryExecutor(
                global_safety_service=AllowingSafetyService(),
                business_commercial_transport=VerifiedCommercialSender(),
            )

            result = await executor.execute_async(
                TelegramDeliveryPayload(
                    message_text="Async brain result",
                    delivery_method="text",
                ),
                context={
                    "chat_id": 123456789,
                    "transport": sender,
                },
            )

            return result, sender

        result, sender = asyncio.run(run())

        self.assertTrue(result.executed)
        self.assertEqual(result.status, "success")
        self.assertEqual(
            sender.calls,
            [{"chat_id": 123456789, "message_text": "Async brain result"}],
        )

    def test_execute_async_sends_asset_with_conversation_as_caption(self):
        async def run():
            sender = AsyncRecordingAssetSender()
            executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())
            result = await executor.execute_async(
                TelegramDeliveryPayload(
                    delivery_type="FREE", message_text="A little preview for you",
                    asset_path="C:/vault/teaser.jpg", delivery_method="free_asset",
                ),
                context={"chat_id": 123456789, "transport": sender},
            )
            return result, sender

        result, sender = asyncio.run(run())
        self.assertTrue(result.executed)
        self.assertEqual(result.metadata["execution_state"], "asset_sent")
        self.assertEqual(result.metadata["telegram_message_id"], 778)
        self.assertEqual(sender.calls[0]["asset_path"], "C:/vault/teaser.jpg")
        self.assertEqual(sender.calls[0]["message_text"], "A little preview for you")

    def test_execute_async_projects_provider_verified_commercial_action(self):
        async def run():
            executor = TelegramDeliveryExecutor(
                global_safety_service=AllowingSafetyService(),
                business_commercial_transport=VerifiedCommercialSender(),
            )
            return await executor.execute_async(
                TelegramDeliveryPayload(
                    message_text="Here it is - unlock this private one.",
                    delivery_method="text",
                    metadata={"private_chat_unlock_button": {
                        "label": "🔓 Unlock",
                        "url": "https://creator.example/unlock/opaque",
                    }},
                ),
                context={"chat_id": 123456789, "transport": VerifiedCommercialSender()},
            )

        result = asyncio.run(run())
        self.assertEqual(result.metadata["telegram_message_id"], 779)
        self.assertTrue(result.metadata["actionable_destination_attached"])
        self.assertTrue(result.metadata["provider_action_verified"])
        self.assertTrue(result.metadata["provider_markup_included"])
        self.assertTrue(result.metadata["provider_markup_verified"])
        self.assertEqual(
            result.metadata["attachment_mode"],
            "TELEGRAM_BUSINESS_INLINE_BUTTON",
        )
        self.assertTrue(result.metadata["customer_facing_destination_valid"])
        self.assertEqual(result.metadata["destination_scope"], "PUBLIC")

    def test_commercial_localhost_destination_fails_before_transport(self):
        sender = RecordingTextSender()
        executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())
        result = executor.execute(
            TelegramDeliveryPayload(
                message_text="Here it is - unlock this private one.",
                delivery_method="text",
                metadata={"private_chat_unlock_button": {
                    "label": "Unlock", "url": "http://127.0.0.1:8001/unlock/x",
                }},
            ),
            context={"chat_id": 123456789, "text_sender": sender},
        )
        self.assertFalse(result.executed)
        self.assertEqual(sender.calls, [])

    def test_execute_preserves_blocked_and_no_delivery_states(self):
        executor = TelegramDeliveryExecutor()

        blocked = executor.execute(
            {
                "delivery_method": "blocked",
                "blocking_reason": "media_link_unavailable",
            }
        )
        none = executor.execute({"delivery_method": "none"})

        self.assertEqual(blocked.status, "blocked")
        self.assertEqual(blocked.blocking_reason, "media_link_unavailable")
        self.assertEqual(none.status, "no_delivery")
        self.assertFalse(none.executed)

    def test_executor_source_does_not_own_business_logic_or_transport(self):
        source = Path("app/services/telegram_delivery_executor.py").read_text()

        self.assertNotIn("DecisionEngine", source)
        self.assertNotIn("ProductRecommendationService", source)
        self.assertNotIn("PublishingService", source)
        self.assertNotIn("TelegramBotApiSender", source)
        self.assertNotIn("TelethonUserTransport", source)


if __name__ == "__main__":
    unittest.main()
