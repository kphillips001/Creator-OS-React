"""Exactly-once private Telegram inbound storage and chat-level claims."""
from __future__ import annotations

import json
from uuid import uuid4

from app.database import get_db_connection
from app.models.telegram_private_inbound_message import TelegramPrivateInboundMessage


class TelegramPrivateInboundRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory = connection_factory

    def capture(self, *, account_scope, user_id, chat_id, message_id, received_at, customer_text,
                media_types=(), creator_profile_id=None, fanvue_account_id=None,
                mapped_customer_id=None, prospect_id=None, ingestion_provenance="TELETHON_NEW_MESSAGE",
                automation_state="OFF"):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"telegram-inbound:{account_scope}:{chat_id}",))
            cursor.execute("""INSERT INTO telegram_private_inbound_messages(
                inbound_id,telegram_account_scope,telegram_user_id,telegram_chat_id,telegram_message_id,
                received_at,customer_text,has_media,media_types,creator_profile_id,fanvue_account_id,
                mapped_customer_id,prospect_id,ingestion_provenance,automation_state_at_receipt,reconciliation_state)
                VALUES(%s,%s,%s,%s,%s,COALESCE(%s,NOW()),%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(telegram_account_scope,telegram_chat_id,telegram_message_id) DO NOTHING
                RETURNING *""", (uuid4(), account_scope, user_id, chat_id, message_id, received_at,
                    str(customer_text or ""), bool(media_types), json.dumps(list(media_types)), creator_profile_id,
                    fanvue_account_id, mapped_customer_id, prospect_id, ingestion_provenance, automation_state,
                    "CAPTURED" if automation_state == "OFF" else "LIVE_HANDLED"))
            row = cursor.fetchone(); created = row is not None
            if row is None:
                cursor.execute("""SELECT * FROM telegram_private_inbound_messages
                    WHERE telegram_account_scope=%s AND telegram_chat_id=%s AND telegram_message_id=%s""",
                    (account_scope, chat_id, message_id)); row = cursor.fetchone()
            connection.commit()
        return self._model(row), created

    def consume_control(self, *, account_scope, chat_id, message_id):
        """Retain transport evidence while excluding control traffic from response work."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_private_inbound_messages
                SET reconciliation_state='NO_RESPONSE_REQUIRED',reconciled_at=NOW(),updated_at=NOW()
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                  AND telegram_message_id=%s
                  AND reconciliation_state IN ('CAPTURED','LIVE_HANDLED')
                RETURNING inbound_id""", (account_scope, chat_id, message_id))
            row = cursor.fetchone()
            connection.commit()
        return row is not None
    def pending_for_chat(self, *, account_scope, chat_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT * FROM telegram_private_inbound_messages
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s AND reconciliation_state='CAPTURED'
                ORDER BY received_at,telegram_message_id""", (account_scope, chat_id))
            return [self._model(row) for row in cursor.fetchall()]

    def latest_boundary(self, *, account_scope):
        """Return the newest durable inbound boundary for bounded history overlap."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""SELECT telegram_message_id,received_at
                FROM telegram_private_inbound_messages
                WHERE telegram_account_scope=%s
                ORDER BY received_at DESC,telegram_message_id DESC LIMIT 1""",
                (account_scope,))
            row = cursor.fetchone()
        return dict(row) if row else None

    def correlate(self, *, account_scope, chat_id, message_id, mapped_customer_id=None,
                  prospect_id=None, response_operation_id=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE telegram_private_inbound_messages SET
                mapped_customer_id=COALESCE(mapped_customer_id,%s),
                prospect_id=COALESCE(prospect_id,%s),
                response_operation_id=COALESCE(response_operation_id,%s),updated_at=NOW()
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s AND telegram_message_id=%s""",
                (mapped_customer_id, prospect_id, response_operation_id,
                 account_scope, chat_id, message_id))
            connection.commit()

    def reconcile(self, *, account_scope, chat_id, authoritative_message_id=None, outcome,
                  reconciliation_id, expected_message_ids=()):
        """Atomically terminate one chat backlog and create at most one current obligation."""
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (f"telegram-inbound:{account_scope}:{chat_id}",))
            cursor.execute("""SELECT telegram_message_id FROM telegram_private_inbound_messages
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s AND reconciliation_state='CAPTURED'
                ORDER BY received_at,telegram_message_id FOR UPDATE""", (account_scope, chat_id))
            current_ids = tuple(int(row["telegram_message_id"]) for row in cursor.fetchall())
            if tuple(expected_message_ids) != current_ids:
                return [], None, True
            operation_id = None
            if outcome == "RESPOND":
                cursor.execute("""SELECT * FROM telegram_private_inbound_messages
                    WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                      AND telegram_message_id=%s AND reconciliation_state='CAPTURED' FOR UPDATE""",
                    (account_scope, chat_id, authoritative_message_id))
                authority = cursor.fetchone()
                if authority is not None:
                    operation_id = uuid4()
                    cursor.execute("""INSERT INTO ordinary_chat_reply_operations(
                        operation_id,telegram_account_scope,telegram_chat_id,inbound_telegram_message_id,
                        inbound_sender_telegram_user_id,correlation_id,inbound_message_text,inbound_received_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s)
                        ON CONFLICT(telegram_account_scope,telegram_chat_id,inbound_telegram_message_id)
                        DO NOTHING RETURNING operation_id""", (operation_id, account_scope, chat_id,
                            authority["telegram_message_id"], authority["telegram_user_id"],
                            f"backlog:{reconciliation_id}", authority["customer_text"], authority["received_at"]))
                    created = cursor.fetchone()
                    if created is None:
                        cursor.execute("""SELECT operation_id FROM ordinary_chat_reply_operations
                            WHERE telegram_account_scope=%s AND telegram_chat_id=%s
                              AND inbound_telegram_message_id=%s""",
                            (account_scope, chat_id, authoritative_message_id))
                        existing = cursor.fetchone(); operation_id = existing["operation_id"] if existing else None
            cursor.execute("""UPDATE telegram_private_inbound_messages SET
                reconciliation_state=CASE WHEN %s='NO_RESPONSE_REQUIRED' THEN 'NO_RESPONSE_REQUIRED'
                    WHEN telegram_message_id=%s THEN 'RECONCILED' ELSE 'SUPERSEDED' END,
                reconciliation_id=%s,response_operation_id=CASE WHEN telegram_message_id=%s THEN %s::uuid ELSE NULL::uuid END,
                reconciled_at=NOW(),updated_at=NOW()
                WHERE telegram_account_scope=%s AND telegram_chat_id=%s AND reconciliation_state='CAPTURED'
                RETURNING *""", (outcome, authoritative_message_id, reconciliation_id,
                    authoritative_message_id, operation_id, account_scope, chat_id))
            rows = [self._model(row) for row in cursor.fetchall()]
            connection.commit()
            return rows, operation_id, False

    @staticmethod
    def _model(row):
        return TelegramPrivateInboundMessage(
            inbound_id=row["inbound_id"], telegram_account_scope=row["telegram_account_scope"],
            telegram_user_id=int(row["telegram_user_id"]), telegram_chat_id=int(row["telegram_chat_id"]),
            telegram_message_id=int(row["telegram_message_id"]), received_at=row["received_at"],
            customer_text=row.get("customer_text") or "", has_media=bool(row.get("has_media")),
            media_types=tuple(row.get("media_types") or ()), reconciliation_state=row["reconciliation_state"],
            mapped_customer_id=row.get("mapped_customer_id"), prospect_id=row.get("prospect_id"))
