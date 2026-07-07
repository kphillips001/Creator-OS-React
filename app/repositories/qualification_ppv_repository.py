from app.database import get_db_connection


def create_qualification_ppv_event(
    *,
    fanvue_user_id: str,
    fanvue_account_id: str,
    qualification_type: str,
    content_tag: str = None,
    fanvue_media_uuid: str = None,
    price: float = None,
):
    """
    3D.10.2

    Tracks qualification PPV sends for:
    - new followers
    - new subscribers
    """

    sql = """
        INSERT INTO qualification_ppv_events (
            fanvue_user_id,
            fanvue_account_id,
            qualification_type,
            content_tag,
            fanvue_media_uuid,
            price,
            was_sent,
            sent_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            TRUE,
            NOW()
        )
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    fanvue_user_id,
                    fanvue_account_id,
                    qualification_type,
                    content_tag,
                    fanvue_media_uuid,
                    price,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row


def mark_qualification_ppv_purchased(
    *,
    qualification_event_id: int,
    purchase_event_id: int = None,
):
    """
    3D.10.2

    Marks qualification PPV as purchased.
    """

    sql = """
        UPDATE qualification_ppv_events
        SET
            was_purchased = TRUE,
            purchase_event_id = %s,
            purchased_at = NOW()
        WHERE id = %s
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:

            cursor.execute(
                sql,
                (
                    purchase_event_id,
                    qualification_event_id,
                ),
            )

            row = cursor.fetchone()

            conn.commit()

            return row