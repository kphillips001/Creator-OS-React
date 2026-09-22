"""Content-neutral capabilities and acceptance certainty for Telegram delivery."""
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlsplit


class DeliveryCertainty(str, Enum):
    NOT_SENT = "NOT_SENT"
    REJECTED = "REJECTED"
    ACCEPTED = "ACCEPTED"
    UNKNOWN = "UNKNOWN"


class TelegramPreflightError(ValueError):
    certainty = DeliveryCertainty.NOT_SENT
    code = "TELEGRAM_ROUTE_UNAVAILABLE"


class TelegramPeerUnavailableError(TelegramPreflightError):
    """Definite pre-invocation recipient eligibility failure, not runtime health."""
    health_scope = "RECIPIENT_REACHABILITY"


@dataclass(frozen=True)
class TelegramRequirements:
    text: bool = True
    photo: bool = False
    caption: bool = False
    url_action: bool = False
    suppress_preview: bool = False
    sender_scope: str | None = None
    caption_text_url: bool = False

    @classmethod
    def from_send(cls, *, message_text="", asset_path=None, button_label=None,
                  button_url=None, disable_link_preview=False, sender_scope=None, caption_entities=None):
        if bool(button_label) != bool(button_url):
            raise TelegramPreflightError("A URL action requires both label and URL.")
        if button_url:
            url = urlsplit(button_url)
            if url.scheme not in {"https", "http"} or not url.netloc:
                raise TelegramPreflightError("URL actions require an absolute HTTP(S) URL.")
        if caption_entities is not None:
            from app.models.telegram_unlock_action import validate_unlock_entities
            if button_url or not asset_path:
                raise TelegramPreflightError("Caption action requires media and no keyboard.")
            validate_unlock_entities(message_text, caption_entities)
        return cls(bool(message_text) and not asset_path, bool(asset_path),
                   bool(message_text) and bool(asset_path), bool(button_url),
                   bool(disable_link_preview), sender_scope, caption_entities is not None)


@dataclass(frozen=True)
class TelegramReachability:
    transport: str
    sender_scope: str
    peer_id: int
    evidence_type: str
    observed_at: datetime
    business_connection_id: str | None = None
    sender_id: int | None = None

    def validate(self, requirements, *, now=None):
        now = now or datetime.now(timezone.utc)
        if self.peer_id <= 0 or self.observed_at.tzinfo is None:
            raise TelegramPreflightError("Invalid peer reachability evidence.")
        if self.observed_at > now + timedelta(seconds=5):
            raise TelegramPreflightError("Reachability evidence is in the future.")
        if requirements.sender_scope and requirements.sender_scope != self.sender_scope:
            raise TelegramPreflightError("Sender identity does not match required scope.")
        expected = {"BOT_API": {"BOT_INBOUND", "BOT_ACCEPTED"},
                    "TELEGRAM_BUSINESS": {"BUSINESS_INBOUND"},
                    "TELETHON": {"AUTHORIZED_SESSION_ENTITY"}}
        if self.evidence_type not in expected.get(self.transport, set()):
            raise TelegramPreflightError("Evidence belongs to a different transport.")
        if self.transport == "TELEGRAM_BUSINESS" and (
                not self.business_connection_id or now-self.observed_at >= timedelta(hours=24)):
            raise TelegramPeerUnavailableError("Business peer reply eligibility has expired.")
        if requirements.caption_text_url and self.transport != "TELETHON":
            raise TelegramPreflightError("Caption action requires the user-account renderer.")
        if self.transport == "TELETHON" and requirements.url_action:
            raise TelegramPreflightError("The user-account transport cannot send URL buttons.")


def payload_digest(values):
    return sha256(json.dumps(values, sort_keys=True, separators=(",", ":"),
                             default=str).encode()).hexdigest()


def validate_local_payload(values):
    text = values.get("message_text", "")
    media = values.get("asset_path")
    if not isinstance(text, str) or len(text) > (1024 if media else 4096):
        raise TelegramPreflightError("Telegram text/caption length is unsupported.")
    if not media and not text.strip():
        raise TelegramPreflightError("An outbound text message must not be empty.")
    if media and not Path(media).is_file():
        raise TelegramPreflightError("The local media file is unavailable.")
    if media and Path(media).suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
        raise TelegramPreflightError("This delivery contract supports still-image media only.")


def route_evidence(reachability, requirements, *, operation_id, attempt_id, payload):
    reachability.validate(requirements)
    return {"operation_id": str(operation_id), "provider_attempt_id": str(attempt_id),
            **asdict(reachability), "observed_at": reachability.observed_at.isoformat(),
            "required_capabilities": asdict(requirements), "payload_sha256": payload_digest(payload),
            "decision_at": datetime.now(timezone.utc).isoformat()}
