from __future__ import annotations

import json
from uuid import UUID, uuid4

from psycopg.errors import UniqueViolation

from app.database import get_db_connection
from app.models.telegram_identity import TelegramIdentityMapping
from app.repositories.telegram_identity_repository import (
    TelegramIdentityConflictError,
    TelegramIdentityIntegrityError,
)


class TelegramIdentityVerificationRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def pending(self, *, telegram_user_id: int, fanvue_account_id: int):
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """UPDATE public.telegram_identity_verification_challenges
                          SET state='EXPIRED',updated_at=NOW()
                        WHERE telegram_user_id=%s AND fanvue_account_id=%s
                          AND state='PENDING' AND expires_at<=NOW()""",
                    (telegram_user_id, fanvue_account_id),
                )
                cursor.execute(
                    """SELECT * FROM public.telegram_identity_verification_challenges
                        WHERE telegram_user_id=%s AND fanvue_account_id=%s
                          AND state='PENDING' AND expires_at>NOW()
                        LIMIT 1""",
                    (telegram_user_id, fanvue_account_id),
                )
                row = cursor.fetchone()
        return dict(row) if row else None

    def create(self, *, telegram_user_id: int, telegram_chat_id: int,
               fanvue_account_id: int, token_hash: str, expires_at):
        challenge_id = uuid4()
        with self.connection_factory() as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    """INSERT INTO public.telegram_identity_verification_challenges (
                           challenge_id,telegram_user_id,telegram_chat_id,
                           fanvue_account_id,token_hash,expires_at)
                       VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (challenge_id, telegram_user_id, telegram_chat_id,
                     fanvue_account_id, token_hash, expires_at),
                )
                return dict(cursor.fetchone())

    def complete(self, *, fanvue_account_id: int, fanvue_user_uuid: UUID,
                 token_hash: str, provider_event_id: str):
        """Consume proof and create its identity mapping in one transaction."""
        try:
            with self.connection_factory() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        """SELECT * FROM public.telegram_identity_verification_challenges
                            WHERE fanvue_account_id=%s AND token_hash=%s
                            FOR UPDATE""",
                        (fanvue_account_id, token_hash),
                    )
                    challenge = cursor.fetchone()
                    if challenge is None:
                        return {"status": "NO_MATCH"}
                    if challenge["state"] == "VERIFIED":
                        if challenge["provider_fanvue_user_uuid"] == fanvue_user_uuid:
                            cursor.execute(
                                "SELECT * FROM public.telegram_identity_map WHERE id=%s",
                                (challenge["resulting_identity_mapping_id"],),
                            )
                            return {"status": "VERIFIED", "mapping": TelegramIdentityMapping.from_row(cursor.fetchone()), "duplicate": True}
                        return {"status": "CONFLICT"}
                    if challenge["state"] != "PENDING":
                        return {"status": challenge["state"]}
                    cursor.execute("SELECT NOW() AS now")
                    if challenge["expires_at"] <= cursor.fetchone()["now"]:
                        cursor.execute(
                            """UPDATE public.telegram_identity_verification_challenges
                                  SET state='EXPIRED',updated_at=NOW()
                                WHERE challenge_id=%s""",
                            (challenge["challenge_id"],),
                        )
                        return {"status": "EXPIRED"}

                    cursor.execute(
                        """SELECT * FROM public.telegram_identity_observations
                            WHERE telegram_user_id=%s FOR UPDATE""",
                        (challenge["telegram_user_id"],),
                    )
                    observation = cursor.fetchone()
                    if observation is None:
                        raise TelegramIdentityIntegrityError(
                            "Telegram identity has not been observed by Creator-OS."
                        )
                    cursor.execute(
                        """INSERT INTO public.fanvue_users (
                               fanvue_account_id,fanvue_user_uuid,source,last_seen_at)
                           VALUES (%s,%s,'telegram_identity_dm_challenge',NOW())
                           ON CONFLICT (fanvue_account_id,fanvue_user_uuid)
                           DO UPDATE SET last_seen_at=NOW()
                           RETURNING *""",
                        (fanvue_account_id, fanvue_user_uuid),
                    )
                    fanvue_user = cursor.fetchone()
                    cursor.execute(
                        """SELECT * FROM public.telegram_identity_map
                            WHERE telegram_user_id=%s OR
                                  (fanvue_account_id=%s AND external_fanvue_user_uuid=%s)
                            FOR UPDATE""",
                        (challenge["telegram_user_id"], fanvue_account_id,
                         fanvue_user_uuid),
                    )
                    existing = cursor.fetchall()
                    exact = next((row for row in existing
                                  if int(row["telegram_user_id"]) == int(challenge["telegram_user_id"])
                                  and int(row["fanvue_account_id"]) == fanvue_account_id
                                  and row["external_fanvue_user_uuid"] == fanvue_user_uuid
                                  and row["verification_status"] == "VERIFIED"
                                  and row["is_active"]), None)
                    if existing and exact is None:
                        raise TelegramIdentityConflictError(
                            "Telegram or Fanvue identity is already mapped differently."
                        )
                    evidence = {
                        "provider_event_id": provider_event_id,
                        "challenge_id": str(challenge["challenge_id"]),
                        "proof": "signed_fanvue_inbound_message",
                    }
                    if exact is None:
                        cursor.execute(
                            """INSERT INTO public.telegram_identity_map (
                                   telegram_user_id,telegram_chat_id,fanvue_account_id,
                                   local_fanvue_user_id,external_fanvue_user_uuid,
                                   verification_status,verification_method,verified_at,
                                   verified_by,verification_evidence,
                                   last_observed_username,last_observed_display_name)
                               VALUES (%s,%s,%s,%s,%s,'VERIFIED','FANVUE_DM_CHALLENGE',
                                   NOW(),'FANVUE_SIGNED_WEBHOOK',%s::jsonb,%s,%s)
                               RETURNING *""",
                            (challenge["telegram_user_id"], challenge["telegram_chat_id"],
                             fanvue_account_id, fanvue_user["id"], fanvue_user_uuid,
                             json.dumps(evidence), observation.get("username"),
                             observation.get("display_name")),
                        )
                        mapping = cursor.fetchone()
                        cursor.execute(
                            """INSERT INTO public.telegram_identity_verification_audit (
                                   audit_id,telegram_identity_mapping_id,telegram_user_id,
                                   fanvue_account_id,local_fanvue_user_id,
                                   external_fanvue_user_uuid,action,verification_method,
                                   operator_source,evidence)
                               VALUES (%s,%s,%s,%s,%s,%s,'VERIFIED',
                                   'FANVUE_DM_CHALLENGE','FANVUE_SIGNED_WEBHOOK',%s::jsonb)""",
                            (uuid4(), mapping["id"], challenge["telegram_user_id"],
                             fanvue_account_id, fanvue_user["id"], fanvue_user_uuid,
                             json.dumps(evidence)),
                        )
                    else:
                        mapping = exact
                    cursor.execute(
                        """UPDATE public.telegram_identity_verification_challenges
                              SET state='VERIFIED',consumed_at=NOW(),updated_at=NOW(),
                                  provider_event_id=%s,provider_fanvue_user_uuid=%s,
                                  resulting_identity_mapping_id=%s,
                                  verification_evidence=%s::jsonb
                            WHERE challenge_id=%s RETURNING *""",
                        (provider_event_id, fanvue_user_uuid, mapping["id"],
                         json.dumps(evidence), challenge["challenge_id"]),
                    )
                    cursor.fetchone()
                    return {"status": "VERIFIED", "mapping": TelegramIdentityMapping.from_row(mapping), "duplicate": exact is not None}
        except UniqueViolation as error:
            raise TelegramIdentityConflictError(
                "Verification conflicts with an existing identity or provider event."
            ) from error
