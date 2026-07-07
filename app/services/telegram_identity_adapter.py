"""Temporary, in-memory Telegram-to-engine identity compatibility adapter."""

from app.models.telegram_identity import (
    TelegramMvpIdentityInput,
    TelegramMvpIdentityOutput,
)


POSTGRES_BIGINT_MAX = (2**63) - 1
POSTGRES_BIGINT_MIN = -(2**63)


class InvalidTelegramMvpIdentityError(ValueError):
    """The supplied identifier cannot be represented by the MVP strategy."""


class TelegramIdentityAdapter:
    """Map an opaque Telegram user ID into the legacy engine namespace."""

    def __init__(self, *, engine_account_id: int) -> None:
        self._validate_positive_bigint(
            "engine_account_id",
            engine_account_id,
        )
        self._engine_account_id = engine_account_id

    def adapt(
        self,
        identity: TelegramMvpIdentityInput,
    ) -> TelegramMvpIdentityOutput:
        if not isinstance(identity, TelegramMvpIdentityInput):
            raise InvalidTelegramMvpIdentityError(
                "identity must be a TelegramMvpIdentityInput."
            )

        self._validate_positive_bigint(
            "telegram_user_id",
            identity.telegram_user_id,
        )
        self._validate_optional_chat_id(identity.telegram_chat_id)

        temporary_legacy_user_id = -identity.telegram_user_id
        return TelegramMvpIdentityOutput(
            engine_user_id=(
                f"{self._engine_account_id}:"
                f"{temporary_legacy_user_id}"
            )
        )

    @staticmethod
    def _validate_positive_bigint(name: str, value: int) -> None:
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value <= 0
            or value > POSTGRES_BIGINT_MAX
        ):
            raise InvalidTelegramMvpIdentityError(
                f"{name} must be a positive signed 64-bit integer."
            )

    @staticmethod
    def _validate_optional_chat_id(value: int | None) -> None:
        if value is None:
            return
        if (
            isinstance(value, bool)
            or not isinstance(value, int)
            or value == 0
            or value < POSTGRES_BIGINT_MIN
            or value > POSTGRES_BIGINT_MAX
        ):
            raise InvalidTelegramMvpIdentityError(
                "telegram_chat_id must be a non-zero signed 64-bit "
                "integer when provided."
            )
