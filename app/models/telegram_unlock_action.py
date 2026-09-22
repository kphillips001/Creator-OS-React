"""Trusted UNLOCK semantics, independent of Telegram keyboard support."""
from dataclasses import dataclass
import os
import re
from urllib.parse import urlsplit

from app.models.telegram_transport_contract import TelegramPreflightError


def utf16_length(text):
    return len(text.encode('utf-16-le')) // 2


def validate_unlock_destination(destination):
    from app.services.customer_facing_commerce_url_service import require_public_commerce_origin
    origin = require_public_commerce_origin(os.getenv('CREATOR_OS_PUBLIC_API_URL'))
    try:
        expected = urlsplit(origin)
        actual = urlsplit(destination)
        valid = (actual.scheme == 'https' and actual.netloc == expected.netloc
                 and not actual.username and not actual.password
                 and not actual.query and not actual.fragment
                 and re.fullmatch(r'/u/[A-Za-z0-9_-]{22}', actual.path)
                 and destination == origin + actual.path)
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise TelegramPreflightError('Unlock requires the canonical first-party alias.')
    return destination


def validate_unlock_entities(text, entities):
    if not isinstance(entities, list) or len(entities) != 1:
        raise TelegramPreflightError('Exactly one trusted Unlock entity is required.')
    entity = entities[0]
    if not isinstance(entity, dict) or set(entity) != {'type', 'offset', 'length', 'url'}:
        raise TelegramPreflightError('Malformed Unlock entity.')
    if (entity['type'] != 'text_url' or type(entity['offset']) is not int
            or type(entity['length']) is not int or entity['length'] != 6
            or not text.endswith('\n\nUnlock')
            or entity['offset'] != utf16_length(text[:-6])):
        raise TelegramPreflightError('Malformed Unlock entity offsets or label.')
    validate_unlock_destination(entity['url'])
    if utf16_length(text) > 1024:
        raise TelegramPreflightError('Telegram caption exceeds 1024 UTF-16 units.')


@dataclass(frozen=True)
class TelegramUnlockAction:
    destination: str
    semantic: str = 'UNLOCK'

    def render(self, caption, *, transport, button_label):
        validate_unlock_destination(self.destination)
        from app.models.telegram_offer_caption import telegram_offer_caption
        caption = telegram_offer_caption(caption)
        if transport in {'TELEGRAM_BUSINESS','BOT_API'}:
            return {'message_text': caption, 'button_label': button_label,
                    'button_url': self.destination}
        if transport != 'TELETHON':
            raise TelegramPreflightError('No supported Unlock rendering.')
        final = caption + '\n\nUnlock'
        entities = [{'type': 'text_url', 'offset': utf16_length(caption + '\n\n'),
                     'length': 6, 'url': self.destination}]
        validate_unlock_entities(final, entities)
        return {'message_text': final, 'caption_entities': entities}
