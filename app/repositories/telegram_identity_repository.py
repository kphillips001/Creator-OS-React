from collections.abc import Callable
from uuid import UUID

from psycopg import IntegrityError
from psycopg.errors import UniqueViolation

from app.database import get_db_connection
from app.models.telegram_identity import TelegramIdentityMapping


class TelegramIdentityRepositoryError(Exception):
    """Base persistence error for Telegram identity mappings."""


class TelegramIdentityConflictError(TelegramIdentityRepositoryError):
    """A database uniqueness constraint rejected the mapping."""


class TelegramIdentityIntegrityError(TelegramIdentityRepositoryError):
    """A database integrity constraint rejected the mapping."""


class TelegramIdentityRepository:
    """Persistence for Telegram-to-canonical-user mappings."""

    def __init__(
        self,
        connection_factory: Callable = get_db_connection,
    ):
        self._connection_factory = connection_factory

    def get_by_telegram_user_id(
        self,
        telegram_user_id: int,
        *,
        include_inactive: bool = False,
    ) -> TelegramIdentityMapping | None:
        active_filter = "" if include_inactive else "AND tim.is_active = TRUE"
        query = f"""
            SELECT tim.*
            FROM public.telegram_identity_map tim
            INNER JOIN public.fanvue_users fu
                ON fu.id = tim.local_fanvue_user_id
               AND fu.fanvue_account_id = tim.fanvue_account_id
               AND fu.fanvue_user_uuid =
                   tim.external_fanvue_user_uuid
            WHERE tim.telegram_user_id = %s
              {active_filter}
            LIMIT 1;
        """

        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (telegram_user_id,))
                row = cursor.fetchone()

        return self._to_mapping(row)

    def get_by_local_user_id(
        self,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        *,
        include_inactive: bool = False,
    ) -> TelegramIdentityMapping | None:
        active_filter = "" if include_inactive else "AND tim.is_active = TRUE"
        query = f"""
            SELECT tim.*
            FROM public.telegram_identity_map tim
            INNER JOIN public.fanvue_users fu
                ON fu.id = tim.local_fanvue_user_id
               AND fu.fanvue_account_id = tim.fanvue_account_id
               AND fu.fanvue_user_uuid =
                   tim.external_fanvue_user_uuid
            WHERE tim.fanvue_account_id = %s
              AND tim.local_fanvue_user_id = %s
              {active_filter}
            LIMIT 1;
        """

        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query,
                    (
                        fanvue_account_id,
                        local_fanvue_user_id,
                    ),
                )
                row = cursor.fetchone()

        return self._to_mapping(row)

    def get_by_id(
        self,
        mapping_id: int,
    ) -> TelegramIdentityMapping | None:
        query = """
            SELECT tim.*
            FROM public.telegram_identity_map tim
            INNER JOIN public.fanvue_users fu
                ON fu.id = tim.local_fanvue_user_id
               AND fu.fanvue_account_id = tim.fanvue_account_id
               AND fu.fanvue_user_uuid =
                   tim.external_fanvue_user_uuid
            WHERE tim.id = %s
            LIMIT 1;
        """

        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (mapping_id,))
                row = cursor.fetchone()

        return self._to_mapping(row)

    def create_mapping(
        self,
        *,
        telegram_user_id: int,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID,
    ) -> TelegramIdentityMapping:
        query = """
            INSERT INTO public.telegram_identity_map (
                telegram_user_id,
                telegram_chat_id,
                fanvue_account_id,
                local_fanvue_user_id,
                external_fanvue_user_uuid
            )
            SELECT
                %s,
                %s,
                fu.fanvue_account_id,
                fu.id,
                fu.fanvue_user_uuid
            FROM public.fanvue_users fu
            WHERE fu.fanvue_account_id = %s
              AND fu.id = %s
              AND fu.fanvue_user_uuid = %s
            RETURNING *;
        """

        try:
            with self._connection_factory() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        query,
                        (
                            telegram_user_id,
                            telegram_chat_id,
                            fanvue_account_id,
                            local_fanvue_user_id,
                            external_fanvue_user_uuid,
                        ),
                    )
                    row = cursor.fetchone()
        except UniqueViolation as error:
            raise TelegramIdentityConflictError(
                "The Telegram or canonical user is already mapped."
            ) from error
        except IntegrityError as error:
            raise TelegramIdentityIntegrityError(
                "The mapping violates canonical identity integrity."
            ) from error

        if not row:
            raise TelegramIdentityIntegrityError(
                "The Fanvue account, local user ID, and external "
                "Fanvue UUID do not identify the same existing user."
            )

        return TelegramIdentityMapping.from_row(row)

    def update_mapping(
        self,
        *,
        mapping_id: int,
        telegram_chat_id: int,
        fanvue_account_id: int,
        local_fanvue_user_id: int,
        external_fanvue_user_uuid: UUID,
        is_active: bool,
    ) -> TelegramIdentityMapping | None:
        query = """
            UPDATE public.telegram_identity_map tim
            SET
                telegram_chat_id = %s,
                fanvue_account_id = fu.fanvue_account_id,
                local_fanvue_user_id = fu.id,
                external_fanvue_user_uuid =
                    fu.fanvue_user_uuid,
                is_active = %s,
                updated_at = NOW()
            FROM public.fanvue_users fu
            WHERE tim.id = %s
              AND fu.fanvue_account_id = %s
              AND fu.id = %s
              AND fu.fanvue_user_uuid = %s
            RETURNING tim.*;
        """

        try:
            with self._connection_factory() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        query,
                        (
                            telegram_chat_id,
                            is_active,
                            mapping_id,
                            fanvue_account_id,
                            local_fanvue_user_id,
                            external_fanvue_user_uuid,
                        ),
                    )
                    row = cursor.fetchone()
        except UniqueViolation as error:
            raise TelegramIdentityConflictError(
                "The canonical user is already mapped."
            ) from error
        except IntegrityError as error:
            raise TelegramIdentityIntegrityError(
                "The mapping violates canonical identity integrity."
            ) from error

        return self._to_mapping(row)

    def deactivate_mapping(
        self,
        mapping_id: int,
    ) -> TelegramIdentityMapping | None:
        query = """
            UPDATE public.telegram_identity_map
            SET
                is_active = FALSE,
                updated_at = NOW()
            WHERE id = %s
            RETURNING *;
        """

        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(query, (mapping_id,))
                row = cursor.fetchone()

        return self._to_mapping(row)

    @staticmethod
    def _to_mapping(row) -> TelegramIdentityMapping | None:
        if not row:
            return None
        return TelegramIdentityMapping.from_row(row)
