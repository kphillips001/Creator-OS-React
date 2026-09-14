"""Audited, account-scoped operator relationship-value overrides."""
from uuid import uuid4

from app.database import get_db_connection


class RelationshipValueOverrideRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def active(self, *, creator_profile_id, fanvue_account_id,
               telegram_user_id, telegram_chat_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM telegram_relationship_value_overrides
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND removed_at IS NULL LIMIT 1""", (
                creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id,
            ))
            row = cursor.fetchone()
        return dict(row) if row else None

    def set_high_value(self, *, creator_profile_id, fanvue_account_id,
                       telegram_user_id, telegram_chat_id, changed_by, reason=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM telegram_relationship_value_overrides
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                ORDER BY version DESC FOR UPDATE""", (
                creator_profile_id, fanvue_account_id, telegram_user_id,
                telegram_chat_id,
            ))
            rows = cursor.fetchall()
            active = next((row for row in rows if row["removed_at"] is None), None)
            if active:
                return dict(active), False
            version = max((int(row["version"]) for row in rows), default=0) + 1
            cursor.execute("""INSERT INTO telegram_relationship_value_overrides(
                override_id,creator_profile_id,fanvue_account_id,telegram_user_id,
                telegram_chat_id,classification,version,changed_by,reason)
                VALUES(%s,%s,%s,%s,%s,'HIGH_VALUE_PROSPECT',%s,%s,%s)
                RETURNING *""", (uuid4(), creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id, version, changed_by, reason))
            return dict(cursor.fetchone()), True

    def remove(self, *, creator_profile_id, fanvue_account_id,
               telegram_user_id, telegram_chat_id, removed_by):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_relationship_value_overrides
                SET removed_by=%s,removed_at=NOW()
                WHERE creator_profile_id=%s AND fanvue_account_id=%s
                  AND telegram_user_id=%s AND telegram_chat_id=%s
                  AND removed_at IS NULL RETURNING *""", (
                removed_by, creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id,
            ))
            row = cursor.fetchone()
        return dict(row) if row else None

    def advance_eligible(self, *, telegram_user_id, telegram_chat_id,
                         available_at):
        """Advance only definitive, unclaimed, pre-generation availability work."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE ordinary_chat_reply_operations target SET
                  next_retry_at=%s,updated_at=NOW(),
                  delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)
                    || jsonb_build_object('highValueProspectScheduleAdvanced',true)
                WHERE telegram_account_scope='AVA_TELETHON_PRIVATE'
                  AND telegram_chat_id=%s
                  AND inbound_sender_telegram_user_id=%s
                  AND state='RETRYABLE' AND response_payload IS NULL
                  AND last_error='availability_deferred'
                  AND generation_attempt_count=0 AND send_attempt_count=0
                  AND claim_owner IS NULL AND outbound_telegram_message_id IS NULL
                  AND next_retry_at IS NOT NULL AND %s<next_retry_at
                  AND inbound_telegram_message_id=(
                    SELECT MAX(candidate.inbound_telegram_message_id)
                    FROM ordinary_chat_reply_operations candidate
                    WHERE candidate.telegram_account_scope=target.telegram_account_scope
                      AND candidate.telegram_chat_id=target.telegram_chat_id
                      AND candidate.inbound_sender_telegram_user_id=target.inbound_sender_telegram_user_id)
                RETURNING operation_id,next_retry_at""", (
                available_at, telegram_chat_id, telegram_user_id, available_at,
            ))
            row = cursor.fetchone()
        return dict(row) if row else None
