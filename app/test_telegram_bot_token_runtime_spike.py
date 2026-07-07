import unittest

from app.integrations.telegram.bot_token_runtime_spike import (
    TelegramBotRuntimeError,
    TelegramBotTokenRuntimeSpike,
    TelegramBotTokenUpdateSource,
)
from app.models.telegram_inbound import TelegramInboundResult


class FakeResponse:
    def __init__(self, payload, *, raises=False):
        self.payload = payload
        self.raises = raises

    def raise_for_status(self):
        if self.raises:
            raise RuntimeError("request contained secret-token")

    def json(self):
        return self.payload


class RecordingSession:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self.response


class StaticUpdateSource:
    def __init__(self, update):
        self.update = update
        self.calls = 0

    def receive_one_update(self):
        self.calls += 1
        return self.update


class RecordingInboundAdapter:
    def __init__(self, *, result_overrides=None):
        self.calls = []
        self.result_overrides = result_overrides or {}

    def execute(self, payload):
        self.calls.append(payload)
        values = {
            "correlation_id": (
                f"telegram:{payload.telegram_chat_id}:{payload.message_id}"
            ),
            "telegram_chat_id": payload.telegram_chat_id,
            "telegram_user_id": payload.telegram_user_id,
            "message_id": payload.message_id,
            "engine_user_id": "7:-123456789",
            "response_text": "Brain result sent",
            "offer_authorized": False,
            "offer_link": None,
            "blocked": False,
            "error_code": None,
            "diagnostic_metadata": {"status": "ok"},
        }
        values.update(self.result_overrides)
        return TelegramInboundResult(**values)


class RecordingOutboundSender:
    def __init__(self):
        self.calls = []

    def send_text(self, *, chat_id, message_text):
        self.calls.append(
            {"chat_id": chat_id, "message_text": message_text}
        )


def private_text_update():
    return {
        "update_id": 9001,
        "message": {
            "message_id": 42,
            "from": {
                "id": 123456789,
                "is_bot": False,
            },
            "chat": {
                "id": 123456789,
                "type": "private",
            },
            "text": "hello Ava",
        },
    }


class TelegramBotTokenUpdateSourceTests(unittest.TestCase):
    def test_one_shot_source_calls_only_get_updates(self):
        session = RecordingSession(
            FakeResponse({"ok": True, "result": [private_text_update()]})
        )
        source = TelegramBotTokenUpdateSource(
            bot_token="test-token",
            timeout_seconds=12,
            session=session,
        )

        update = source.receive_one_update()

        self.assertEqual(update, private_text_update())
        self.assertEqual(len(session.calls), 1)
        url, kwargs = session.calls[0]
        self.assertTrue(url.endswith("/getUpdates"))
        self.assertNotIn("sendMessage", url)
        self.assertEqual(kwargs["params"]["limit"], 1)
        self.assertEqual(kwargs["params"]["timeout"], 12)

    def test_no_updates_returns_none(self):
        session = RecordingSession(
            FakeResponse({"ok": True, "result": []})
        )
        source = TelegramBotTokenUpdateSource(
            bot_token="test-token",
            timeout_seconds=0,
            session=session,
        )

        self.assertIsNone(source.receive_one_update())

    def test_http_failure_does_not_expose_token(self):
        session = RecordingSession(
            FakeResponse({}, raises=True)
        )
        source = TelegramBotTokenUpdateSource(
            bot_token="super-secret-token",
            timeout_seconds=0,
            session=session,
        )

        with self.assertRaises(TelegramBotRuntimeError) as caught:
            source.receive_one_update()

        self.assertNotIn("super-secret-token", str(caught.exception))


class TelegramBotTokenRuntimeSpikeTests(unittest.TestCase):
    def test_private_text_update_reaches_inbound_adapter_once(self):
        source = StaticUpdateSource(private_text_update())
        inbound = RecordingInboundAdapter()
        outbound = RecordingOutboundSender()
        runtime = TelegramBotTokenRuntimeSpike(
            update_source=source,
            inbound_adapter=inbound,
            outbound_sender=outbound,
        )

        result = runtime.run_once()

        self.assertEqual(source.calls, 1)
        self.assertEqual(len(inbound.calls), 1)
        payload = inbound.calls[0]
        self.assertEqual(payload.telegram_user_id, 123456789)
        self.assertEqual(payload.telegram_chat_id, 123456789)
        self.assertEqual(payload.message_id, 42)
        self.assertEqual(payload.message_text, "hello Ava")
        self.assertEqual(result.engine_user_id, "7:-123456789")
        self.assertEqual(result.response_text, "Brain result sent")
        self.assertEqual(
            outbound.calls,
            [{"chat_id": 123456789, "message_text": "Brain result sent"}],
        )

    def test_offer_metadata_is_not_sent(self):
        inbound = RecordingInboundAdapter(
            result_overrides={
                "response_text": "Plain conversational reply",
                "offer_authorized": True,
                "offer_link": "https://fanvue.com/not-delivered",
            }
        )
        outbound = RecordingOutboundSender()
        runtime = TelegramBotTokenRuntimeSpike(
            update_source=StaticUpdateSource(private_text_update()),
            inbound_adapter=inbound,
            outbound_sender=outbound,
        )

        runtime.run_once()

        self.assertEqual(
            outbound.calls,
            [
                {
                    "chat_id": 123456789,
                    "message_text": "Plain conversational reply",
                }
            ],
        )

    def test_unsupported_updates_do_not_reach_inbound_adapter(self):
        updates = (
            {"update_id": 1, "edited_message": {}},
            {
                "message": {
                    "message_id": 1,
                    "from": {"id": 1, "is_bot": False},
                    "chat": {"id": -1001, "type": "group"},
                    "text": "group text",
                }
            },
            {
                "message": {
                    "message_id": 1,
                    "from": {"id": 1, "is_bot": False},
                    "chat": {"id": 1, "type": "private"},
                    "photo": [],
                }
            },
        )
        for update in updates:
            with self.subTest(update=update):
                inbound = RecordingInboundAdapter()
                outbound = RecordingOutboundSender()
                runtime = TelegramBotTokenRuntimeSpike(
                    update_source=StaticUpdateSource(update),
                    inbound_adapter=inbound,
                    outbound_sender=outbound,
                )
                self.assertIsNone(runtime.run_once())
                self.assertEqual(inbound.calls, [])
                self.assertEqual(outbound.calls, [])

    def test_empty_update_result_does_not_call_inbound_adapter(self):
        inbound = RecordingInboundAdapter()
        outbound = RecordingOutboundSender()
        runtime = TelegramBotTokenRuntimeSpike(
            update_source=StaticUpdateSource(None),
            inbound_adapter=inbound,
            outbound_sender=outbound,
        )

        self.assertIsNone(runtime.run_once())
        self.assertEqual(inbound.calls, [])
        self.assertEqual(outbound.calls, [])


if __name__ == "__main__":
    unittest.main()
