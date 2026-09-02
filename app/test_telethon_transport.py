import unittest

from app.integrations.telegram.telethon_transport import (
    TelethonTransportError,
    TelethonUserTransport,
)


class FakeSender:
    def __init__(self, *, sender_id=123456789, bot=False):
        self.id = sender_id
        self.bot = bot


class FakeEvent:
    def __init__(
        self,
        *,
        text="hello",
        private=True,
        outgoing=False,
        sender=None,
        chat_id=123456789,
        message_id=42,
    ):
        self.raw_text = text
        self.is_private = private
        self.out = outgoing
        self.chat_id = chat_id
        self.id = message_id
        self.sender = sender or FakeSender()

    async def get_sender(self):
        return self.sender


class FakeTelethonClient:
    def __init__(self, *, authorized=True):
        self.authorized = authorized
        self.connected = False
        self.disconnected = False
        self.handlers = []
        self.sent = []

    async def connect(self):
        self.connected = True

    async def is_user_authorized(self):
        return self.authorized

    def add_event_handler(self, handler, event_builder):
        self.handlers.append((handler, event_builder))

    async def is_bot(self):
        return False

    async def send_message(self, chat_id, message_text, **kwargs):
        self.sent.append((chat_id, message_text))
        return type("Message", (), {"id": len(self.sent), "raw_text": message_text})()

    async def get_messages(self, chat_id, ids):
        text = self.sent[ids - 1][1]
        return type(
            "Message", (), {"id": ids, "raw_text": text, "buttons": []}
        )()

    async def run_until_disconnected(self):
        return None

    async def disconnect(self):
        self.disconnected = True


class TelethonUserTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_incoming_text_is_normalized(self):
        payload = await TelethonUserTransport.normalize_event(FakeEvent())

        self.assertEqual(payload.telegram_user_id, 123456789)
        self.assertEqual(payload.telegram_chat_id, 123456789)
        self.assertEqual(payload.message_id, 42)
        self.assertEqual(payload.message_text, "hello")
        self.assertEqual(payload.chat_history, [])

    async def test_groups_outgoing_empty_and_bot_messages_are_ignored(self):
        events = (
            FakeEvent(private=False),
            FakeEvent(outgoing=True),
            FakeEvent(text="   "),
            FakeEvent(sender=FakeSender(bot=True)),
        )

        for event in events:
            with self.subTest(event=event):
                self.assertIsNone(
                    await TelethonUserTransport.normalize_event(event)
                )

    async def test_start_requires_authorized_session(self):
        transport = TelethonUserTransport(
            client=FakeTelethonClient(authorized=False)
        )

        with self.assertRaises(TelethonTransportError):
            await transport.start()

    async def test_handler_receives_payload_and_send_uses_user_client(self):
        client = FakeTelethonClient()
        transport = TelethonUserTransport(client=client)
        received = []

        async def handler(payload):
            received.append(payload)

        transport.set_inbound_handler(handler)
        await transport.start()
        self.assertEqual(len(client.handlers), 1)
        await client.handlers[0][0](FakeEvent())
        await transport.send_text(chat_id=123456789, message_text="hello")

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].message_text, "hello")
        self.assertEqual(client.sent, [(123456789, "hello")])

    async def test_user_session_commercial_send_uses_provider_verified_visible_url(self):
        client = FakeTelethonClient()
        transport = TelethonUserTransport(client=client)

        receipt = await transport.send_text(
            chat_id=123456789,
            message_text="Here it is - unlock this private one.",
            button_label="Unlock",
            button_url="https://creator.example/unlock/opaque",
        )

        self.assertEqual(receipt.id, 1)
        self.assertEqual(receipt.attachment_mode, "VISIBLE_URL")
        self.assertTrue(receipt.actionable_destination_attached)
        self.assertTrue(receipt.provider_action_verified)
        self.assertFalse(receipt.provider_markup_included)
        self.assertFalse(receipt.provider_markup_verified)
        self.assertIn("Unlock: https://creator.example/unlock/opaque", receipt.final_text)


if __name__ == "__main__":
    unittest.main()
