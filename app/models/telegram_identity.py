from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping
from uuid import UUID


@dataclass(frozen=True)
class TelegramMvpIdentityInput:
    """Opaque Telegram identifiers accepted by the temporary MVP adapter."""

    telegram_user_id: int
    telegram_chat_id: int | None = None


@dataclass(frozen=True)
class TelegramMvpIdentityOutput:
    """Existing-brain compatibility identity produced for the MVP."""

    engine_user_id: str


@dataclass(frozen=True)
class TelegramIdentityMapping:
    """A Telegram identity linked to one existing Fanvue user."""

    id: int | None
    telegram_user_id: int
    telegram_chat_id: int
    fanvue_account_id: int
    local_fanvue_user_id: int
    external_fanvue_user_uuid: UUID
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    verification_status: str = "UNVERIFIED"
    verification_method: str | None = None
    verified_at: datetime | None = None
    verified_by: str | None = None
    last_observed_username: str | None = None
    last_observed_display_name: str | None = None

    @property
    def engine_user_id(self) -> str:
        return (
            f"{self.fanvue_account_id}:"
            f"{self.local_fanvue_user_id}"
        )

    @classmethod
    def from_row(
        cls,
        row: Mapping[str, Any],
    ) -> "TelegramIdentityMapping":
        return cls(
            id=row.get("id"),
            telegram_user_id=int(row["telegram_user_id"]),
            telegram_chat_id=int(row["telegram_chat_id"]),
            fanvue_account_id=int(row["fanvue_account_id"]),
            local_fanvue_user_id=int(
                row["local_fanvue_user_id"]
            ),
            external_fanvue_user_uuid=UUID(
                str(row["external_fanvue_user_uuid"])
            ),
            is_active=bool(row.get("is_active", True)),
            created_at=row.get("created_at"),
            updated_at=row.get("updated_at"),
            verification_status=str(row.get("verification_status") or "UNVERIFIED"),
            verification_method=row.get("verification_method"),
            verified_at=row.get("verified_at"), verified_by=row.get("verified_by"),
            last_observed_username=row.get("last_observed_username"),
            last_observed_display_name=row.get("last_observed_display_name"),
        )


@dataclass(frozen=True)
class CanonicalTelegramIdentity:
    """Validated identity contract consumed by a future transport layer."""

    telegram_user_id: int
    telegram_chat_id: int
    fanvue_account_id: int
    local_fanvue_user_id: int
    external_fanvue_user_uuid: UUID
    engine_user_id: str

    @classmethod
    def from_mapping(
        cls,
        mapping: TelegramIdentityMapping,
    ) -> "CanonicalTelegramIdentity":
        return cls(
            telegram_user_id=mapping.telegram_user_id,
            telegram_chat_id=mapping.telegram_chat_id,
            fanvue_account_id=mapping.fanvue_account_id,
            local_fanvue_user_id=(
                mapping.local_fanvue_user_id
            ),
            external_fanvue_user_uuid=(
                mapping.external_fanvue_user_uuid
            ),
            engine_user_id=mapping.engine_user_id,
        )
