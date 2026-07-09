"""Social publishing provider boundary."""

from app.providers.social.x_provider import XAccount, XPublishResult, XPublishingProvider
from app.providers.social.telegram_provider import (
    TelegramPublishError,
    TelegramPublishResult,
    TelegramPublishingProvider,
)

__all__ = (
    "TelegramPublishError",
    "TelegramPublishResult",
    "TelegramPublishingProvider",
    "XAccount",
    "XPublishResult",
    "XPublishingProvider",
)
