from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

from app.models.telegram_identity_verification import TelegramIdentityVerificationChallenge
from app.repositories.telegram_identity_verification_repository import TelegramIdentityVerificationRepository
from app.services.conversational_sales_progression_service import ConversationalSalesProgressionService


class TelegramIdentityVerificationService:
    FEATURE_FLAG = "TELEGRAM_FANVUE_DM_IDENTITY_VERIFICATION_ENABLED"
    CODE_PATTERN = re.compile(r"(?<![A-Z0-9])AVA-([23456789ABCDEFGHJKMNPQRSTUVWXYZ]{12})(?![A-Z0-9])", re.I)
    ALPHABET = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"

    def __init__(self, *, repository=None, clock=lambda: datetime.now(timezone.utc),
                 ttl=timedelta(minutes=15), intent_detector=None,
                 enabled: bool | None = None):
        self.repository = repository or TelegramIdentityVerificationRepository()
        self.clock = clock
        self.ttl = ttl
        self.intent_detector = intent_detector or ConversationalSalesProgressionService()
        self.enabled = (
            str(os.getenv(self.FEATURE_FLAG, "false")).strip().lower()
            in {"1", "true", "yes", "on"}
            if enabled is None else bool(enabled)
        )

    @staticmethod
    def _hash(code: str) -> str:
        return hashlib.sha256(code.upper().encode("ascii")).hexdigest()

    def should_start(self, message_text: str) -> bool:
        return self.enabled and self.intent_detector.has_direct_purchase_intent(message_text)

    def start(self, *, telegram_user_id: int, telegram_chat_id: int,
              fanvue_account_id: int) -> TelegramIdentityVerificationChallenge:
        if not self.enabled:
            raise RuntimeError("Fanvue DM identity verification is disabled.")
        pending = self.repository.pending(
            telegram_user_id=telegram_user_id, fanvue_account_id=fanvue_account_id
        )
        if pending:
            return self._model(
                pending, already_pending=True,
                instruction=("I already have a secure Fanvue link check waiting for you. "
                             "Send the AVA code from my earlier message to Ava on Fanvue."),
            )
        code = "AVA-" + "".join(secrets.choice(self.ALPHABET) for _ in range(12))
        row = self.repository.create(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            fanvue_account_id=fanvue_account_id,
            token_hash=self._hash(code),
            expires_at=self.clock() + self.ttl,
        )
        instruction = (
            f"Before I can share paid options here, send me this one-time code "
            f"in a DM on Fanvue: {code}. It expires in 15 minutes."
        )
        return self._model(row, verification_code=code, instruction=instruction)

    def complete_from_fanvue_message(self, *, fanvue_account_id: int,
                                      fanvue_user_uuid: UUID | str,
                                      message_text: str,
                                      provider_event_id: str):
        if not self.enabled:
            return {"status": "DISABLED"}
        match = self.CODE_PATTERN.search(str(message_text or "").upper())
        if match is None:
            return {"status": "NOT_A_CHALLENGE"}
        code = "AVA-" + match.group(1).upper()
        return self.repository.complete(
            fanvue_account_id=int(fanvue_account_id),
            fanvue_user_uuid=UUID(str(fanvue_user_uuid)),
            token_hash=self._hash(code),
            provider_event_id=str(provider_event_id),
        )

    @staticmethod
    def _model(row, **extra):
        return TelegramIdentityVerificationChallenge(
            challenge_id=UUID(str(row["challenge_id"])),
            telegram_user_id=int(row["telegram_user_id"]),
            telegram_chat_id=int(row["telegram_chat_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            state=str(row["state"]), created_at=row["created_at"],
            expires_at=row["expires_at"], consumed_at=row.get("consumed_at"),
            attempt_count=int(row.get("attempt_count") or 0),
            resulting_identity_mapping_id=row.get("resulting_identity_mapping_id"),
            provider_fanvue_user_uuid=row.get("provider_fanvue_user_uuid"),
            **extra,
        )
