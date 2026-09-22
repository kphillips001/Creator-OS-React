"""PostgreSQL persistence for publication-specific Chat CTA attribution."""

from __future__ import annotations

from collections.abc import Callable

from app.database import get_db_connection
from app.models.creator_content_entry_attribution import (
    CreatorContentEntryAttribution, CreatorContentEntryEvent,
)


class CreatorContentEntryAttributionRepository:
    def __init__(self, *, connection_factory: Callable = get_db_connection):
        self.connection_factory = connection_factory

    def create_or_get(self, value: CreatorContentEntryAttribution):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._ensure(connection)
            cursor.execute("""INSERT INTO public.creator_content_entry_attributions
                (attribution_id,creator_profile_id,publication_id,token_digest,
                 source_platform,provenance_method,status,token_created_at,created_at,updated_at)
                VALUES (%s::uuid,%s,%s::uuid,%s,%s,%s,%s,%s,now(),now())
                ON CONFLICT (publication_id) DO UPDATE SET
                  updated_at=creator_content_entry_attributions.updated_at
                RETURNING *""", (value.attribution_id,value.creator_profile_id,
                value.publication_id,value.token_digest,value.source_platform,
                value.provenance_method,value.status,value.token_created_at))
            return self._attribution(cursor.fetchone())

    def get_by_digest(self, token_digest: str):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._ensure(connection)
            cursor.execute("""SELECT * FROM public.creator_content_entry_attributions
                WHERE token_digest=%s AND status<>'REVOKED'""", (token_digest,))
            row=cursor.fetchone()
        return self._attribution(row) if row else None

    def mark_attachment(self, attribution_id: str, *, succeeded: bool, error_code=None):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute("""UPDATE public.creator_content_entry_attributions
                SET status=%s,cta_attached_at=CASE WHEN %s THEN now() ELSE cta_attached_at END,
                    last_error_code=%s,updated_at=now() WHERE attribution_id=%s::uuid RETURNING *""",
                ("CTA_ATTACHED" if succeeded else "CTA_ATTACHMENT_FAILED",succeeded,
                 None if succeeded else str(error_code or "CTA_ATTACHMENT_FAILED")[:200],attribution_id))
            row=cursor.fetchone()
        return self._attribution(row)

    def observe(self, value: CreatorContentEntryEvent):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._ensure(connection)
            cursor.execute("""INSERT INTO public.creator_content_entry_events
                (entry_event_id,attribution_id,creator_profile_id,publication_id,event_status,
                 telegram_user_id,telegram_chat_id,inbound_telegram_message_id,observed_at,created_at)
                VALUES (%s::uuid,%s::uuid,%s,%s::uuid,%s,%s,%s,%s,%s,now())
                ON CONFLICT (attribution_id,telegram_user_id,telegram_chat_id,inbound_telegram_message_id)
                DO UPDATE SET observed_at=creator_content_entry_events.observed_at RETURNING *""",
                (value.entry_event_id,value.attribution_id,value.creator_profile_id,
                 value.publication_id,value.event_status,value.telegram_user_id,
                 value.telegram_chat_id,value.inbound_telegram_message_id,value.observed_at))
            return self._event(cursor.fetchone())

    def list_entry_history(self, *, creator_profile_id: int, telegram_user_id: int,
                           telegram_chat_id: int | None = None, limit: int = 5):
        """Return only authoritative observed entries, newest first and bounded."""
        filters = ["event.creator_profile_id=%s", "event.telegram_user_id=%s",
                   "event.event_status='ENTRY_OBSERVED'", "attribution.status<>'REVOKED'"]
        params = [int(creator_profile_id), int(telegram_user_id)]
        if telegram_chat_id is not None:
            filters.append("event.telegram_chat_id=%s")
            params.append(int(telegram_chat_id))
        params.append(max(1, min(int(limit), 10)))
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._ensure(connection)
            cursor.execute(f"""SELECT event.entry_event_id,event.attribution_id,
                event.publication_id,event.observed_at,event.telegram_user_id,
                event.telegram_chat_id,event.inbound_telegram_message_id,
                attribution.provenance_method
                FROM public.creator_content_entry_events event
                JOIN public.creator_content_entry_attributions attribution
                  ON attribution.attribution_id=event.attribution_id
                WHERE {' AND '.join(filters)}
                ORDER BY event.observed_at DESC,event.entry_event_id DESC
                LIMIT %s""", tuple(params))
            rows = cursor.fetchall()
        return tuple({
            "entryEventId": str(row["entry_event_id"]),
            "attributionId": str(row["attribution_id"]),
            "publicationId": str(row["publication_id"]),
            "observedAt": row["observed_at"],
            "provenanceMethod": str(row["provenance_method"]),
            "telegramUserId": int(row["telegram_user_id"]),
            "telegramChatId": int(row["telegram_chat_id"]),
            "inboundTelegramMessageId": int(row["inbound_telegram_message_id"]),
        } for row in rows)
    def list_events(self, *, creator_profile_id: int, telegram_user_id: int):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            self._ensure(connection)
            cursor.execute("""SELECT * FROM public.creator_content_entry_events
                WHERE creator_profile_id=%s AND telegram_user_id=%s
                ORDER BY observed_at,entry_event_id""", (creator_profile_id,telegram_user_id))
            rows=cursor.fetchall()
        return tuple(self._event(row) for row in rows)

    @staticmethod
    def _ensure(connection):
        with connection.cursor() as cursor:
            cursor.execute("SELECT to_regclass('public.creator_content_entry_attributions') table_ref")
            row=cursor.fetchone()
        if not row or not row["table_ref"]:
            raise RuntimeError("Missing creator_content_entry_attributions; apply migration 145 first.")

    @staticmethod
    def _attribution(row):
        return CreatorContentEntryAttribution(**{key: row.get(key) for key in CreatorContentEntryAttribution.__dataclass_fields__})

    @staticmethod
    def _event(row):
        return CreatorContentEntryEvent(**{key: row.get(key) for key in CreatorContentEntryEvent.__dataclass_fields__})
