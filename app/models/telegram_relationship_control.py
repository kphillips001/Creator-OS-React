from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from uuid import UUID


class TelegramRelationshipMode(str, Enum):
    AVA_AUTO = "AVA_AUTO"
    HUMAN_OPERATOR = "HUMAN_OPERATOR"


class TelegramCommunicationDisposition(str, Enum):
    ACTIVE = "ACTIVE"
    IGNORED = "IGNORED"


@dataclass(frozen=True)
class TelegramRelationshipControl:
    relationship_control_id: UUID | None
    creator_profile_id: int
    fanvue_account_id: int
    telegram_user_id: int
    telegram_chat_id: int
    mode: TelegramRelationshipMode
    control_version: int
    changed_at: datetime | None = None
    changed_by: str = "SYSTEM_DEFAULT"
    reason: str | None = None
    last_manual_activity_at: datetime | None = None
    telegram_identity_mapping_id: int | None = None
    local_fanvue_user_id: int | None = None
    content_selling_enabled: bool = True
    session_selling_enabled: bool = True
    communication_disposition: TelegramCommunicationDisposition = TelegramCommunicationDisposition.ACTIVE
    ignore_version: int = 0
    ignored_at: datetime | None = None
    ignored_by: str | None = None
    ignore_reason: str | None = None
    unignored_at: datetime | None = None
    unignored_by: str | None = None
    resume_after_inbound_message_id: int | None = None

    @property
    def manual(self):
        return self.mode is TelegramRelationshipMode.HUMAN_OPERATOR

    @property
    def ignored(self):
        return self.communication_disposition is TelegramCommunicationDisposition.IGNORED
