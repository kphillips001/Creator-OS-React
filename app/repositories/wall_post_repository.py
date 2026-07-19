from app.database import get_db_connection
from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


_claims = AtomicQueueClaimRepository(
    table="wall_post_queue", status_column="queue_status", pending_status="pending",
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
# WALL POST HISTORY TABLE
# =========================================================

def ensure_wall_post_history_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.wall_post_history') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.wall_post_history. Run forward migrations before using WallPostRepository."
        )


# =========================================================
# WALL POST QUEUE TABLE
# =========================================================

def ensure_wall_post_queue_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.wall_post_queue') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.wall_post_queue. Run forward migrations before using WallPostRepository."
        )


def init_wall_post_tables():
    ensure_wall_post_history_table()
    ensure_wall_post_queue_table()


# =========================================================
# WALL HISTORY HELPERS
# =========================================================

def has_wall_content_been_used(
    fanvue_account_id: int,
    content_item_id: int,
) -> bool:
    ensure_wall_post_history_table()

    sql = """
    SELECT 1
    FROM wall_post_history
    WHERE fanvue_account_id = %s
      AND content_item_id = %s
      AND wall_status IN ('scheduled', 'posted')
    LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (fanvue_account_id, content_item_id))
            row = cur.fetchone()

    return row is not None


def mark_wall_content_scheduled(
    fanvue_account_id: int,
    content_item_id: int,
    scheduled_for=None,
) -> dict:
    ensure_wall_post_history_table()

    sql = """
    INSERT INTO wall_post_history (
        fanvue_account_id,
        content_item_id,
        wall_status,
        delivery_method,
        scheduled_for
    )
    VALUES (%s, %s, 'scheduled', 'scheduled', %s)
    ON CONFLICT (fanvue_account_id, content_item_id)
    DO UPDATE SET
        wall_status = 'scheduled',
        delivery_method = 'scheduled',
        scheduled_for = EXCLUDED.scheduled_for,
        updated_at = NOW()
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    fanvue_account_id,
                    content_item_id,
                    scheduled_for,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}


def mark_wall_content_posted(
    fanvue_account_id: int,
    content_item_id: int,
    delivery_method: str = "post_now",
    fanvue_post_uuid: str | None = None,
) -> dict:
    ensure_wall_post_history_table()

    sql = """
    INSERT INTO wall_post_history (
        fanvue_account_id,
        content_item_id,
        wall_status,
        delivery_method,
        fanvue_post_uuid,
        posted_at
    )
    VALUES (%s, %s, 'posted', %s, %s, NOW())
    ON CONFLICT (fanvue_account_id, content_item_id)
    DO UPDATE SET
        wall_status = 'posted',
        delivery_method = EXCLUDED.delivery_method,
        fanvue_post_uuid = EXCLUDED.fanvue_post_uuid,
        posted_at = NOW(),
        updated_at = NOW()
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    fanvue_account_id,
                    content_item_id,
                    delivery_method,
                    fanvue_post_uuid,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}


# =========================================================
# WALL QUEUE HELPERS
# =========================================================

def enqueue_wall_post(
    fanvue_account_id: int,
    content_item_id: int,
    scheduled_for,
) -> dict:
    init_wall_post_tables()

    sql = """
    INSERT INTO wall_post_queue (
        fanvue_account_id,
        content_item_id,
        queue_status,
        scheduled_for
    )
    VALUES (%s, %s, 'pending', %s)
    RETURNING *;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                (
                    fanvue_account_id,
                    content_item_id,
                    scheduled_for,
                ),
            )
            row = cur.fetchone()
        conn.commit()

    mark_wall_content_scheduled(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
        scheduled_for=scheduled_for,
    )

    return dict(row) if row else {}


def fetch_due_wall_post_queue(
    limit: int = 25,
) -> list[dict]:
    ensure_wall_post_queue_table()

    sql = """
    SELECT *
    FROM wall_post_queue
    WHERE queue_status = 'pending'
      AND scheduled_for <= NOW()
    ORDER BY scheduled_for ASC, id ASC
    LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (limit,))
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def mark_wall_post_processing(
    queue_id: int,
) -> dict:
    ensure_wall_post_queue_table()

    sql = """
    UPDATE wall_post_queue
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


def mark_wall_post_completed(
    queue_id: int,
) -> dict:
    ensure_wall_post_queue_table()

    sql = """
    UPDATE wall_post_queue
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


def mark_wall_post_failed(
    queue_id: int,
    error_message: str,
    retry: bool = True,
) -> dict:
    ensure_wall_post_queue_table()

    if retry:
        sql = """
        UPDATE wall_post_queue
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
        UPDATE wall_post_queue
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
            cur.execute(sql, (error_message, queue_id))
            row = cur.fetchone()
        conn.commit()

    return dict(row) if row else {}

# =========================================================
# WALL DASHBOARD HELPERS
# =========================================================

def fetch_wall_queue_dashboard(
    fanvue_account_id: int | None = None,
    limit: int = 100,
) -> list[dict]:

    ensure_wall_post_queue_table()

    params = []

    where_clause = ""

    if fanvue_account_id:
        where_clause = """
        WHERE fanvue_account_id = %s
        """
        params.append(fanvue_account_id)

    params.append(limit)

    sql = f"""
    SELECT *
    FROM wall_post_queue

    {where_clause}

    ORDER BY created_at DESC
    LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                tuple(params),
            )
            rows = cur.fetchall()

    return [dict(row) for row in rows]


def fetch_wall_queue_counts(
    fanvue_account_id: int | None = None,
) -> dict:

    ensure_wall_post_queue_table()

    params = []

    where_clause = ""

    if fanvue_account_id:
        where_clause = """
        WHERE fanvue_account_id = %s
        """
        params.append(fanvue_account_id)

    sql = f"""
    SELECT
        COUNT(*) AS total,
        COUNT(*) FILTER (
            WHERE queue_status = 'pending'
        ) AS pending,
        COUNT(*) FILTER (
            WHERE queue_status = 'processing'
        ) AS processing,
        COUNT(*) FILTER (
            WHERE queue_status = 'completed'
        ) AS completed,
        COUNT(*) FILTER (
            WHERE queue_status = 'failed'
        ) AS failed
    FROM wall_post_queue

    {where_clause};
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                sql,
                tuple(params),
            )
            row = cur.fetchone()

    return dict(row) if row else {}
