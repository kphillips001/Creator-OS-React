import json

from app.database import get_db_connection


def log_broadcast_send(
    fanvue_account_id: int,
    fanvue_user_id,
    content_tag: str,
    campaign_type: str = None,
    offer_type: str = None,
    status: str = "sent",
    metadata: dict = None,
):
    """
    Logs a PPV broadcast send under a specific creator account.
    """

    if not fanvue_account_id:
        return None

    if not fanvue_user_id:
        return None

    metadata_json = json.dumps(metadata) if metadata is not None else None
    normalized_user_id = str(fanvue_user_id)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO ppv_broadcast_logs (
                    fanvue_account_id,
                    fanvue_user_id,
                    campaign_type,
                    content_tag,
                    offer_type,
                    status,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING *;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    campaign_type,
                    content_tag,
                    offer_type,
                    status,
                    metadata_json,
                ),
            )

            row = cur.fetchone()
            conn.commit()

            return dict(row) if row else {}


def has_user_received_content_recently(
    fanvue_account_id: int,
    fanvue_user_id,
    content_tag: str,
    hours: int = 24,
) -> bool:
    """
    Checks whether this user recently received this content
    under this specific creator account.
    """

    if not fanvue_account_id:
        return False

    if not fanvue_user_id or not content_tag:
        return False

    normalized_user_id = str(fanvue_user_id)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM ppv_broadcast_logs
                WHERE fanvue_account_id = %s
                  AND fanvue_user_id = %s
                  AND content_tag = %s
                  AND created_at >= NOW() - (%s * INTERVAL '1 hour')
                LIMIT 1
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_tag,
                    hours,
                ),
            )

            return cur.fetchone() is not None


def get_recent_broadcasts_for_user(
    fanvue_account_id: int,
    fanvue_user_id,
    limit: int = 10,
):
    """
    Returns recent PPV broadcasts only for this creator account + user.
    """

    if not fanvue_account_id:
        return []

    if not fanvue_user_id:
        return []

    normalized_user_id = str(fanvue_user_id)

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM ppv_broadcast_logs
                WHERE fanvue_account_id = %s
                  AND fanvue_user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    limit,
                ),
            )

            rows = cur.fetchall()

            return [dict(row) for row in rows]