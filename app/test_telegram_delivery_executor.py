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
            executor = TelegramDeliveryExecutor(global_safety_service=AllowingSafetyService())

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
