"""Telegram publishing provider migrated from Wavespeed_App."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

import requests
from PIL import Image, ImageOps

from app.config import settings


TELEGRAM_IMAGE_MAX_SIDE = 4096
TELEGRAM_IMAGE_MAX_TOTAL_DIMENSIONS = 9500
TELEGRAM_API_TIMEOUT = 45


class TelegramPublishError(RuntimeError):
    """Raised when Telegram publishing cannot complete."""


@dataclass(frozen=True)
class TelegramPublishResult:
    success: bool
    post_to: str
    provider_post_id: str | None = None
    message: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


class TelegramPublishingProvider:
    """Thin provider for posting generated images to Telegram Bot API."""

    def __init__(self, *, http_client=None):
        self.http_client = http_client or requests

    def publish(
        self,
        *,
        image_reference: str | None = None,
        caption: str = "",
        post_to: str = "main",
        cta_enabled: bool = False,
        cta_label: str = "",
        cta_url: str = "",
    ) -> TelegramPublishResult:
        result = self.publish_to_telegram(
            image_reference=image_reference,
            caption=caption,
            post_to=post_to,
            cta_enabled=cta_enabled,
            cta_label=cta_label,
            cta_url=cta_url,
        )
        if not result.get("ok"):
            raise TelegramPublishError(str(result.get("error") or "Unknown Telegram API error."))
        return TelegramPublishResult(
            success=True,
            post_to=str(result.get("post_to") or post_to or "main").strip().lower(),
            provider_post_id=str(result.get("message_id") or "") or None,
            message="Posted to Telegram.",
            metadata={key: value for key, value in result.items() if key != "ok"},
        )

    @staticmethod
    def load_telegram_env() -> dict[str, str]:
        return {
            "bot_token": str(settings.TELEGRAM_BOT_TOKEN_AVA or "").strip(),
            "main_chat_id": (
                str(settings.TELEGRAM_CHAT_ID_AVA or "").strip()
                or str(settings.TELEGRAM_CHANNEL_ID or "").strip()
            ),
            "vault_chat_id": str(settings.TELEGRAM_VAULT_CHANNEL_ID or "").strip(),
            "content_vault_url": str(settings.TELEGRAM_CONTENT_VAULT_URL or "").strip(),
            "main_channel_url": str(settings.TELEGRAM_MAIN_CHANNEL_URL or "").strip(),
            "ava_chat_url": str(settings.TELEGRAM_AVA_CHAT_URL or "").strip(),
            "dmgate_url": str(settings.DMGATE_URL_AVA or "").strip(),
            "fanvue_url": str(settings.AVA_FANVUE_URL or "").strip(),
        }

    @staticmethod
    def get_chat_id(config: Mapping[str, str], post_to: str | None) -> str:
        normalized_post_to = (post_to or "main").strip().lower()
        if normalized_post_to == "vault":
            return str(config["vault_chat_id"])
        if normalized_post_to == "main":
            return str(config["main_chat_id"])
        raise TelegramPublishError(f"Unknown Telegram post target: {post_to}")

    @staticmethod
    def build_inline_keyboard(
        *,
        cta_enabled: bool = False,
        cta_label: str = "",
        cta_url: str = "",
    ) -> Mapping[str, Any] | None:
        if not cta_enabled:
            return None
        label = (cta_label or "").strip()
        url = (cta_url or "").strip()
        if not label:
            raise TelegramPublishError("CTA button text is required when CTA is enabled.")
        if not url:
            raise TelegramPublishError("CTA button URL is required when CTA is enabled.")
        if not url.startswith(("http://", "https://", "tg://")):
            raise TelegramPublishError("CTA URL must start with http://, https://, or tg://.")
        return {"inline_keyboard": [[{"text": label, "url": url}]]}

    def prepare_telegram_photo(self, image_path: str | Path) -> Path:
        source_path = Path(image_path)
        if not source_path.exists():
            raise TelegramPublishError(f"Image file does not exist: {source_path}")

        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            if image.mode in ("RGBA", "LA") or (image.mode == "P" and "transparency" in image.info):
                background = Image.new("RGB", image.size, "white")
                alpha = image.convert("RGBA").getchannel("A")
                background.paste(image.convert("RGBA"), mask=alpha)
                image = background
            else:
                image = image.convert("RGB")

            width, height = image.size
            scale = min(
                TELEGRAM_IMAGE_MAX_SIDE / max(width, height),
                TELEGRAM_IMAGE_MAX_TOTAL_DIMENSIONS / (width + height),
                1.0,
            )
            if scale < 1.0:
                image = image.resize(
                    (max(1, int(width * scale)), max(1, int(height * scale))),
                    Image.Resampling.LANCZOS,
                )

            width, height = image.size
            if max(width, height) / max(1, min(width, height)) > 20:
                if width > height:
                    new_height = max(1, int(width / 20))
                    canvas = Image.new("RGB", (width, new_height), "white")
                    canvas.paste(image, (0, (new_height - height) // 2))
                else:
                    new_width = max(1, int(height / 20))
                    canvas = Image.new("RGB", (new_width, height), "white")
                    canvas.paste(image, ((new_width - width) // 2, 0))
                image = canvas

            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix="_telegram.jpg")
            temp_path = Path(temp_file.name)
            temp_file.close()
            image.save(temp_path, "JPEG", quality=92, optimize=True)
        return temp_path

    @staticmethod
    def parse_telegram_response(response) -> dict[str, Any]:
        if response.status_code != 200:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": response.text[:1000],
            }
        try:
            payload = response.json()
        except ValueError:
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": "Telegram returned a non-JSON response.",
                "raw_response": response.text[:1000],
            }
        if not payload.get("ok"):
            return {
                "ok": False,
                "status_code": response.status_code,
                "error": payload.get("description", "Telegram API returned ok=false."),
                "response": payload,
            }
        return {
            "ok": True,
            "status_code": response.status_code,
            "message_id": payload.get("result", {}).get("message_id"),
            "response": payload,
        }

    def publish_to_telegram(
        self,
        *,
        image_reference: str | None = None,
        caption: str = "",
        post_to: str = "main",
        cta_enabled: bool = False,
        cta_label: str = "",
        cta_url: str = "",
    ) -> dict[str, Any]:
        config = self.load_telegram_env()
        temp_image_path: Path | None = None
        local_source: Path | None = None
        try:
            if not config["bot_token"]:
                raise TelegramPublishError("Telegram bot token is not configured.")
            chat_id = self.get_chat_id(config, post_to)
            if not chat_id:
                if (post_to or "main").strip().lower() == "vault":
                    raise TelegramPublishError("Telegram vault channel is not configured.")
                raise TelegramPublishError("Telegram main chat or channel is not configured.")
            reply_markup = self.build_inline_keyboard(
                cta_enabled=cta_enabled,
                cta_label=cta_label,
                cta_url=cta_url,
            )
            data = {"chat_id": chat_id, "parse_mode": "HTML"}
            if reply_markup:
                data["reply_markup"] = json.dumps(reply_markup)
            normalized_caption = (caption or "").strip()
            if image_reference:
                local_source = self._materialize_image_reference(image_reference)
                temp_image_path = self.prepare_telegram_photo(local_source)
                data["caption"] = normalized_caption
                with open(temp_image_path, "rb") as photo:
                    response = self.http_client.post(
                        f"https://api.telegram.org/bot{config['bot_token']}/sendPhoto",
                        data=data,
                        files={"photo": photo},
                        timeout=TELEGRAM_API_TIMEOUT,
                    )
            else:
                if not normalized_caption and not reply_markup:
                    raise TelegramPublishError("Caption-only Telegram posts require caption text or a CTA.")
                data["text"] = normalized_caption
                response = self.http_client.post(
                    f"https://api.telegram.org/bot{config['bot_token']}/sendMessage",
                    data=data,
                    timeout=TELEGRAM_API_TIMEOUT,
                )
            result = self.parse_telegram_response(response)
            result["post_to"] = (post_to or "main").strip().lower()
            return result
        except Exception as error:
            return {
                "ok": False,
                "error": str(error),
                "post_to": (post_to or "main").strip().lower(),
            }
        finally:
            if temp_image_path:
                temp_image_path.unlink(missing_ok=True)
            if local_source and local_source.parent.name.startswith("creator_os_telegram_"):
                local_source.unlink(missing_ok=True)

    def _materialize_image_reference(self, image_reference: str | Path) -> Path:
        reference = str(image_reference or "").strip()
        if not reference:
            raise TelegramPublishError("Generated image reference is required.")
        parsed = urlparse(reference)
        if parsed.scheme in {"http", "https"}:
            suffix = Path(parsed.path).suffix or ".jpg"
            temp_dir = Path(tempfile.mkdtemp(prefix="creator_os_telegram_"))
            target = temp_dir / f"generated{suffix}"
            response = self.http_client.get(reference, timeout=120, headers={"User-Agent": "Creator-OS"})
            response.raise_for_status()
            target.write_bytes(response.content)
            return target
        path = Path(reference).expanduser()
        if not path.exists():
            raise TelegramPublishError(f"Generated image was not found: {reference}")
        return path
