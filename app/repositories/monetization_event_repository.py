import json

from app.database import get_db_connection


def create_monetization_event(event: dict):
    """
    3D.3 — Persist normalized monetization event.

    This table is separate from webhook_events because webhook_events
    tracks raw inbound webhook lifecycle, while fanvue_monetization_events
    tracks money/business events used by buyer intelligence.
    """

    sql = """
        INSERT INTO fanvue_monetization_events (
            external_event_id,
            event_type,
            fanvue_account_id,
            fanvue_user_id,
            local_user_id,
            amount,
            currency,
            content_item_id,
            content_tag,
            fanvue_media_uuid,
            purchase_type,
            status,
            raw_payload
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb
        )
        ON CONFLICT (external_event_id)
        DO NOTHING
        RETURNING id;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    event.get("external_event_id"),
                    event.get("event_type"),
                    event.get("fanvue_account_id"),
                    event.get("fanvue_user_id"),
                    event.get("local_user_id"),
                    event.get("amount", 0),
                    event.get("currency", "USD"),
                    event.get("content_item_id"),
                    event.get("content_tag"),
                    event.get("fanvue_media_uuid"),
                    event.get("purchase_type"),
                    event.get("status", "received"),
                    json.dumps(event.get("raw_payload", {})),
                ),
            )

            row = cursor.fetchone()
            conn.commit()

            if not row:
                return None

            return row["id"]


def get_monetization_event_by_external_id(external_event_id: str):
    if not external_event_id:
        return None

    sql = """
        SELECT *
        FROM fanvue_monetization_events
        WHERE external_event_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (external_event_id,))
            return cursor.fetchone()


def mark_monetization_event_processed(event_id: int):
    sql = """
        UPDATE fanvue_monetization_events
        SET
            status = 'processed',
            processed_at = NOW(),
            updated_at = NOW()
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (event_id,))
            conn.commit()

    return True