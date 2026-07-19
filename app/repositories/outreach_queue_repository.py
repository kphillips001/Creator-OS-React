from app.database import get_db_connection
from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


_claims = AtomicQueueClaimRepository(
    table="outreach_queue",
    status_column="queue_status",
    pending_status="pending",
    completed_status="completed",
    eligible_predicate=("queue_status = 'pending' AND scheduled_for <= NOW() "
                        "AND (next_retry_at IS NULL OR next_retry_at <= NOW())"),
    order_by="scheduled_for ASC, id ASC",
    claim_assignments=", started_at = NOW(), updated_at = NOW()",
)


def claim_due_items(*, worker_instance_id: str, limit: int = 25, lease_seconds: int = 300) -> list[dict]:
    return _claims.claim_due_items(worker_instance_id=worker_instance_id, lease_seconds=lease_seconds, limit=limit)


def renew_claim(queue_id: int, *, worker_instance_id: str, lease_seconds: int = 300) -> dict:
    return _claims.renew_claim(queue_id, worker_instance_id=worker_instance_id, lease_seconds=lease_seconds)


def release_claim(queue_id: int, *, worker_instance_id: str) -> dict:
    return _claims.release_claim(queue_id, worker_instance_id=worker_instance_id)


def complete_claim(queue_id: int, *, worker_instance_id: str) -> dict:
    return _claims.complete_claim(queue_id, worker_instance_id=worker_instance_id,
                                  assignments="completed_at = NOW(), updated_at = NOW()")


def fail_claim(queue_id: int, *, worker_instance_id: str, error_message: str, retry: bool = True) -> dict:
    if retry:
        assignments = ("queue_status = 'pending', retry_count = retry_count + 1, "
                       "next_retry_at = NOW() + INTERVAL '15 minutes', error_message = %s, updated_at = NOW()")
    else:
        assignments = "queue_status = 'failed', failed_at = NOW(), error_message = %s, updated_at = NOW()"
    return _claims.fail_claim(queue_id, worker_instance_id=worker_instance_id,
                              assignments=assignments, params=(error_message,))


def recover_stale_claims(*, limit: int = 100) -> list[dict]:
    return _claims.recover_stale_claims(limit=limit)


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


def fetch_outreach_queue_dashboard(
    fanvue_account_id: int,
    limit: int = 250,
) -> list[dict]:
    """Return account-scoped Outreach queue evidence for read-only dashboards."""
    ensure_outreach_queue_table()
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM outreach_queue
                WHERE fanvue_account_id = %s
                ORDER BY created_at DESC, id DESC
                LIMIT %s
                """,
                (fanvue_account_id, limit),
            )
            rows = cur.fetchall()
    return [dict(row) for row in rows]
