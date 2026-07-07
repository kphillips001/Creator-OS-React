import json

from app.database import get_db_connection


def create_inbound_chat_message(
    fanvue_account_id: int,
    fanvue_user_uuid: str,
    fanvue_message_uuid: str,
    sender_uuid: str,
    message_text: str,
    raw_payload: dict,
):
    if not fanvue_account_id:
        raise ValueError("fanvue_account_id is required")

    insert_sql = """
        INSERT INTO fanvue_chat_messages (
            fanvue_account_id,
            fanvue_user_uuid,
            fanvue_message_uuid,
            sender_uuid,
            message_text,
            sent_at,
            is_inbound,
            raw_payload,
            created_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            NOW(),
            TRUE,
            %s,
            NOW()
        )
        ON CONFLICT (fanvue_account_id, fanvue_message_uuid)
        DO UPDATE SET
            raw_payload = EXCLUDED.raw_payload
        RETURNING id;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                insert_sql,
                (
                    fanvue_account_id,
                    str(fanvue_user_uuid),
                    str(fanvue_message_uuid),
                    str(sender_uuid),
                    message_text,
                    json.dumps(raw_payload),
                ),
            )

            row = cursor.fetchone()

        conn.commit()

    return row["id"]