from app.database import get_db_connection
from psycopg.types.json import Json


def get_or_create_chat_thread(
    fanvue_account_id: int,
    fanvue_user_id: int,
    fanvue_chat_uuid: str = None,
):
    query = """
        SELECT *
        FROM chat_threads
        WHERE fanvue_account_id = %s
          AND fanvue_user_id = %s
        ORDER BY id ASC
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, fanvue_user_id))
            thread = cur.fetchone()

            if thread:
                return thread

            insert_query = """
                INSERT INTO chat_threads (
                    fanvue_account_id,
                    fanvue_user_id,
                    fanvue_chat_uuid,
                    thread_status
                )
                VALUES (%s, %s, %s, 'active')
                RETURNING *;
            """
            cur.execute(
                insert_query,
                (fanvue_account_id, fanvue_user_id, fanvue_chat_uuid),
            )
            return cur.fetchone()


def save_chat_message(
    fanvue_account_id: int,
    thread_id: int,
    fanvue_user_id: int,
    direction: str,
    sender_type: str,
    text: str,
    fanvue_message_uuid: str = None,
    has_media: bool = False,
    media_uuids=None,
    is_paid_message: bool = False,
    price_cents: int = None,
    template_uuid: str = None,
    raw_payload=None,
):
    if media_uuids is None:
        media_uuids = []

    if raw_payload is None:
        raw_payload = {}

    direction = direction.strip().lower()
    sender_type = sender_type.strip().lower()

    if direction not in {"inbound", "outbound"}:
        raise ValueError("direction must be 'inbound' or 'outbound'")

    # Normalize legacy values
    if sender_type == "fan":
        sender_type = "user"

    if sender_type not in {"user", "bot"}:
        raise ValueError("sender_type must be 'user' or 'bot'")

    insert_query = """
        INSERT INTO chat_messages (
            fanvue_account_id,
            thread_id,
            fanvue_user_id,
            fanvue_message_uuid,
            direction,
            sender_type,
            text,
            has_media,
            media_uuids,
            is_paid_message,
            price_cents,
            template_uuid,
            sent_at,
            raw_payload
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), %s)
        RETURNING *;
    """

    update_thread_query = """
        UPDATE chat_threads
        SET
            last_message_at = NOW(),
            last_inbound_at = CASE WHEN %s = 'inbound' THEN NOW() ELSE last_inbound_at END,
            last_outbound_at = CASE WHEN %s = 'outbound' THEN NOW() ELSE last_outbound_at END,
            updated_at = NOW()
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                insert_query,
                (
                    fanvue_account_id,
                    thread_id,
                    fanvue_user_id,
                    fanvue_message_uuid,
                    direction,
                    sender_type,
                    text,
                    has_media,
                    Json(media_uuids),
                    is_paid_message,
                    price_cents,
                    template_uuid,
                    Json(raw_payload),
                ),
            )
            message = cur.fetchone()

            cur.execute(update_thread_query, (direction, direction, thread_id))
            return message


def get_messages_by_thread(
    fanvue_account_id: int,
    thread_id: int,
):
    query = """
        SELECT
            cm.id,
            cm.thread_id,
            cm.fanvue_user_id,
            cm.direction,
            cm.sender_type,
            cm.text,
            cm.sent_at
        FROM chat_messages cm
        JOIN chat_threads ct
            ON ct.id = cm.thread_id
        WHERE cm.thread_id = %s
          AND ct.fanvue_account_id = %s
        ORDER BY cm.id ASC;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    thread_id,
                    fanvue_account_id,
                ),
            )

            return cur.fetchall()


def get_thread_messages_for_user(
    fanvue_account_id: int,
    fanvue_user_id: int,
):
    query = """
        SELECT
            cm.id,
            cm.thread_id,
            cm.fanvue_user_id,
            cm.direction,
            cm.sender_type,
            cm.text,
            cm.sent_at
        FROM chat_threads ct
        JOIN chat_messages cm
            ON cm.thread_id = ct.id
        WHERE ct.fanvue_account_id = %s
          AND ct.fanvue_user_id = %s
        ORDER BY cm.id ASC;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_account_id, fanvue_user_id))
            return cur.fetchall()


def get_recent_messages(
    fanvue_account_id: int,
    thread_id: int,
    limit: int = 10,
):
    query = """
        SELECT
            cm.id,
            cm.thread_id,
            cm.fanvue_user_id,
            cm.direction,
            cm.sender_type,
            cm.text,
            cm.sent_at
        FROM chat_messages cm
        JOIN chat_threads ct
            ON ct.id = cm.thread_id
        WHERE cm.thread_id = %s
          AND ct.fanvue_account_id = %s
        ORDER BY cm.id DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    thread_id,
                    fanvue_account_id,
                    limit,
                ),
            )

            messages = cur.fetchall()

    return list(reversed(messages))

def get_recent_messages_for_gpt(
    fanvue_account_id: int,
    thread_id: int,
    limit: int = 10,
):
    messages = get_recent_messages(
        fanvue_account_id=fanvue_account_id,
        thread_id=thread_id,
        limit=limit,
    )

    formatted_messages = []

    for msg in messages:
        role = (
            "user"
            if msg["sender_type"] == "user"
            else "assistant"
        )

        formatted_messages.append(
            {
                "role": role,
                "content": msg["text"],
            }
        )

    return formatted_messages