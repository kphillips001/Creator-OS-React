from app.database import get_db_connection


def upsert_fanvue_thread(
    thread_id: str,
    fanvue_user_uuid: str,
    fanvue_account_id: int,
    last_message_at=None,
):
    """
    Insert or update a Fanvue chat thread.
    """

    query = """
        INSERT INTO fanvue_threads (
            thread_id,
            fanvue_user_uuid,
            fanvue_account_id,
            last_message_at,
            updated_at
        )
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT (thread_id)
        DO UPDATE SET
            fanvue_user_uuid = EXCLUDED.fanvue_user_uuid,
            fanvue_account_id = EXCLUDED.fanvue_account_id,
            last_message_at = EXCLUDED.last_message_at,
            updated_at = CURRENT_TIMESTAMP
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    thread_id,
                    fanvue_user_uuid,
                    fanvue_account_id,
                    last_message_at,
                ),
            )
            return cur.fetchone()


def fanvue_message_exists(fanvue_message_id: str) -> bool:
    """
    Check if a Fanvue message already exists.
    Used for deduplication.
    """

    query = """
        SELECT 1
        FROM fanvue_messages
        WHERE fanvue_message_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (fanvue_message_id,))
            return cur.fetchone() is not None


def save_fanvue_message(
    fanvue_message_id: str,
    thread_id: str,
    fanvue_user_uuid: str,
    fanvue_account_id: int,
    direction: str,
    message_text: str,
    message_type: str = "chat",
    ppv_set_id=None,
    price=None,
    sent_at=None,
):
    """
    Save a Fanvue message.

    Duplicate messages are skipped safely.
    """

    direction = direction.strip().lower()
    message_type = message_type.strip().lower()

    if direction not in {"inbound", "outbound"}:
        raise ValueError("direction must be inbound or outbound")

    if message_type not in {"chat", "ppv", "system"}:
        raise ValueError("message_type must be chat, ppv, or system")

    if fanvue_message_exists(fanvue_message_id):
        print(f"[FANVUE MESSAGE DUPLICATE] {fanvue_message_id}")
        return {
            "saved": False,
            "skipped": True,
            "reason": "duplicate",
            "fanvue_message_id": fanvue_message_id,
        }

    query = """
        INSERT INTO fanvue_messages (
            fanvue_message_id,
            thread_id,
            fanvue_user_uuid,
            fanvue_account_id,
            direction,
            message_text,
            message_type,
            ppv_set_id,
            price,
            sent_at
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_message_id,
                    thread_id,
                    fanvue_user_uuid,
                    fanvue_account_id,
                    direction,
                    message_text,
                    message_type,
                    ppv_set_id,
                    price,
                    sent_at,
                ),
            )

            saved_message = cur.fetchone()

            print(f"[FANVUE MESSAGE SAVED] {fanvue_message_id}")

            return {
                "saved": True,
                "skipped": False,
                "reason": None,
                "message": saved_message,
            }


def get_fanvue_messages_for_thread(thread_id: str, limit: int = 20):
    """
    Fetch recent Fanvue messages for a thread in chronological order.
    """

    query = """
        SELECT *
        FROM fanvue_messages
        WHERE thread_id = %s
        ORDER BY sent_at ASC NULLS LAST, created_at ASC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, (thread_id, limit))
            return cur.fetchall()