import json
from app.database import get_db_connection


def ensure_fanvue_chat_messages_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.fanvue_chat_messages') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.fanvue_chat_messages. Run forward migrations before using FanvueMessageRepository."
        )


def save_fanvue_chat_message(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
    message: dict,
    my_user_uuid: str,
) -> dict:
    ensure_fanvue_chat_messages_table()

    message_uuid = message.get("message_uuid")
    sender_uuid = message.get("sender_uuid")
    message_text = message.get("text")
    sent_at = message.get("sent_at")
    raw_payload = message.get("raw") or message

    if not message_uuid:
        return {
            "success": False,
            "inserted": False,
            "reason": "missing_message_uuid",
        }

    is_inbound = sender_uuid != my_user_uuid

    sql = """
    INSERT INTO fanvue_chat_messages (
        fanvue_account_id,
        fanvue_user_uuid,
        fanvue_message_uuid,
        sender_uuid,
        message_text,
        sent_at,
        is_inbound,
        raw_payload
    )
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON CONFLICT (fanvue_message_uuid)
    DO NOTHING
    RETURNING id;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_uuid,
                    message_uuid,
                    sender_uuid,
                    message_text,
                    sent_at,
                    is_inbound,
                    json.dumps(raw_payload, default=str),
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return {
        "success": True,
        "inserted": row is not None,
        "fanvue_message_uuid": message_uuid,
        "is_inbound": is_inbound,
    }


def get_latest_message_timestamp(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
) -> str | None:
    ensure_fanvue_chat_messages_table()

    sql = """
    SELECT sent_at
    FROM fanvue_chat_messages
    WHERE fanvue_account_id = %s
      AND fanvue_user_uuid = %s
    ORDER BY sent_at DESC
    LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (fanvue_account_id, fanvue_user_uuid))
            row = cur.fetchone()

    if not row:
        return None

    if isinstance(row, dict):
        value = row.get("sent_at")
    else:
        value = row[0]

    return value.isoformat() if value else None
