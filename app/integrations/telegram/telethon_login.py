"""Interactive one-time authorization for a Telethon user session."""

import argparse
import asyncio
import getpass
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError

from app.config import ENV_PATH


class TelethonLoginError(RuntimeError):
    """A sanitized Telethon authorization failure."""


class TelethonLogin:
    """Create an authorized user-account session without logging secrets."""

    def __init__(
        self,
        *,
        api_id: int,
        api_hash: str,
        session_path: str,
        client_factory: Callable[..., Any] = TelegramClient,
        input_fn: Callable[[str], str] = input,
        secret_input_fn: Callable[[str], str] = getpass.getpass,
        logger: logging.Logger | None = None,
    ) -> None:
        if isinstance(api_id, bool) or not isinstance(api_id, int) or api_id <= 0:
            raise ValueError("api_id must be a positive integer")
        if not isinstance(api_hash, str) or not api_hash.strip():
            raise ValueError("api_hash is required")
        if not isinstance(session_path, str) or not session_path.strip():
            raise ValueError("session_path is required")

        self._api_id = api_id
        self._api_hash = api_hash.strip()
        self._session_path = session_path.strip()
        self._client_factory = client_factory
        self._input = input_fn
        self._secret_input = secret_input_fn
        self._logger = logger or logging.getLogger("telethon-login")

    async def authorize(self) -> None:
        """Interactively authorize the session, including Telegram 2FA."""

        Path(self._session_path).expanduser().parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        client = self._client_factory(
            self._session_path,
            self._api_id,
            self._api_hash,
        )

        try:
            await client.connect()
            if await client.is_user_authorized():
                self._logger.info("Telethon session is already authorized.")
                return

            phone = self._input("Telegram phone number: ").strip()
            if not phone:
                raise TelethonLoginError("A phone number is required.")

            await client.send_code_request(phone)
            code = self._secret_input("Telegram login code: ").strip()
            if not code:
                raise TelethonLoginError("A Telegram login code is required.")

            try:
                await client.sign_in(phone=phone, code=code)
            except SessionPasswordNeededError:
                password = self._secret_input("Telegram 2FA password: ")
                if not password:
                    raise TelethonLoginError(
                        "A Telegram 2FA password is required."
                    ) from None
                await client.sign_in(password=password)

            self._logger.info("Telethon session authorized successfully.")
        except TelethonLoginError:
            raise
        except Exception as error:
            self._logger.error(
                "[TELETHON ERROR] login failed error_type=%s",
                type(error).__name__,
            )
            raise TelethonLoginError("Telethon authorization failed.") from None
        finally:
            await client.disconnect()


def _positive_api_id(value: str) -> int:
    try:
        api_id = int(value)
    except (TypeError, ValueError):
        raise TelethonLoginError("TG_API_ID must be a positive integer.") from None
    if api_id <= 0:
        raise TelethonLoginError("TG_API_ID must be a positive integer.")
    return api_id


def build_login_from_environment() -> TelethonLogin:
    load_dotenv(dotenv_path=ENV_PATH, override=True)

    api_hash = os.getenv("TG_API_HASH", "").strip()
    if not api_hash:
        raise TelethonLoginError("TG_API_HASH is required.")

    return TelethonLogin(
        api_id=_positive_api_id(os.getenv("TG_API_ID", "")),
        api_hash=api_hash,
        session_path=os.getenv(
            "TG_SESSION_PATH",
            "tg_sessions/ava",
        ).strip(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Authorize Ava's Telethon user-account session."
    )
    parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    asyncio.run(build_login_from_environment().authorize())


if __name__ == "__main__":
    main()
