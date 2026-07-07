import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from telethon.errors import SessionPasswordNeededError

from app.integrations.telegram.telethon_login import (
    TelethonLogin,
    build_login_from_environment,
)


class FakeLoginClient:
    def __init__(self, *, authorized=False, require_2fa=False):
        self.authorized = authorized
        self.require_2fa = require_2fa
        self.connected = False
        self.disconnected = False
        self.code_requests = []
        self.sign_ins = []

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.disconnected = True

    async def is_user_authorized(self):
        return self.authorized

    async def send_code_request(self, phone):
        self.code_requests.append(phone)

    async def sign_in(self, **kwargs):
        self.sign_ins.append(kwargs)
        if self.require_2fa and "code" in kwargs:
            raise SessionPasswordNeededError(request=None)


class RecordingFactory:
    def __init__(self, client):
        self.client = client
        self.calls = []

    def __call__(self, session_path, api_id, api_hash):
        self.calls.append((session_path, api_id, api_hash))
        return self.client


class TelethonLoginTests(unittest.IsolatedAsyncioTestCase):
    def test_builder_loads_repository_env_before_reading_credentials(self):
        loaded_paths = []

        def load_test_env(*, dotenv_path, override):
            import os

            loaded_paths.append((dotenv_path, override))
            os.environ.update(
                {
                    "TG_API_ID": "12345",
                    "TG_API_HASH": "test-api-hash",
                    "TG_SESSION_PATH": "tg_sessions/test-ava",
                }
            )

        with (
            patch.dict(
                "os.environ",
                {},
                clear=True,
            ),
            patch(
                "app.integrations.telegram.telethon_login.load_dotenv",
                side_effect=load_test_env,
            ),
        ):
            login = build_login_from_environment()

        self.assertEqual(len(loaded_paths), 1)
        self.assertTrue(loaded_paths[0][1])
        self.assertEqual(login._api_id, 12345)
        self.assertEqual(login._api_hash, "test-api-hash")
        self.assertEqual(login._session_path, "tg_sessions/test-ava")

    async def test_phone_code_login_creates_session_parent(self):
        client = FakeLoginClient()
        factory = RecordingFactory(client)
        with tempfile.TemporaryDirectory() as directory:
            session_path = str(Path(directory) / "sessions" / "ava")
            login = TelethonLogin(
                api_id=12345,
                api_hash="api-hash",
                session_path=session_path,
                client_factory=factory,
                input_fn=lambda prompt: "+15551234567",
                secret_input_fn=lambda prompt: "12345",
            )

            await login.authorize()

            self.assertTrue(Path(session_path).parent.is_dir())

        self.assertEqual(client.code_requests, ["+15551234567"])
        self.assertEqual(
            client.sign_ins,
            [{"phone": "+15551234567", "code": "12345"}],
        )
        self.assertTrue(client.disconnected)

    async def test_two_factor_password_is_supported(self):
        client = FakeLoginClient(require_2fa=True)
        secrets = iter(("12345", "two-factor-secret"))
        login = TelethonLogin(
            api_id=12345,
            api_hash="api-hash",
            session_path="tg_sessions/test-ava",
            client_factory=RecordingFactory(client),
            input_fn=lambda prompt: "+15551234567",
            secret_input_fn=lambda prompt: next(secrets),
        )

        await login.authorize()

        self.assertEqual(
            client.sign_ins,
            [
                {"phone": "+15551234567", "code": "12345"},
                {"password": "two-factor-secret"},
            ],
        )
        self.assertTrue(client.disconnected)

    async def test_existing_session_does_not_prompt(self):
        client = FakeLoginClient(authorized=True)
        prompts = []
        login = TelethonLogin(
            api_id=12345,
            api_hash="api-hash",
            session_path="tg_sessions/test-ava",
            client_factory=RecordingFactory(client),
            input_fn=lambda prompt: prompts.append(prompt),
        )

        await login.authorize()

        self.assertEqual(prompts, [])
        self.assertEqual(client.code_requests, [])
        self.assertTrue(client.disconnected)


if __name__ == "__main__":
    unittest.main()
