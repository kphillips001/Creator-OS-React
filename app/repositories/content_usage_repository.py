from app.database import get_db_connection


def _normalize_fanvue_user_id(
    fanvue_user_id,
) -> str | None:
    """
    content_usage_log.fanvue_user_id is stored as TEXT.

    Always normalize incoming bigint/int/string IDs to string
    before querying or inserting.
    """

    if fanvue_user_id is None:
        return None

    return str(fanvue_user_id)


def has_user_seen_content(
    fanvue_account_id: int,
    fanvue_user_id,
    content_item_id: int,
) -> bool:
    """
    Returns True if this Fanvue user has already received this content item.
    Used to prevent duplicate PPV / teaser sends across all pipelines.
    """

    normalized_user_id = _normalize_fanvue_user_id(
        fanvue_user_id
    )

    if not normalized_user_id or not content_item_id:
        return False

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM content_usage_log
                WHERE fanvue_account_id = %s
                  AND fanvue_user_id = %s
                  AND content_item_id = %s
                LIMIT 1;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_item_id,
                ),
            )

            return cur.fetchone() is not None


def log_content_usage(
    fanvue_account_id: int,
    fanvue_user_id,
    content_item_id: int,
    send_source: str,
    fanvue_message_id: str | None = None,
    caption_used: str | None = None,
    price: float | None = None,
    usage_type: str = "send",
    pipeline: str | None = None,
    classification: str | None = None,
) -> dict:
    """
    Logs that a content item was sent/used for a Fanvue user.
    This is the source of truth for duplicate protection.
    """

    normalized_user_id = _normalize_fanvue_user_id(
        fanvue_user_id
    )

    if not normalized_user_id:
        return {
            "success": False,
            "reason": "missing_fanvue_user_id",
        }

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO content_usage_log (
                    fanvue_account_id,
                    fanvue_user_id,
                    content_item_id,
                    send_source,
                    fanvue_message_id,
                    caption_used,
                    price,
                    usage_type,
                    pipeline,
                    classification,
                    sent_at
                )
                VALUES (
                    %s, %s, %s, %s, %s,
                    %s, %s, %s, %s, %s,
                    NOW()
                )
                RETURNING *;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_item_id,
                    send_source,
                    fanvue_message_id,
                    caption_used,
                    price,
                    usage_type,
                    pipeline,
                    classification,
                ),
            )

            row = cur.fetchone()
            conn.commit()

            print(
                f"[CONTENT USAGE LOGGED] "
                f"account={fanvue_account_id} "
                f"user_id={normalized_user_id} "
                f"content_id={content_item_id} "
                f"source={send_source}"
            )

            return dict(row) if row else {}


def has_user_seen_content_tag(
    fanvue_account_id: int,
    fanvue_user_id,
    content_tag: str,
) -> bool:
    """
    Returns True if this Fanvue user has already received content with this tag.
    Used for JSON/catalog content where no database content_item_id exists.
    """

    normalized_user_id = _normalize_fanvue_user_id(
        fanvue_user_id
    )

    if not normalized_user_id or not content_tag:
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
                LIMIT 1;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_tag,
                ),
            )

            return cur.fetchone() is not None