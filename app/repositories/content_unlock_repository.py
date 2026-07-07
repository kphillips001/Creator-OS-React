from app.database import get_db_connection


def log_content_unlock(
    fanvue_user_id: str,
    content_tag: str = None,
    fanvue_media_uuid: str = None,
    purchase_amount: float = 0,
):
    """
    3D.5

    Tracks confirmed unlock ownership.

    This becomes the foundation for:
    - duplicate PPV prevention
    - ownership tracking
    - next-best-offer logic
    - future intimacy escalation
    """

    sql = """
        INSERT INTO content_usage_log (
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
            NOW()
        )
        RETURNING id;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    fanvue_user_id,
                    content_tag,
                    fanvue_media_uuid,
                    "content_unlocked",
                    purchase_amount,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row