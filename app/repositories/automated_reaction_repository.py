from app.database import get_db_connection
from psycopg.types.json import Json


def ensure_automated_reactions_table():
    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT to_regclass('public.automated_reactions') AS table_ref;
            """
        )
        row = cur.fetchone()
        cur.close()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.automated_reactions. Run forward migrations before using AutomatedReactionRepository."
        )


def create_automated_reaction_log(
    reaction_payload: dict,
):
    ensure_automated_reactions_table()

    with get_db_connection() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            INSERT INTO automated_reactions (
                external_event_id,
                fanvue_user_id,
                fanvue_account_id,
                local_user_id,
                reaction_type,
                message_text,
                status,
                execution_mode,
                blocked_reason,
                raw_payload
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id;
            """,
            (
                reaction_payload.get(
                    "external_event_id"
                ),
                reaction_payload.get(
                    "fanvue_user_id"
                ),
                reaction_payload.get(
                    "fanvue_account_id"
                ),
                reaction_payload.get(
                    "local_user_id"
                ),
                reaction_payload.get(
                    "reaction_type"
                ),
                reaction_payload.get(
                    "message_text"
                ),
                reaction_payload.get(
                    "status",
                    "planned",
                ),
                reaction_payload.get(
                    "execution_mode"
                ),
                reaction_payload.get(
                    "blocked_reason"
                ),
                Json(reaction_payload),
            ),
        )

        row = cur.fetchone()

        conn.commit()
        cur.close()

        if isinstance(row, dict):
            return row.get("id")

        return row[0]
