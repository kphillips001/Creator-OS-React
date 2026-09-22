import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.integrations.telegram.bot_api_sender import (
    TELEGRAM_TEXT_LIMIT,
    TelegramBotApiSender,
    TelegramOutboundSendError,
    TelegramOutboundSendAmbiguousError,
)


class FakeResponse:
    def __init__(self, payload, *, status_code=200, raises=False):
        self.payload = payload
        self.status_code = status_code
        self.raises = raises

    def json(self):
        if self.raises:
            raise ValueError("unreadable response")
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
    def _send_fixture_asset(self, sender):
        with TemporaryDirectory() as directory:
            asset_path = Path(directory) / "fixture.bin"
            asset_path.write_bytes(b"fixture")
            return sender.send_asset(
                chat_id=123456789, asset_path=str(asset_path), message_text="hello",
            )

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

    def test_ordinary_text_does_not_change_link_preview_behavior(self):
        session = RecordingSession(
            FakeResponse({"ok": True, "result": {"message_id": 100}})
        )
        sender = TelegramBotApiSender(bot_token="test-token", session=session)
        sender.send_text(
            chat_id=123456789,
            message_text="ordinary https://creator.example/page",
        )
        self.assertNotIn("link_preview_options", session.calls[0][1]["json"])

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

        with self.assertRaises(TelegramOutboundSendAmbiguousError) as caught:
            sender.send_text(chat_id=123456789, message_text="hello")

        self.assertNotIn("super-secret-token", str(caught.exception))

    def test_media_provider_rejection_preserves_bounded_diagnostics(self):
        session = RecordingSession(FakeResponse({
            "ok": False, "error_code": 400,
            "description": "Bad Request: image dimensions are invalid",
        }, status_code=400))
        sender = TelegramBotApiSender(bot_token="test-token", session=session)

        with self.assertRaises(TelegramOutboundSendError) as caught:
            self._send_fixture_asset(sender)

        message = str(caught.exception)
        self.assertIn("HTTP 400", message)
        self.assertIn("error_code 400", message)
        self.assertIn("image dimensions are invalid", message)

    def test_media_transport_failure_is_acceptance_ambiguous(self):
        sender = TelegramBotApiSender(
            bot_token="test-token", session=RecordingSession(raises=True),
        )

        with self.assertRaises(TelegramOutboundSendAmbiguousError):
            self._send_fixture_asset(sender)

    def test_unreadable_media_response_is_acceptance_ambiguous(self):
        sender = TelegramBotApiSender(
            bot_token="test-token",
            session=RecordingSession(FakeResponse({}, status_code=502, raises=True)),
        )

        with self.assertRaises(TelegramOutboundSendAmbiguousError):
            self._send_fixture_asset(sender)


if __name__ == "__main__":
    unittest.main()
