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

        mapping = self.repository.get_by_telegram_user_id(
            telegram_user_id,
            include_inactive=True,
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
