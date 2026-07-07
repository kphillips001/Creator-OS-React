import unittest

from app.models.conversation_gateway import (
    ConversationGatewayInput,
    ConversationGatewayOutput,
)
from app.models.telegram_inbound import TelegramInboundPayload
from app.services.telegram_identity_adapter import TelegramIdentityAdapter
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


class FakeGateway:
    def __init__(self, output):
        self.output = output
        self.inputs = []

    def execute(self, gateway_input: ConversationGatewayInput):
        self.inputs.append(gateway_input)
        return self.output


class TelegramRuntimeDeliveryTests(unittest.TestCase):
    def execute(self, output):
        adapter = TelegramInboundAdapter(
            identity_adapter=TelegramIdentityAdapter(engine_account_id=7),
            conversation_gateway=FakeGateway(output),
        )
        return adapter.execute(
            TelegramInboundPayload(
                telegram_user_id=123456789,
                telegram_chat_id=123456789,
                message_text="show me",
                message_id=42,
            )
        )

    def test_paid_delivery_metadata_reaches_telegram_result(self):
        result = self.execute(
            ConversationGatewayOutput(
                correlation_id="telegram:123456789:42",
                response_text="Here is the offer.",
                offer_authorized=True,
                offer_link="https://fanvue.com/offer",
                blocked=False,
                error_code=None,
                delivery_type="PAID",
                delivery_mode="paid",
                delivery_requires_payment=True,
            )
        )

        self.assertEqual(result.delivery_type, "PAID")
        self.assertEqual(result.delivery_mode, "paid")
        self.assertTrue(result.delivery_requires_payment)
        self.assertEqual(result.offer_link, "https://fanvue.com/offer")

    def test_free_delivery_metadata_reaches_telegram_without_checkout(self):
        result = self.execute(
            ConversationGatewayOutput(
                correlation_id="telegram:123456789:42",
                response_text="Here is a free preview.",
                offer_authorized=True,
                offer_link=None,
                blocked=False,
                error_code=None,
                delivery_type="FREE",
                delivery_mode="included",
                delivery_requires_payment=False,
            )
        )

        self.assertEqual(result.delivery_type, "FREE")
        self.assertEqual(result.delivery_mode, "included")
        self.assertFalse(result.delivery_requires_payment)
        self.assertIsNone(result.offer_link)


if __name__ == "__main__":
    unittest.main()
