"""Persistence for authoritative Telegram Business connection state."""

from __future__ import annotations

import json
from datetime import datetime

from app.database import get_db_connection
from app.models.telegram_business_connection import TelegramBusinessConnection


class TelegramBusinessConnectionRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def reconcile(self, *, business_connection_id, business_owner_telegram_user_id,
                  bot_telegram_user_id, is_enabled, can_reply, rights,
                  provider_updated_at):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM telegram_business_connections
                   WHERE business_owner_telegram_user_id=%s
                     AND bot_telegram_user_id=%s AND superseded_at IS NULL
                   ORDER BY provider_updated_at DESC LIMIT 1 FOR UPDATE""",
                (business_owner_telegram_user_id, bot_telegram_user_id),
            )
            current = cursor.fetchone()
            if (
                current is not None
                and current["provider_updated_at"] > provider_updated_at
            ):
                return self._item(current)
            cursor.execute(
                """UPDATE telegram_business_connections SET superseded_at=NOW(),
                   updated_at=NOW()
                   WHERE business_owner_telegram_user_id=%s
                     AND bot_telegram_user_id=%s
                     AND business_connection_id<>%s
                     AND superseded_at IS NULL""",
                (business_owner_telegram_user_id, bot_telegram_user_id,
                 business_connection_id),
            )
            cursor.execute(
                """INSERT INTO telegram_business_connections (
                   business_connection_id,business_owner_telegram_user_id,
                   bot_telegram_user_id,is_enabled,can_reply,rights,
                   provider_updated_at,observed_at)
                   VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,NOW())
                   ON CONFLICT (business_connection_id) DO UPDATE SET
                   business_owner_telegram_user_id=EXCLUDED.business_owner_telegram_user_id,
                   bot_telegram_user_id=EXCLUDED.bot_telegram_user_id,
                   is_enabled=EXCLUDED.is_enabled,can_reply=EXCLUDED.can_reply,
                   rights=EXCLUDED.rights,
                   provider_updated_at=EXCLUDED.provider_updated_at,
                   observed_at=NOW(),superseded_at=NULL,updated_at=NOW()
                   WHERE telegram_business_connections.provider_updated_at
                         <= EXCLUDED.provider_updated_at
                   RETURNING *""",
                (business_connection_id, business_owner_telegram_user_id,
                 bot_telegram_user_id, is_enabled, can_reply,
                 json.dumps(dict(rights or {})), provider_updated_at),
            )
            row = cursor.fetchone()
            if row is None:
                cursor.execute(
                    "SELECT * FROM telegram_business_connections WHERE business_connection_id=%s",
                    (business_connection_id,),
                )
                row = cursor.fetchone()
            return self._item(row)

    def get_active(self, *, business_owner_telegram_user_id, bot_telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM telegram_business_connections
                   WHERE business_owner_telegram_user_id=%s
                     AND bot_telegram_user_id=%s
                     AND is_enabled=TRUE AND can_reply=TRUE
                     AND superseded_at IS NULL
                   ORDER BY provider_updated_at DESC LIMIT 1""",
                (business_owner_telegram_user_id, bot_telegram_user_id),
            )
            row = cursor.fetchone()
        return self._item(row) if row else None

    def get_current(self, *, business_owner_telegram_user_id, bot_telegram_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT * FROM telegram_business_connections
                   WHERE business_owner_telegram_user_id=%s
                     AND bot_telegram_user_id=%s AND superseded_at IS NULL
                   ORDER BY provider_updated_at DESC LIMIT 1""",
                (business_owner_telegram_user_id, bot_telegram_user_id),
            )
            row = cursor.fetchone()
        return self._item(row) if row else None

    @staticmethod
    def _item(row):
        if row is None:
            return None
        values = dict(row)
        values["rights"] = dict(values.get("rights") or {})
        return TelegramBusinessConnection(**values)
