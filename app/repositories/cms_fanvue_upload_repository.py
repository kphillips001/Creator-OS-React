from app.database import get_db_connection


def _normalize_fanvue_user_id(fanvue_user_id) -> str | None:
    if fanvue_user_id is None:
        return None

    return str(fanvue_user_id)


def log_content_unlock(
    fanvue_account_id: int,
    fanvue_user_id,
    content_tag: str = None,
    fanvue_media_uuid: str = None,
    purchase_amount: float = 0,
):
    """
    3D.5 / 3D.16

    Tracks confirmed unlock ownership.

    Section 6 hardened:
    Unlock ownership must be scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    normalized_user_id = _normalize_fanvue_user_id(fanvue_user_id)

    if not fanvue_account_id or not normalized_user_id:
        return {
            "success": False,
            "reason": "missing_account_or_user_id",
        }

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO content_usage_log (
                    fanvue_account_id,
                    fanvue_user_id,
                    content_tag,
                    fanvue_media_uuid,
                    usage_type,
                    purchase_amount,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    NOW()
                )
                RETURNING *;
                """,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    content_tag,
                    fanvue_media_uuid,
                    "content_unlocked",
                    purchase_amount,
                ),
            )

            row = cursor.fetchone()
            conn.commit()

    return dict(row) if row else {}