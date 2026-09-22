"""Transactional authority for bounded Telegram text/media turn assembly."""
from __future__ import annotations
import json
from uuid import NAMESPACE_URL, uuid5
from app.database import get_db_connection


class TelegramTurnReservationRepository:
    def __init__(self, connection_factory=get_db_connection): self.connection_factory=connection_factory

    def open_text(self, *, creator_profile_id, fanvue_account_id, inbound, window_ms):
        rid=uuid5(NAMESPACE_URL,f"telegram-turn:{creator_profile_id}:{fanvue_account_id}:{inbound.telegram_chat_id}:{inbound.telegram_message_id}")
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                      (f"telegram-turn:{inbound.telegram_chat_id}",))
            q.execute("""UPDATE telegram_conversation_turn_reservations SET state='CLOSED',updated_at=NOW(),version=version+1
              WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_chat_id=%s
                AND state='OPEN' AND closes_at<=NOW()""",(creator_profile_id,fanvue_account_id,inbound.telegram_chat_id))
            q.execute("""INSERT INTO telegram_conversation_turn_reservations(
              reservation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,telegram_user_id,
              closes_at,member_inbound_ids,member_telegram_message_ids,member_roles,
              newest_message_freshness_watermark,state)
              VALUES(%s,%s,%s,%s,%s,NOW()+(%s*INTERVAL '1 millisecond'),ARRAY[%s::uuid],ARRAY[%s::bigint],%s::jsonb,%s,'OPEN')
              ON CONFLICT(reservation_id) DO UPDATE SET updated_at=NOW() RETURNING *""",
              (rid,creator_profile_id,fanvue_account_id,inbound.telegram_chat_id,inbound.telegram_user_id,
               window_ms,inbound.inbound_id,inbound.telegram_message_id,json.dumps([{"inbound_id":str(inbound.inbound_id),"telegram_message_id":inbound.telegram_message_id,"role":"TEXT"}]),inbound.telegram_message_id))
            return q.fetchone()

    def bind_owner(self, reservation_id, operation_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""UPDATE telegram_conversation_turn_reservations SET
              authoritative_response_operation_id=COALESCE(authoritative_response_operation_id,%s),
              conversation_burst_id=COALESCE(conversation_burst_id,%s),version=version+1,updated_at=NOW()
              WHERE reservation_id=%s AND state IN ('OPEN','READY') RETURNING *""",(operation_id,operation_id,reservation_id))
            row=q.fetchone()
            self._synchronize_owner(q,row)
            return row

    def bind_captured_owner(self, reservation_id, inbound_id):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""UPDATE telegram_conversation_turn_reservations reservation SET
              authoritative_response_operation_id=inbound.response_operation_id,
              conversation_burst_id=inbound.response_operation_id,version=version+1,updated_at=NOW()
              FROM telegram_private_inbound_messages inbound
              WHERE reservation.reservation_id=%s AND inbound.inbound_id=%s
                AND inbound.response_operation_id IS NOT NULL
                AND reservation.state IN ('OPEN','READY') RETURNING reservation.*""",(reservation_id,inbound_id))
            row=q.fetchone()
            self._synchronize_owner(q,row)
            return row

    def join_media(self, *, creator_profile_id, fanvue_account_id, inbound):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))",
                      (f"telegram-turn:{inbound.telegram_chat_id}",))
            q.execute("""UPDATE telegram_conversation_turn_reservations SET
              member_inbound_ids=(SELECT ARRAY(SELECT DISTINCT unnest(member_inbound_ids||ARRAY[%s::uuid]))),
              member_telegram_message_ids=(SELECT ARRAY(SELECT DISTINCT unnest(member_telegram_message_ids||ARRAY[%s::bigint]) ORDER BY 1)),
              member_roles=CASE WHEN %s::uuid=ANY(member_inbound_ids) THEN member_roles ELSE member_roles||%s::jsonb END,
              newest_message_freshness_watermark=GREATEST(newest_message_freshness_watermark,%s),
              state='READY',version=version+1,updated_at=NOW()
              WHERE creator_profile_id=%s AND fanvue_account_id=%s AND telegram_chat_id=%s
                AND state IN ('OPEN','READY') AND closes_at>NOW()
              RETURNING *""",(inbound.inbound_id,inbound.telegram_message_id,
                inbound.inbound_id,
                json.dumps([{"inbound_id":str(inbound.inbound_id),"telegram_message_id":inbound.telegram_message_id,"role":"MEDIA"}]),
                inbound.telegram_message_id,creator_profile_id,fanvue_account_id,inbound.telegram_chat_id));
            row=q.fetchone()
            self._synchronize_owner(q,row)
            return row

    def close_expired(self):
        with self.connection_factory() as c,c.cursor() as q:
            q.execute("""UPDATE telegram_conversation_turn_reservations
              SET state='CLOSED',updated_at=NOW(),version=version+1
              WHERE state='OPEN' AND closes_at<=NOW() RETURNING reservation_id""")
            return tuple(row['reservation_id'] for row in q.fetchall())

    @staticmethod
    def _synchronize_owner(q,row):
        if row and row.get('authoritative_response_operation_id'):
            q.execute("""UPDATE ordinary_chat_reply_operations SET
                  conversation_burst_id=%s,burst_survivor_operation_id=%s,burst_role='SURVIVOR',
                  burst_freshness_telegram_message_id=GREATEST(
                    COALESCE(burst_freshness_telegram_message_id,%s),%s),
                  delivery_payload=COALESCE(delivery_payload,'{}'::jsonb)||jsonb_build_object(
                    'conversationTurnReservation',jsonb_build_object('reservationId',%s::text,
                    'freshnessMessageId',%s,'version',%s)),updated_at=NOW()
                  WHERE operation_id=%s""",(row['conversation_burst_id'],row['authoritative_response_operation_id'],
                    row['newest_message_freshness_watermark'],row['newest_message_freshness_watermark'],row['reservation_id'],
                    row['newest_message_freshness_watermark'],row['version'],row['authoritative_response_operation_id']))
