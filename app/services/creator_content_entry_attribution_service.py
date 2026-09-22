"""Issue and observe opaque Telegram Broadcast Chat-entry attribution."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from uuid import NAMESPACE_URL, uuid5

from app.models.creator_content_entry_attribution import (
    CreatorContentEntryAttribution, CreatorContentEntryEvent,
)
from app.repositories.creator_content_entry_attribution_repository import CreatorContentEntryAttributionRepository


class CreatorContentEntryAttributionService:
    COMMAND = re.compile(r"^/start\s+cc_([A-Za-z0-9_-]{43})$")
    TOKEN_LIKE = re.compile(r"^/start\s+cc_", re.I)

    def __init__(self, *, repository=None, telegram_provider=None,
                 signing_secret: str | None = None, clock=lambda: datetime.now(UTC)):
        self.repository = repository or CreatorContentEntryAttributionRepository()
        self.telegram = telegram_provider
        self.secret = str(signing_secret or os.getenv("CREATOR_CONTENT_ATTRIBUTION_SECRET") or "")
        self.clock = clock

    def ensure_and_attach(self, *, publication, publish_item, chat_base_url: str,
                          cta_buttons: tuple[dict, ...]):
        if not any(str(button.get("identity") or "").upper() == "CHAT"
                   for button in cta_buttons):
            raise ValueError("A Chat CTA is required for publication attribution.")
        token = self._token(publication.publication_id)
        attribution_id = str(uuid5(NAMESPACE_URL,
            f"creator-os:content-entry:{publication.publication_id}"))
        attribution = self.repository.create_or_get(CreatorContentEntryAttribution(
            attribution_id=attribution_id,
            creator_profile_id=publication.creator_profile_id,
            publication_id=publication.publication_id,
            token_digest=self._digest(token), token_created_at=self.clock()))
        if not hmac.compare_digest(attribution.token_digest, self._digest(token)):
            raise ValueError("Attribution signing authority changed for an existing publication.")
        chat_url = self._chat_url(chat_base_url, token)
        buttons = tuple({**dict(button), "url": chat_url}
            if str(button.get("identity") or "").upper() == "CHAT" else dict(button)
            for button in cta_buttons)
        metadata = dict(publish_item.metadata or {})
        provider = dict(metadata.get("provider_metadata") or {})
        result = dict(dict(provider.get("response") or {}).get("result") or {})
        channel_id = int(dict(result.get("chat") or {}).get("id"))
        message_id = int(metadata.get("provider_post_id") or result.get("message_id"))
        if self.telegram is None:
            from app.providers.social.telegram_provider import TelegramPublishingProvider
            self.telegram = TelegramPublishingProvider()
        keyboard = self.telegram.build_inline_keyboard(cta_buttons=buttons)
        response = self.telegram.edit_message_reply_markup(
            chat_id=str(channel_id), message_id=message_id, reply_markup=keyboard)
        succeeded = bool(response.get("ok") and str(response.get("chat_id")) == str(channel_id)
                         and str(response.get("message_id")) == str(message_id)
                         and response.get("reply_markup") == keyboard)
        self.repository.mark_attachment(attribution.attribution_id, succeeded=succeeded,
            error_code=None if succeeded else response.get("error") or "CTA_IDENTITY_MISMATCH")
        return {"attributionId": attribution.attribution_id,
            "publicationId": publication.publication_id,
            "status": "CTA_ATTACHED" if succeeded else "CTA_ATTACHMENT_FAILED",
            "chatUrl": chat_url if succeeded else None}

    def observe_message(self, *, creator_profile_id: int, message_text: str,
                        telegram_user_id: int, telegram_chat_id: int,
                        inbound_telegram_message_id: int, observed_at=None):
        text = " ".join(str(message_text or "").split()).strip()
        match = self.COMMAND.fullmatch(text)
        if match is None:
            return {"disposition": "MALFORMED" if self.TOKEN_LIKE.match(text) else "NONE",
                    "entryObserved": False}
        token = match.group(1)
        attribution = self.repository.get_by_digest(self._digest(token))
        if attribution is None or attribution.creator_profile_id != int(creator_profile_id):
            return {"disposition": "UNKNOWN", "entryObserved": False}
        if not hmac.compare_digest(token, self._token(attribution.publication_id)):
            return {"disposition": "INVALID", "entryObserved": False}
        event_id = str(uuid5(NAMESPACE_URL, "creator-os:content-entry-event:"
            f"{attribution.attribution_id}:{telegram_user_id}:{telegram_chat_id}:{inbound_telegram_message_id}"))
        event = self.repository.observe(CreatorContentEntryEvent(
            entry_event_id=event_id, attribution_id=attribution.attribution_id,
            creator_profile_id=attribution.creator_profile_id,
            publication_id=attribution.publication_id,
            telegram_user_id=int(telegram_user_id), telegram_chat_id=int(telegram_chat_id),
            inbound_telegram_message_id=int(inbound_telegram_message_id),
            observed_at=observed_at or self.clock()))
        return {"disposition": "ENTRY_OBSERVED", "entryObserved": True,
            "entryEventId": event.entry_event_id, "attributionId": event.attribution_id,
            "publicationId": event.publication_id}

    def _token(self, publication_id: str):
        if len(self.secret.encode("utf-8")) < 32:
            raise ValueError("CREATOR_CONTENT_ATTRIBUTION_SECRET must contain at least 32 bytes.")
        digest = hmac.new(self.secret.encode("utf-8"),
            f"creator-content:{publication_id}".encode("utf-8"), hashlib.sha256).digest()
        return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")

    @staticmethod
    def _digest(token):
        return hashlib.sha256(str(token).encode("ascii")).hexdigest()

    @staticmethod
    def _chat_url(base_url, token):
        parsed = urlsplit(str(base_url or "").strip())
        if parsed.scheme not in {"http", "https"} or parsed.netloc.lower() not in {
            "t.me", "www.t.me", "telegram.me", "www.telegram.me"} or not parsed.path.strip("/"):
            raise ValueError("A canonical Telegram public-chat URL is required.")
        query = dict(parse_qsl(parsed.query, keep_blank_values=True))
        query["text"] = f"/start cc_{token}"
        return urlunsplit(("https", parsed.netloc, parsed.path, urlencode(query), ""))
