from app.database import get_db_connection


def log_outreach_attempt(
    fanvue_account_id: int,
    fanvue_user_id,
    opener_text: str,
    campaign_type: str = "outreach",
    dry_run: bool = True,
):
    """
    Logs an outreach attempt safely under a creator account.
    """

    if not fanvue_account_id:
        return None

    if not fanvue_user_id:
        return None

    normalized_user_id = str(fanvue_user_id)

    query = """
        INSERT INTO outreach_log (
            fanvue_account_id,
            fanvue_user_id,
            opener_text,
            campaign_type,
            dry_run,
            created_at
        )
        VALUES (%s, %s, %s, %s, %s, NOW())
        RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    opener_text,
                    campaign_type,
                    dry_run,
                ),
            )

            row = cur.fetchone()
            conn.commit()

            return dict(row) if row else {}


def get_recent_outreach_logs_for_user(
    fanvue_account_id: int,
    fanvue_user_id,
    limit: int = 20,
):
    """
    Returns recent outreach attempts ONLY for this creator account + user pair.
    """

    if not fanvue_account_id:
        return []

    if not fanvue_user_id:
        return []

    normalized_user_id = str(fanvue_user_id)

    query = """
        SELECT *
        FROM outreach_log
        WHERE fanvue_account_id = %s
        AND fanvue_user_id = %s
        ORDER BY created_at DESC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                query,
                (
                    fanvue_account_id,
                    normalized_user_id,
                    limit,
                ),
            )

            rows = cur.fetchall()

            return [dict(row) for row in rows]