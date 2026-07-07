from app.database import get_db_connection


OWNERSHIP_USAGE_TYPES = [
    "ppv_purchased",
    "content_unlocked",
    "content_owned",
    "purchase",
    "unlock",
    "owned",
]


def _normalize_fanvue_user_id(fanvue_user_id) -> str | None:
    if fanvue_user_id is None:
        return None

    return str(fanvue_user_id)


def get_owned_content_tags(
    fanvue_account_id: int,
    fanvue_user_id,
):
    """
    Returns all content tags owned by this fan for this specific creator account.
    """

    normalized_user_id = _normalize_fanvue_user_id(fanvue_user_id)

    if not fanvue_account_id or not normalized_user_id:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT content_tag
                FROM content_usage_log
                WHERE fanvue_account_id = %s
                  AND fanvue_user_id = %s
                  AND usage_type = ANY(%s)
                  AND content_tag IS NOT NULL;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    OWNERSHIP_USAGE_TYPES,
                ),
            )

            rows = cur.fetchall()

    return [row["content_tag"] for row in rows]


def user_already_owns_content(
    fanvue_account_id: int,
    fanvue_user_id,
    content_tag: str,
):
    """
    Returns True only if this fan owns this content under this creator account.
    """

    normalized_user_id = _normalize_fanvue_user_id(fanvue_user_id)

    if not fanvue_account_id or not normalized_user_id or not content_tag:
        return False

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM content_usage_log
                WHERE fanvue_account_id = %s
                  AND fanvue_user_id = %s
                  AND content_tag = %s
                  AND usage_type = ANY(%s)
                LIMIT 1;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_tag,
                    OWNERSHIP_USAGE_TYPES,
                ),
            )

            row = cur.fetchone()

    return row is not None