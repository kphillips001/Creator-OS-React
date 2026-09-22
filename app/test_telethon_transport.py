import unittest
import asyncio
from datetime import datetime, timezone
from types import SimpleNamespace

from telethon.tl import functions, types

from app.integrations.telegram.telethon_transport import (
    TelethonCommercialCapabilityError,
    TelethonTransportError,
    TelethonUserTransport,
)


async def _async_items(*items):
    for item in items:
        yield item


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
        photo=None,
        document=None,
        grouped_id=None,
    ):
        self.raw_text = text
        self.is_private = private
        self.out = outgoing
        self.chat_id = chat_id
        self.id = message_id
        self.sender = sender or FakeSender()
        self.photo = photo
        self.document = document
        self.grouped_id = grouped_id
        self.message = self

    async def get_sender(self):
        return self.sender


class FakeTelethonClient:
    def __init__(self, *, authorized=True):
        self.authorized = authorized
        self.connected = False
        self.disconnected = False
        self.handlers = []
        self.sent = []
        self.actions = []
        self.requests = []
        self.resolved = []
        self.send_options = []

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
        self.send_options.append(dict(kwargs))
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

    async def get_input_entity(self, chat_id):
        self.resolved.append(chat_id)
        return types.InputPeerUser(chat_id, 987654321)

    async def __call__(self, request):
        self.requests.append(request)
        return True

    def action(self, chat_id, action_name):
        client = self

        class Action:
            async def __aenter__(self):
                client.actions.append(("start", chat_id, action_name))

            async def __aexit__(self, *_args):
                client.actions.append(("stop", chat_id, action_name))

        return Action()


class TelethonUserTransportTests(unittest.IsolatedAsyncioTestCase):
    async def test_private_incoming_text_is_normalized(self):
        payload = await TelethonUserTransport.normalize_event(FakeEvent())

        self.assertEqual(payload.telegram_user_id, 123456789)
        self.assertEqual(payload.telegram_chat_id, 123456789)
        self.assertEqual(payload.message_id, 42)
        self.assertEqual(payload.message_text, "hello")
        self.assertEqual(payload.chat_history, [])

    async def test_bounded_history_reuses_live_eligibility_and_skips_old_dialogs(self):
        cutoff = datetime(2026, 9, 17, 1, 0, tzinfo=timezone.utc)
        current = FakeEvent(message_id=6412)
        current.date = datetime(2026, 9, 17, 1, 20, tzinfo=timezone.utc)
        outgoing = FakeEvent(message_id=6413, outgoing=True)
        outgoing.date = datetime(2026, 9, 17, 1, 21, tzinfo=timezone.utc)
        client = FakeTelethonClient()
        client.iter_dialogs = lambda **_: _async_items(
            SimpleNamespace(entity=FakeSender(), date=current.date),
            SimpleNamespace(entity=FakeSender(sender_id=8),
                            date=datetime(2026, 9, 16, tzinfo=timezone.utc)),
        )
        calls = []
        def messages(entity, **_):
            calls.append(entity.id)
            return _async_items(outgoing, current)
        client.iter_messages = messages
        result = await TelethonUserTransport(client=client).bounded_private_inbound_history(
            since=cutoff, dialog_limit=10, per_dialog_limit=10)
        self.assertEqual([item.message_id for item in result], [6412])
        self.assertEqual(calls, [123456789])

    async def test_media_only_photo_and_captioned_document_are_normalized(self):
        photo=type("Photo",(),{"id":77,"sizes":[type("Size",(),{"w":640,"h":480})()]})()
        media_only=await TelethonUserTransport.normalize_event(FakeEvent(text="",photo=photo,grouped_id=9))
        self.assertEqual(media_only.message_text,"")
        self.assertEqual(media_only.attachments[0].media_kind,"PHOTO")
        self.assertEqual(media_only.attachments[0].grouped_id,"9")
        document=type("Document",(),{"id":88,"mime_type":"image/png","size":123,"w":20,"h":10,"attributes":[]})()
        captioned=await TelethonUserTransport.normalize_event(FakeEvent(text="exact caption",document=document))
        self.assertEqual(captioned.message_text,"exact caption")
        self.assertEqual(captioned.attachments[0].mime_type,"image/png")

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

    async def test_user_session_commercial_send_fails_closed_without_exposing_url(self):
        client = FakeTelethonClient()
        transport = TelethonUserTransport(client=client)

        with self.assertRaises(TelethonCommercialCapabilityError):
            await transport.send_text(
                chat_id=123456789,
                message_text="Here it is - unlock this private one.",
                button_label="Unlock",
                button_url="https://creator.example/unlock/opaque",
            )
        self.assertEqual(client.sent, [])
        self.assertEqual(client.send_options, [])

    async def test_accepted_commercial_send_with_unverifiable_action_stays_ambiguous(self):
        class MissingProviderEcho(FakeTelethonClient):
            async def get_messages(self, chat_id, ids):
                return type("Message", (), {
                    "id": ids, "raw_text": "Offer without destination", "buttons": [],
                })()

        transport = TelethonUserTransport(client=MissingProviderEcho())
        with self.assertRaises(TelethonCommercialCapabilityError):
            await transport.send_text(
                chat_id=123456789, message_text="Offer",
                button_label="Unlock",
                button_url="https://creator.example/unlock/opaque",
            )

    async def test_native_typing_overlaps_existing_operation_and_stops_before_send(self):
        client = FakeTelethonClient()
        transport = TelethonUserTransport(client=client)
        timeline = []

        async def existing_pacing_wait():
            timeline.append("wait")

        await transport.show_typing_while(
            chat_id=123456789, operation=existing_pacing_wait(),
        )
        timeline.append("delivery")

        self.assertEqual(client.resolved, [123456789])
        self.assertEqual(len(client.requests), 2)
        self.assertIsInstance(client.requests[0], functions.messages.SetTypingRequest)
        self.assertIsInstance(client.requests[0].action, types.SendMessageTypingAction)
        self.assertEqual(client.requests[0].peer.user_id, 123456789)
        self.assertIsInstance(client.requests[1].action, types.SendMessageCancelAction)
        self.assertEqual(timeline, ["wait", "delivery"])
        self.assertEqual(client.sent, [])

    async def test_typing_publication_failure_does_not_skip_existing_wait(self):
        class FailingActionClient(FakeTelethonClient):
            async def __call__(self, request):
                raise ConnectionError("typing unavailable")

        transport = TelethonUserTransport(client=FailingActionClient())
        waited = []

        async def existing_pacing_wait():
            waited.append(True)

        with self.assertLogs("telethon-transport", level="WARNING"):
            await transport.show_typing_while(
                chat_id=123456789, operation=existing_pacing_wait(),
            )

        self.assertEqual(waited, [True])

    async def test_initial_native_request_completes_before_pacing_begins(self):
        timeline = []

        class RecordingClient(FakeTelethonClient):
            async def __call__(self, request):
                timeline.append(type(request.action).__name__)
                return await super().__call__(request)

        client = RecordingClient()
        transport = TelethonUserTransport(client=client)

        async def pacing():
            timeline.append("pacing")

        await transport.show_typing_while(
            chat_id=123456789, telegram_user_id=123456789,
            correlation_id="ordinary:test", operation=pacing(),
        )

        self.assertEqual(timeline, [
            "SendMessageTypingAction", "pacing", "SendMessageCancelAction",
        ])
        self.assertEqual(client.sent, [])

    async def test_long_wait_refreshes_at_canonical_interval(self):
        client = FakeTelethonClient()
        transport = TelethonUserTransport(client=client)
        canonical_refresh = transport._refresh_typing

        async def brief_refresh_interval(peer):
            await canonical_refresh(peer, interval_seconds=0.01)

        transport._refresh_typing = brief_refresh_interval
        await transport.show_typing_while(
            chat_id=123456789, operation=asyncio.sleep(0.025),
        )

        typing = [request for request in client.requests
                  if isinstance(request.action, types.SendMessageTypingAction)]
        self.assertGreaterEqual(len(typing), 2)
        self.assertIsInstance(client.requests[-1].action, types.SendMessageCancelAction)


if __name__ == "__main__":
    unittest.main()
