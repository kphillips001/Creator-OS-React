"""X publishing provider.

The provider owns X credential lookup, media preparation, and API calls.
SocialPublishingService owns queue state and publish history.
"""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps


class XPublishError(RuntimeError):
    """Raised when X publishing cannot complete."""


@dataclass(frozen=True)
class XAccount:
    account_name: str
    display_name: str
    credential_env: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class XPublishResult:
    success: bool
    account_name: str
    provider_post_id: str | None = None
    provider_media_id: str | None = None
    provider_output_url: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class XPublishingProvider:
    """Thin provider for posting generated images to X."""

    X_IMAGE_MAX_BYTES = 4_500_000
    X_IMAGE_MAX_SIDE = 4096

    DEFAULT_ACCOUNTS = (
        XAccount(
            account_name="AvaBlackthorne",
            display_name="AvaBlackthorne",
            credential_env={
                "consumer_key": "X_CONSUMER_KEY",
                "consumer_secret": "X_CONSUMER_SECRET",
                "access_token": "X_ACCESS_TOKEN",
                "access_token_secret": "X_ACCESS_TOKEN_SECRET",
            },
        ),
        XAccount(
            account_name="AvaBlackthorneX",
            display_name="AvaBlackthorneX",
            credential_env={
                "consumer_key": "X_AVABLACKTHORNEX_CONSUMER_KEY",
                "consumer_secret": "X_AVABLACKTHORNEX_CONSUMER_SECRET",
                "access_token": "X_AVABLACKTHORNEX_ACCESS_TOKEN",
                "access_token_secret": "X_AVABLACKTHORNEX_ACCESS_TOKEN_SECRET",
            },
        ),
    )

    def __init__(self, *, accounts: tuple[XAccount, ...] | None = None, http_client=None, tweepy_module=None):
        self._accounts = accounts or self.DEFAULT_ACCOUNTS
        self.http_client = http_client or requests
        self._tweepy = tweepy_module

    def accounts(self) -> tuple[XAccount, ...]:
        return self._accounts

    def account_names(self) -> tuple[str, ...]:
        return tuple(account.account_name for account in self._accounts)

    def get_account(self, account_name: str | None) -> XAccount:
        selected = str(account_name or "").strip()
        if not selected and self._accounts:
            return self._accounts[0]
        for account in self._accounts:
            if account.account_name == selected:
                return account
        raise XPublishError(f"Unknown X account: {selected}")

    def credentials_for(self, account_name: str | None) -> dict[str, str]:
        account = self.get_account(account_name)
        credentials = {
            key: os.getenv(env_name, "")
            for key, env_name in account.credential_env.items()
        }
        missing = tuple(
            env_name
            for key, env_name in account.credential_env.items()
            if not credentials.get(key)
        )
        if missing:
            raise XPublishError("Missing X credentials: " + ", ".join(missing))
        return credentials

    def publish(
        self,
        *,
        image_reference: str,
        caption: str,
        account_name: str | None = None,
    ) -> XPublishResult:
        account = self.get_account(account_name)
        text = str(caption or "").strip()
        if not text:
            raise XPublishError("X caption text is required.")
        credentials = self.credentials_for(account.account_name)
        tweepy = self._load_tweepy()
        local_source = self._materialize_image_reference(image_reference)
        prepared_image = self._prepare_image_for_x(local_source)
        try:
            auth = tweepy.OAuth1UserHandler(
                credentials["consumer_key"],
                credentials["consumer_secret"],
                credentials["access_token"],
                credentials["access_token_secret"],
            )
            api = tweepy.API(auth)
            client = tweepy.Client(
                consumer_key=credentials["consumer_key"],
                consumer_secret=credentials["consumer_secret"],
                access_token=credentials["access_token"],
                access_token_secret=credentials["access_token_secret"],
            )
            media = api.media_upload(str(prepared_image))
            tweet = client.create_tweet(text=text[:280], media_ids=[media.media_id])
        except Exception as exc:
            raise XPublishError(f"{account.account_name} X publish failed: {self._error_details(exc)}") from exc
        finally:
            prepared_image.unlink(missing_ok=True)
            if local_source.parent.name.startswith("creator_os_x_"):
                local_source.unlink(missing_ok=True)

        post_id = self._tweet_id(tweet)
        return XPublishResult(
            success=True,
            account_name=account.account_name,
            provider_post_id=post_id,
            provider_media_id=str(getattr(media, "media_id", "")) or None,
            provider_output_url=f"https://x.com/{account.account_name}/status/{post_id}" if post_id else None,
            message="Posted to X.",
            metadata={"tweet_data": getattr(tweet, "data", None) or {}},
        )

    def _load_tweepy(self):
        if self._tweepy is not None:
            return self._tweepy
        try:
            import tweepy  # type: ignore
        except ImportError as exc:
            raise XPublishError("tweepy is required for X publishing.") from exc
        return tweepy

    def _materialize_image_reference(self, image_reference: str) -> Path:
        reference = str(image_reference or "").strip()
        if not reference:
            raise XPublishError("Generated image reference is required.")
        parsed = urlparse(reference)
        if parsed.scheme in {"http", "https"}:
            suffix = Path(parsed.path).suffix or ".jpg"
            temp_dir = Path(tempfile.mkdtemp(prefix="creator_os_x_"))
            target = temp_dir / f"generated{suffix}"
            response = self.http_client.get(reference, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status()
            target.write_bytes(response.content)
            return target
        path = Path(reference).expanduser()
        if not path.exists():
            raise XPublishError(f"Generated image was not found: {reference}")
        return path

    def _prepare_image_for_x(self, image_path: Path) -> Path:
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".jpg")
        temp_path = Path(temp_file.name)
        temp_file.close()
        with Image.open(image_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                background = Image.new("RGB", image.size, "white")
                alpha = image.convert("RGBA").getchannel("A")
                background.paste(image.convert("RGBA"), mask=alpha)
                image = background
            else:
                image = image.convert("RGB")
            image.thumbnail((self.X_IMAGE_MAX_SIDE, self.X_IMAGE_MAX_SIDE), Image.Resampling.LANCZOS)
            for quality in (94, 90, 86, 82, 78, 74, 70):
                image.save(temp_path, format="JPEG", quality=quality, optimize=True, progressive=True)
                if temp_path.stat().st_size <= self.X_IMAGE_MAX_BYTES:
                    return temp_path
            while temp_path.stat().st_size > self.X_IMAGE_MAX_BYTES:
                width, height = image.size
                if width < 600 or height < 600:
                    break
                image = image.resize((int(width * 0.9), int(height * 0.9)), Image.Resampling.LANCZOS)
                image.save(temp_path, format="JPEG", quality=76, optimize=True, progressive=True)
        if temp_path.stat().st_size > self.X_IMAGE_MAX_BYTES:
            temp_path.unlink(missing_ok=True)
            raise XPublishError("Prepared image is still too large for X upload.")
        return temp_path

    @staticmethod
    def _tweet_id(tweet: Any) -> str | None:
        data = getattr(tweet, "data", None)
        if isinstance(data, Mapping):
            value = data.get("id")
            return str(value) if value is not None else None
        return None

    @staticmethod
    def _error_details(error: Exception) -> str:
        details = []
        response = getattr(error, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code:
            details.append(f"status {status_code}")
        response_text = getattr(response, "text", None)
        if response_text:
            details.append(str(response_text)[:500])
        api_messages = getattr(error, "api_messages", None)
        if api_messages:
            details.append("; ".join(str(message) for message in api_messages))
        text = str(error)
        if text:
            details.append(text)
        return " - ".join(details) or error.__class__.__name__
