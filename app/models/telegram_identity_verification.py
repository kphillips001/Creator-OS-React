from dataclasses import dataclass
from datetime import datetime
from uuid import UUID


@dataclass(frozen=True)
class TelegramIdentityVerificationChallenge:
    challenge_id: UUID
    telegram_user_id: int
    telegram_chat_id: int
    fanvue_account_id: int
    state: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None
    attempt_count: int = 0
    resulting_identity_mapping_id: int | None = None
    provider_fanvue_user_uuid: UUID | None = None
    already_pending: bool = False
    verification_code: str | None = None
    instruction: str | None = None
