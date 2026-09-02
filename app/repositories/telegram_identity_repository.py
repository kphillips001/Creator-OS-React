from collections.abc import Callable
from uuid import UUID
from uuid import uuid4
import json

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

    def get_verified_by_telegram_user_id(self, telegram_user_id: int):
        mapping = self.get_by_telegram_user_id(
            telegram_user_id, include_inactive=True
        )
        return mapping if mapping and mapping.is_active and (
            mapping.verification_status == "VERIFIED"
        ) else None

    def get_by_external_fanvue_user_uuid(
        self,
        fanvue_account_id: int,
        external_fanvue_user_uuid: UUID,
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
               AND fu.fanvue_user_uuid = tim.external_fanvue_user_uuid
            WHERE tim.fanvue_account_id = %s
              AND tim.external_fanvue_user_uuid = %s
              {active_filter}
            LIMIT 1;
        """
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    query, (fanvue_account_id, external_fanvue_user_uuid)
                )
                row = cursor.fetchone()
        return self._to_mapping(row)

    def get_verified_by_external_fanvue_user_uuid(
        self, fanvue_account_id: int, external_fanvue_user_uuid: UUID,
    ):
        mapping = self.get_by_external_fanvue_user_uuid(
            fanvue_account_id, external_fanvue_user_uuid,
            include_inactive=True,
        )
        return mapping if mapping and mapping.is_active and (
            mapping.verification_status == "VERIFIED"
        ) else None

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

    def observe(self, *, telegram_user_id: int, telegram_chat_id: int,
                username: str | None = None, display_name: str | None = None):
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.telegram_identity_observations (
                           telegram_user_id,telegram_chat_id,username,display_name)
                       VALUES (%s,%s,%s,%s)
                       ON CONFLICT (telegram_user_id) DO UPDATE SET
                           telegram_chat_id=EXCLUDED.telegram_chat_id,
                           username=COALESCE(EXCLUDED.username,telegram_identity_observations.username),
                           display_name=COALESCE(EXCLUDED.display_name,telegram_identity_observations.display_name),
                           last_observed_at=NOW() RETURNING *""",
                    (telegram_user_id, telegram_chat_id, username, display_name),
                )
                observation = dict(cursor.fetchone())
                cursor.execute(
                    """UPDATE public.telegram_identity_map SET
                           telegram_chat_id=%s,
                           last_observed_username=COALESCE(%s,last_observed_username),
                           last_observed_display_name=COALESCE(%s,last_observed_display_name),
                           updated_at=NOW()
                       WHERE telegram_user_id=%s RETURNING *""",
                    (telegram_chat_id, username, display_name, telegram_user_id),
                )
                mapping = cursor.fetchone()
        return observation, self._to_mapping(mapping)

    def create_verified_mapping(
        self, *, telegram_user_id: int, fanvue_account_id: int,
        local_fanvue_user_id: int, verification_method: str,
        operator_source: str, evidence: dict,
    ):
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    "SELECT * FROM public.telegram_identity_observations WHERE telegram_user_id=%s FOR UPDATE",
                    (telegram_user_id,),
                )
                observation = cursor.fetchone()
                if observation is None:
                    raise TelegramIdentityIntegrityError(
                        "Telegram identity has not been observed by Creator-OS."
                    )
                cursor.execute(
                    """SELECT * FROM public.fanvue_users
                       WHERE id=%s AND fanvue_account_id=%s""",
                    (local_fanvue_user_id, fanvue_account_id),
                )
                user = cursor.fetchone()
                if user is None:
                    raise TelegramIdentityIntegrityError(
                        "Fanvue user does not belong to the selected account."
                    )
                cursor.execute(
                    """SELECT * FROM public.telegram_identity_map
                       WHERE telegram_user_id=%s OR
                             (fanvue_account_id=%s AND external_fanvue_user_uuid=%s)
                       FOR UPDATE""",
                    (telegram_user_id, fanvue_account_id, user["fanvue_user_uuid"]),
                )
                existing = cursor.fetchall()
                if existing:
                    exact = next((row for row in existing
                                  if int(row["telegram_user_id"]) == telegram_user_id
                                  and int(row["fanvue_account_id"]) == fanvue_account_id
                                  and int(row["local_fanvue_user_id"]) == local_fanvue_user_id), None)
                    if exact and exact["verification_status"] == "VERIFIED" and exact["is_active"]:
                        return self._to_mapping(exact), True
                    raise TelegramIdentityConflictError(
                        "Telegram or Fanvue identity is already mapped differently."
                    )
                cursor.execute(
                    """INSERT INTO public.telegram_identity_map (
                           telegram_user_id,telegram_chat_id,fanvue_account_id,
                           local_fanvue_user_id,external_fanvue_user_uuid,
                           verification_status,verification_method,verified_at,
                           verified_by,verification_evidence,
                           last_observed_username,last_observed_display_name)
                       VALUES (%s,%s,%s,%s,%s,'VERIFIED',%s,NOW(),%s,%s::jsonb,%s,%s)
                       RETURNING *""",
                    (telegram_user_id, observation["telegram_chat_id"],
                     fanvue_account_id, local_fanvue_user_id,
                     user["fanvue_user_uuid"], verification_method,
                     operator_source, json.dumps(evidence),
                     observation.get("username"), observation.get("display_name")),
                )
                mapping = cursor.fetchone()
                cursor.execute(
                    """INSERT INTO public.telegram_identity_verification_audit (
                           audit_id,telegram_identity_mapping_id,telegram_user_id,
                           fanvue_account_id,local_fanvue_user_id,
                           external_fanvue_user_uuid,action,verification_method,
                           operator_source,evidence)
                       VALUES (%s,%s,%s,%s,%s,%s,'VERIFIED',%s,%s,%s::jsonb)""",
                    (uuid4(), mapping["id"], telegram_user_id, fanvue_account_id,
                     local_fanvue_user_id, user["fanvue_user_uuid"],
                     verification_method, operator_source, json.dumps(evidence)),
                )
        return self._to_mapping(mapping), False

    def readiness(self, *, fanvue_account_id: int):
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT
                       COUNT(1) FILTER (WHERE map.verification_status='VERIFIED' AND map.is_active) AS mapped,
                       COUNT(1) FILTER (WHERE map.id IS NULL) AS unmapped,
                       COUNT(1) FILTER (WHERE map.verification_status='CONFLICT') AS conflicts,
                       COUNT(1) FILTER (WHERE map.id IS NOT NULL AND
                           (NOT map.is_active OR map.verification_status='UNVERIFIED')) AS incomplete
                       FROM public.telegram_identity_observations observation
                       LEFT JOIN public.telegram_identity_map map
                         ON map.telegram_user_id=observation.telegram_user_id
                        AND map.fanvue_account_id=%s""",
                    (fanvue_account_id,),
                )
                counts = dict(cursor.fetchone())
                cursor.execute(
                    """SELECT observation.telegram_user_id,
                              observation.telegram_chat_id,
                              observation.username,observation.display_name,
                              observation.last_observed_at,
                              map.id AS mapping_id,map.verification_status,map.is_active,
                              map.local_fanvue_user_id
                       FROM public.telegram_identity_observations observation
                       LEFT JOIN public.telegram_identity_map map
                         ON map.telegram_user_id=observation.telegram_user_id
                        AND map.fanvue_account_id=%s
                       ORDER BY observation.last_observed_at DESC""",
                    (fanvue_account_id,),
                )
                rows = [dict(row) for row in cursor.fetchall()]
        return counts, rows

    def list_fanvue_candidates(self, *, fanvue_account_id: int):
        with self._connection_factory() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """SELECT fu.id,fu.fanvue_user_uuid,fu.username,fu.display_name
                       FROM public.fanvue_users fu
                       LEFT JOIN public.telegram_identity_map map
                         ON map.fanvue_account_id=fu.fanvue_account_id
                        AND map.external_fanvue_user_uuid=fu.fanvue_user_uuid
                       WHERE fu.fanvue_account_id=%s AND map.id IS NULL
                       ORDER BY COALESCE(fu.display_name,fu.username),fu.id""",
                    (fanvue_account_id,),
                )
                return [dict(row) for row in cursor.fetchall()]

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
