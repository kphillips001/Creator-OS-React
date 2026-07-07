import unittest

from app.integrations.telegram.bot_api_sender import (
    TELEGRAM_TEXT_LIMIT,
    TelegramBotApiSender,
    TelegramOutboundSendError,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, raises=False):
        self.payload = payload
        self.status_code = status_code
        self.raises = raises

    def json(self):
        return self.payload

    def raise_for_status(self):
        if self.raises:
            raise RuntimeError("request failed with secret-token")


class RecordingSession:
    def __init__(self, response=None, *, raises=False):
        self.response = response
        self.raises = raises
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.raises:
            raise RuntimeError("request failed with secret-token")
        return self.response


class TelegramBotApiSenderTests(unittest.TestCase):
    def test_sends_exact_plain_text_payload_and_logs_status(self):
        session = RecordingSession(
            FakeResponse({"ok": True, "result": {"message_id": 99}})
        )
        sender = TelegramBotApiSender(
            bot_token="test-token",
            session=session,
        )

        with self.assertLogs("telegram-bot-api-sender", level="INFO") as logs:
            sender.send_text(chat_id=123456789, message_text="hello")

        self.assertEqual(len(session.calls), 1)
        url, kwargs = session.calls[0]
        self.assertTrue(url.endswith("/sendMessage"))
        self.assertEqual(
            kwargs["json"],
            {"chat_id": 123456789, "text": "hello"},
        )
        self.assertEqual(set(kwargs["json"]), {"chat_id", "text"})
        log_output = "\n".join(logs.output)
        self.assertIn("[TELEGRAM SEND]", log_output)
        self.assertIn("chat_id=123456789", log_output)
        self.assertIn("message_length=5", log_output)
        self.assertIn("status_code=200", log_output)
        self.assertIn("ok=True", log_output)

    def test_rejects_group_and_channel_chat_ids_before_request(self):
        session = RecordingSession()
        sender = TelegramBotApiSender(
            bot_token="test-token",
            session=session,
        )

        for chat_id in (0, -1002507455539):
            with self.subTest(chat_id=chat_id):
                with self.assertRaises(ValueError):
                    sender.send_text(chat_id=chat_id, message_text="hello")

        self.assertEqual(session.calls, [])

    def test_rejects_empty_and_oversized_text_before_request(self):
        session = RecordingSession()
        sender = TelegramBotApiSender(
            bot_token="test-token",
            session=session,
        )

        for message_text in ("", "   ", "x" * (TELEGRAM_TEXT_LIMIT + 1)):
            with self.subTest(length=len(message_text)):
                with self.assertRaises(ValueError):
                    sender.send_text(
                        chat_id=123456789,
                        message_text=message_text,
                    )

        self.assertEqual(session.calls, [])

    def test_telegram_rejection_is_sanitized(self):
        session = RecordingSession(
            FakeResponse(
                {"ok": False, "description": "secret-token"},
                status_code=400,
                raises=True,
            )
        )
        sender = TelegramBotApiSender(
            bot_token="super-secret-token",
            session=session,
        )

        with self.assertRaises(TelegramOutboundSendError) as caught:
            sender.send_text(chat_id=123456789, message_text="hello")

        self.assertNotIn("super-secret-token", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
