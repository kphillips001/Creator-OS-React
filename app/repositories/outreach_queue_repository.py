from app.database import get_db_connection


# =========================================================
# OUTREACH QUEUE TABLE
# =========================================================

def ensure_outreach_queue_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.outreach_queue') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.outreach_queue. Run forward migrations before using OutreachQueueRepository."
        )


# =========================================================
# QUEUE HELPERS
# =========================================================

def enqueue_outreach(
    fanvue_account_id: int,
    fanvue_user_id: int,
    scheduled_for,
    outreach_type: str = "reactivation",
) -> dict:
    ensure_outreach_queue_table()

    sql = """
    INSERT INTO outreach_queue (
        fanvue_account_id,
        fanvue_user_id,
        outreach_type,
        queue_status,
        scheduled_for
    )
    VALUES (%s, %s, %s, 'pending', %s)
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    fanvue_account_id,
                    fanvue_user_id,
                    outreach_type,
                    scheduled_for,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}


def fetch_due_outreach_queue(
    limit: int = 25,
) -> list[dict]:
    ensure_outreach_queue_table()

    sql = """
    SELECT *
    FROM outreach_queue
    WHERE queue_status = 'pending'
      AND scheduled_for <= NOW()
      AND (
            next_retry_at IS NULL
            OR next_retry_at <= NOW()
      )
    ORDER BY scheduled_for ASC, id ASC
    LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def mark_outreach_processing(
    queue_id: int,
) -> dict:
    ensure_outreach_queue_table()

    sql = """
    UPDATE outreach_queue
    SET
        queue_status = 'processing',
        started_at = NOW(),
        updated_at = NOW()
    WHERE id = %s
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (queue_id,))
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}


def mark_outreach_completed(
    queue_id: int,
) -> dict:
    ensure_outreach_queue_table()

    sql = """
    UPDATE outreach_queue
    SET
        queue_status = 'completed',
        completed_at = NOW(),
        updated_at = NOW()
    WHERE id = %s
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (queue_id,))
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}


def mark_outreach_failed(
    queue_id: int,
    error_message: str,
    retry: bool = True,
) -> dict:
    ensure_outreach_queue_table()

    if retry:
        sql = """
        UPDATE outreach_queue
        SET
            queue_status = 'pending',
            retry_count = retry_count + 1,
            next_retry_at = NOW() + INTERVAL '15 minutes',
            error_message = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *;
        """
    else:
        sql = """
        UPDATE outreach_queue
        SET
            queue_status = 'failed',
            failed_at = NOW(),
            error_message = %s,
            updated_at = NOW()
        WHERE id = %s
        RETURNING *;
        """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    error_message,
                    queue_id,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}
