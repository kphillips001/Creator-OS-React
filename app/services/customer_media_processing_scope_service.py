"""Fail-closed authority for entering the Telegram customer-image pipeline."""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from enum import Enum


def _enabled(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _positive_int(value: object) -> int | None:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


class CustomerMediaProcessingMode(str, Enum):
    ONLY_CONTROLLED_IDENTITY = "ONLY_CONTROLLED_IDENTITY"
    NORMAL_PRODUCTION = "NORMAL_PRODUCTION"


@dataclass(frozen=True)
class CustomerMediaProcessingScopeDecision:
    allowed: bool
    mode: str
    reason: str
    identity_fingerprint: str | None = None


class CustomerMediaProcessingScopeService:
    """Authorize processing from numeric Telegram identity and explicit mode."""

    MODE_ENV = "TELEGRAM_CUSTOMER_IMAGE_SCOPE_MODE"
    SAFETY_ENV = "TELEGRAM_CUSTOMER_IMAGE_SAFETY_ENABLED"
    RESPONSE_ENV = "TELEGRAM_CUSTOMER_IMAGE_RESPONSE_ENABLED"
    CONTROLLED_ENV = "CONTROLLED_AUTONOMY_TEST_ENABLED"
    USER_ENV = "CONTROLLED_AUTONOMY_TELEGRAM_USER_ID"
    CHAT_ENV = "CONTROLLED_AUTONOMY_TELEGRAM_CHAT_ID"

    def audit_metadata(self) -> dict[str, object]:
        user_id = _positive_int(os.getenv(self.USER_ENV))
        chat_id = _positive_int(os.getenv(self.CHAT_ENV))
        fingerprint = (hashlib.sha256(f"{user_id}:{chat_id}".encode()).hexdigest()[:12]
                       if user_id is not None and chat_id is not None else None)
        return {
            "customer_image_scope_mode": str(os.getenv(self.MODE_ENV) or CustomerMediaProcessingMode.ONLY_CONTROLLED_IDENTITY.value).strip().upper(),
            "customer_image_safety_enabled": _enabled(os.getenv(self.SAFETY_ENV)),
            "customer_image_response_enabled": _enabled(os.getenv(self.RESPONSE_ENV)),
            "customer_image_controlled_identity_valid": fingerprint is not None,
            "customer_image_controlled_identity_fingerprint": fingerprint,
        }

    def decide(self, *, telegram_user_id: object, telegram_chat_id: object) -> CustomerMediaProcessingScopeDecision:
        safety = _enabled(os.getenv(self.SAFETY_ENV))
        response = _enabled(os.getenv(self.RESPONSE_ENV))
        mode = str(os.getenv(self.MODE_ENV) or CustomerMediaProcessingMode.ONLY_CONTROLLED_IDENTITY.value).strip().upper()
        if not safety and not response:
            return CustomerMediaProcessingScopeDecision(False, mode, "IMAGE_FEATURE_DISABLED")
        if response and not safety:
            return CustomerMediaProcessingScopeDecision(False, mode, "IMAGE_FEATURE_CONFIGURATION_INVALID")
        if mode == CustomerMediaProcessingMode.NORMAL_PRODUCTION.value:
            if _enabled(os.getenv(self.CONTROLLED_ENV)):
                return CustomerMediaProcessingScopeDecision(False, mode, "CONTROLLED_MODE_CONFLICT")
            return CustomerMediaProcessingScopeDecision(True, mode, "NORMAL_PRODUCTION_AUTHORIZED")
        if mode != CustomerMediaProcessingMode.ONLY_CONTROLLED_IDENTITY.value:
            return CustomerMediaProcessingScopeDecision(False, mode, "IMAGE_SCOPE_MODE_INVALID")
        if not _enabled(os.getenv(self.CONTROLLED_ENV)):
            return CustomerMediaProcessingScopeDecision(False, mode, "CONTROLLED_TEST_DISABLED")
        configured_user = _positive_int(os.getenv(self.USER_ENV))
        configured_chat = _positive_int(os.getenv(self.CHAT_ENV))
        current_user = _positive_int(telegram_user_id)
        current_chat = _positive_int(telegram_chat_id)
        if configured_user is None or configured_chat is None:
            return CustomerMediaProcessingScopeDecision(False, mode, "CONTROLLED_IDENTITY_INVALID")
        fingerprint = hashlib.sha256(f"{configured_user}:{configured_chat}".encode()).hexdigest()[:12]
        if current_user is None or current_chat is None:
            return CustomerMediaProcessingScopeDecision(False, mode, "EVENT_IDENTITY_INVALID", fingerprint)
        if (current_user, current_chat) != (configured_user, configured_chat):
            return CustomerMediaProcessingScopeDecision(False, mode, "CONTROLLED_SCOPE_NOT_AUTHORIZED", fingerprint)
        return CustomerMediaProcessingScopeDecision(True, mode, "CONTROLLED_SCOPE_AUTHORIZED", fingerprint)
