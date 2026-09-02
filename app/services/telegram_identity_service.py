from uuid import UUID

from app.models.telegram_identity import (
    CanonicalTelegramIdentity,
    TelegramIdentityMapping,
)
from app.repositories.telegram_identity_repository import (
    TelegramIdentityConflictError,
    TelegramIdentityIntegrityError,
    TelegramIdentityRepository,
)


class TelegramIdentityError(Exception):
    """Base error for Telegram identity operations."""


class TelegramIdentityNotFoundError(TelegramIdentityError):
    """No Telegram identity mapping exists."""


class InactiveTelegramIdentityError(TelegramIdentityError):
    """The Telegram identity exists but is inactive."""


class DuplicateTelegramIdentityError(TelegramIdentityError):
    """A Telegram or canonical identity is already mapped."""


class InvalidTelegramIdentityError(TelegramIdentityError):
    """The supplied identity values are invalid or inconsistent."""


class UnverifiedTelegramIdentityError(TelegramIdentityError):
    """The identity link has not been verified for commerce use."""


class TelegramIdentityService:
    """Validates and resolves Telegram identities to canonical users."""

    def __init__(
        self,
        repository: TelegramIdentityRepository | None = None,
    ):
        self.repository = repository or TelegramIdentityRepository()

    def resolve_telegram_identity(
        self,
        telegram_user_id: int,
    ) -> CanonicalTelegramIdentity:
        self._require_positive_integer(
            "telegram_user_id",
            telegram_user_id,
        )

        verified_reader = getattr(
            self.repository, "get_verified_by_telegram_user_id", None
        )
        mapping = (
            verified_reader(telegram_user_id)
            if callable(verified_reader)
            else self.repository.get_by_telegram_user_id(
                telegram_user_id, include_inactive=True,
            )
        )

        if mapping is None and callable(verified_reader):
            mapping = self.repository.get_by_telegram_user_id(
                telegram_user_id, include_inactive=True,
            )

        if not mapping:
            raise TelegramIdentityNotFoundError(
                f"No mapping exists for Telegram user {telegram_user_id}."
            )

        if not mapping.is_active:
            raise InactiveTelegramIdentityError(
                f"Telegram user {telegram_user_id} is inactive."
            )

        self.validate_mapping(mapping)
        return CanonicalTelegramIdentity.from_mapping(mapping)

    def observe(self, *, telegram_user_id: int, telegram_chat_id: int,
                username: str | None = None, display_name: str | None = None):
        self._require_positive_integer("telegram_user_id", telegram_user_id)
        self._require_nonzero_integer("telegram_chat_id", telegram_chat_id)
        return self.repository.observe(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            username=self._metadata(username), display_name=self._metadata(display_name),
        )

    def verify_operator_mapping(
        self, *, telegram_user_id: int, fanvue_account_id: int,
        local_fanvue_user_id: int, verification_note: str,
        operator_source: str = "CREATOR_OS_OPERATIONS",
    ):
        self._require_positive_integer("telegram_user_id", telegram_user_id)
        self._require_positive_integer("fanvue_account_id", fanvue_account_id)
        self._require_positive_integer("local_fanvue_user_id", local_fanvue_user_id)
        note = str(verification_note or "").strip()
        if len(note) < 10 or len(note) > 500:
            raise InvalidTelegramIdentityError(
                "Verification evidence must be between 10 and 500 characters."
            )
        try:
            return self.repository.create_verified_mapping(
                telegram_user_id=telegram_user_id,
                fanvue_account_id=fanvue_account_id,
                local_fanvue_user_id=local_fanvue_user_id,
                verification_method="OPERATOR_CONFIRMED_PROVIDER_IDENTITIES",
                operator_source=operator_source,
                evidence={"operator_note": note},
            )
        except TelegramIdentityConflictError as error:
            raise DuplicateTelegramIdentityError(str(error)) from error
        except TelegramIdentityIntegrityError as error:
            raise InvalidTelegramIdentityError(str(error)) from error

    def readiness(self, *, fanvue_account_id: int):
        counts, rows = self.repository.readiness(
            fanvue_account_id=fanvue_account_id
        )
        return {
            "counts": {key: int(value or 0) for key, value in counts.items()},
            "items": [{
                "telegramUserIdMasked": self._mask(row["telegram_user_id"]),
                "telegramUserId": str(row["telegram_user_id"]),
                "displayName": row.get("display_name") or row.get("username") or "Telegram customer",
                "status": (
                    "UNMAPPED" if row.get("mapping_id") is None
                    else "MAPPED" if row.get("verification_status") == "VERIFIED" and row.get("is_active")
                    else "CONFLICT" if row.get("verification_status") == "CONFLICT"
                    else "INCOMPLETE"
                ),
                "lastObservedAt": row.get("last_observed_at"),
            } for row in rows],
            "fanvueCandidates": [{
                "localFanvueUserId": int(row["id"]),
                "displayName": row.get("display_name") or row.get("username") or "Fanvue customer",
                "fanvueBuyerId": str(row["fanvue_user_uuid"]),
                "fanvueBuyerIdMasked": self._mask_uuid(row["fanvue_user_uuid"]),
            } for row in self.repository.list_fanvue_candidates(
                fanvue_account_id=fanvue_account_id
            )],
        }

    def create_mapping(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID | str,
    ) -> TelegramIdentityMapping:
        normalized_uuid = self._validate_values(
            telegram_user_id=telegram_user_id,
            telegram_chat_id=telegram_chat_id,
            fanvue_account_id=fanvue_account_id,
            local_fanvue_user_id=local_fanvue_user_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
        )

        existing_telegram = (
            self.repository.get_by_telegram_user_id(
                telegram_user_id,
                include_inactive=True,
            )
        )
        if existing_telegram:
            raise DuplicateTelegramIdentityError(
                f"Telegram user {telegram_user_id} is already mapped."
            )

        existing_canonical = (
            self.repository.get_by_local_user_id(
                fanvue_account_id,
                local_fanvue_user_id,
                include_inactive=True,
            )
        )
        if existing_canonical:
            raise DuplicateTelegramIdentityError(
                "The canonical Fanvue user is already mapped to "
                "a Telegram identity."
            )

        try:
            mapping = self.repository.create_mapping(
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
                fanvue_account_id=fanvue_account_id,
                local_fanvue_user_id=local_fanvue_user_id,
                external_fanvue_user_uuid=normalized_uuid,
            )
        except TelegramIdentityConflictError as error:
            raise DuplicateTelegramIdentityError(str(error)) from error
        except TelegramIdentityIntegrityError as error:
            raise InvalidTelegramIdentityError(str(error)) from error

        self.validate_mapping(mapping)
        return mapping

    def update_mapping(
        self,
        *,
        mapping_id: int,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID | str,
        is_active: bool = True,
    ) -> TelegramIdentityMapping:
        self._require_positive_integer("mapping_id", mapping_id)
        if not isinstance(is_active, bool):
            raise InvalidTelegramIdentityError(
                "is_active must be a boolean."
            )

        normalized_uuid = self._validate_canonical_values(
            telegram_chat_id=telegram_chat_id,
            fanvue_account_id=fanvue_account_id,
            local_fanvue_user_id=local_fanvue_user_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
        )

        current = self.repository.get_by_id(mapping_id)
        if not current:
            raise TelegramIdentityNotFoundError(
                f"No mapping exists with ID {mapping_id}."
            )

        other_mapping = self.repository.get_by_local_user_id(
            fanvue_account_id,
            local_fanvue_user_id,
            include_inactive=True,
        )
        if other_mapping and other_mapping.id != mapping_id:
            raise DuplicateTelegramIdentityError(
                "The canonical Fanvue user is already mapped to "
                "a different Telegram identity."
            )

        try:
            mapping = self.repository.update_mapping(
                mapping_id=mapping_id,
                telegram_chat_id=telegram_chat_id,
                fanvue_account_id=fanvue_account_id,
                local_fanvue_user_id=local_fanvue_user_id,
                external_fanvue_user_uuid=normalized_uuid,
                is_active=is_active,
            )
        except TelegramIdentityConflictError as error:
            raise DuplicateTelegramIdentityError(str(error)) from error
        except TelegramIdentityIntegrityError as error:
            raise InvalidTelegramIdentityError(str(error)) from error

        if not mapping:
            raise InvalidTelegramIdentityError(
                "The supplied Fanvue identifiers do not identify "
                "the same existing user."
            )

        self.validate_mapping(mapping)
        return mapping

    def deactivate_mapping(
        self,
        mapping_id: int,
    ) -> TelegramIdentityMapping:
        self._require_positive_integer("mapping_id", mapping_id)
        mapping = self.repository.deactivate_mapping(mapping_id)

        if not mapping:
            raise TelegramIdentityNotFoundError(
                f"No mapping exists with ID {mapping_id}."
            )

        return mapping

    @staticmethod
    def validate_mapping(
        mapping: TelegramIdentityMapping,
    ) -> None:
        normalized_uuid = TelegramIdentityService._validate_values(
            telegram_user_id=mapping.telegram_user_id,
            telegram_chat_id=mapping.telegram_chat_id,
            fanvue_account_id=mapping.fanvue_account_id,
            local_fanvue_user_id=mapping.local_fanvue_user_id,
            external_fanvue_user_uuid=(
                mapping.external_fanvue_user_uuid
            ),
        )

        expected_engine_user_id = (
            f"{mapping.fanvue_account_id}:"
            f"{mapping.local_fanvue_user_id}"
        )
        if mapping.engine_user_id != expected_engine_user_id:
            raise InvalidTelegramIdentityError(
                "The canonical engine identity is inconsistent."
            )

        if mapping.external_fanvue_user_uuid != normalized_uuid:
            raise InvalidTelegramIdentityError(
                "The external Fanvue UUID is not normalized."
            )

    @staticmethod
    def _validate_values(
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID | str,
    ) -> UUID:
        TelegramIdentityService._require_positive_integer(
            "telegram_user_id",
            telegram_user_id,
        )
        return TelegramIdentityService._validate_canonical_values(
            telegram_chat_id=telegram_chat_id,
            fanvue_account_id=fanvue_account_id,
            local_fanvue_user_id=local_fanvue_user_id,
            external_fanvue_user_uuid=external_fanvue_user_uuid,
        )

    @staticmethod
    def _validate_canonical_values(
        *,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID | str,
    ) -> UUID:
        TelegramIdentityService._require_nonzero_integer(
            "telegram_chat_id",
            telegram_chat_id,
        )
        TelegramIdentityService._require_positive_integer(
            "fanvue_account_id",
            fanvue_account_id,
        )
        TelegramIdentityService._require_positive_integer(
            "local_fanvue_user_id",
            local_fanvue_user_id,
        )

        try:
            return (
                external_fanvue_user_uuid
                if isinstance(external_fanvue_user_uuid, UUID)
                else UUID(str(external_fanvue_user_uuid).strip())
            )
        except (AttributeError, TypeError, ValueError) as error:
            raise InvalidTelegramIdentityError(
                "external_fanvue_user_uuid must be a valid UUID."
            ) from error

    @staticmethod
    def _require_positive_integer(name: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
            raise InvalidTelegramIdentityError(
                f"{name} must be a positive integer."
            )

    @staticmethod
    def _require_nonzero_integer(name: str, value: int) -> None:
        if isinstance(value, bool) or not isinstance(value, int) or value == 0:
            raise InvalidTelegramIdentityError(
                f"{name} must be a non-zero integer."
            )

    @staticmethod
    def _metadata(value):
        text = str(value or "").strip()
        return text[:200] or None

    @staticmethod
    def _mask(value):
        text = str(value)
        return "***" + text[-4:]

    @staticmethod
    def _mask_uuid(value):
        text = str(value)
        return text[:4] + "…" + text[-4:]
