from uuid import uuid4

from app.database import get_db_connection


class TelegramBusinessPeerObservationRepository:
    def __init__(self, connection_factory=get_db_connection):
        self.connection_factory = connection_factory

    def capture(self, event):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT business_owner_telegram_user_id,is_enabled,can_reply
                     FROM public.telegram_business_connections
                    WHERE business_connection_id=%s""",
                (event.business_connection_id,),
            )
            connection_row = cursor.fetchone()
            if connection_row is None:
                return None
            is_inbound = (
                event.event_type == "business_message"
                and event.sender_telegram_user_id is not None
                and int(event.sender_telegram_user_id)
                    != int(connection_row["business_owner_telegram_user_id"])
            )
            cursor.execute(
                """INSERT INTO public.telegram_business_peer_observations (
                       observation_id,business_connection_id,telegram_peer_user_id,
                       telegram_chat_id,telegram_message_id,bot_api_update_id,event_type,
                       provider_timestamp,last_business_inbound_at,sender_telegram_user_id)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,
                           CASE WHEN %s IS NULL THEN NULL ELSE to_timestamp(%s) END,
                           CASE WHEN %s AND %s IS NOT NULL THEN to_timestamp(%s) END,%s)
                   ON CONFLICT DO NOTHING RETURNING *""",
                (uuid4(),event.business_connection_id,event.telegram_peer_user_id,
                 event.telegram_chat_id,event.telegram_message_id,event.update_id,
                 event.event_type,event.provider_timestamp,event.provider_timestamp,
                 is_inbound,event.provider_timestamp,event.provider_timestamp,
                 event.sender_telegram_user_id),
            )
            row = cursor.fetchone()
            if row is not None:
                return dict(row)
            cursor.execute(
                """SELECT * FROM public.telegram_business_peer_observations
                    WHERE business_connection_id=%s AND telegram_chat_id=%s
                      AND telegram_message_id=%s AND event_type=%s
                    ORDER BY observed_at DESC LIMIT 1""",
                (event.business_connection_id,event.telegram_chat_id,
                 event.telegram_message_id,event.event_type),
            )
            return dict(cursor.fetchone())

    def evidence(self, *, business_connection_id, telegram_peer_user_id):
        with self.connection_factory() as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT connection.business_connection_id,connection.is_enabled,
                          connection.can_reply,MAX(observation.last_business_inbound_at)
                              AS last_business_inbound_at,
                          MAX(observation.observed_at) AS last_observed_at,
                          COUNT(observation.observation_id) AS observation_count
                     FROM public.telegram_business_connections connection
                     LEFT JOIN public.telegram_business_peer_observations observation
                       ON observation.business_connection_id=connection.business_connection_id
                      AND observation.telegram_peer_user_id=%s
                    WHERE connection.business_connection_id=%s
                    GROUP BY connection.business_connection_id,connection.is_enabled,
                             connection.can_reply""",
                (telegram_peer_user_id,business_connection_id),
            )
            row = cursor.fetchone()
        return dict(row) if row else None
