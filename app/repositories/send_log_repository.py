from app.database import get_db_connection
from psycopg.types.json import Jsonb


def create_send_log_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.send_log') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.send_log. Run forward migrations before using SendLogRepository."
        )


def log_send_event(
    fanvue_account_id: int,
    fanvue_user_id: int,
    fanvue_user_uuid: str,
    message_type: str,
    route: str,
    offer_type: str,
    content_tag: str,
    price: float,
    payload: dict,
    response: dict,
):
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO send_log (
                        fanvue_account_id,
                        fanvue_user_id,
                        fanvue_user_uuid,
                        message_type,
                        route,
                        offer_type,
                        content_tag,
                        price,
                        payload,
                        response,
                        send_status
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'sent')
                    """,
                    (
                        fanvue_account_id,
                        fanvue_user_id,
                        fanvue_user_uuid,
                        message_type,
                        route,
                        offer_type,
                        content_tag,
                        price,
                        Jsonb(payload or {}),
                        Jsonb(response or {}),
                    ),
                )

    except Exception as e:
        print(f"[SEND LOG ERROR] {e}")


def list_decision_activities(fanvue_account_id: int, limit: int = 5000):
    """Read DecisionEngine activity without treating it as transport proof."""

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM send_log
                WHERE fanvue_account_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (fanvue_account_id, limit),
            )
            return cur.fetchall()


def get_decision_activity(fanvue_account_id: int, activity_id: int):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM send_log
                WHERE fanvue_account_id = %s AND id = %s
                LIMIT 1
                """,
                (fanvue_account_id, activity_id),
            )
            return cur.fetchone()
