from app.database import get_db_connection
from psycopg.types.json import Json
from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


def _claims(account_scoped: bool = False) -> AtomicQueueClaimRepository:
    account_filter = " AND fanvue_account_id = %s" if account_scoped else ""
    return AtomicQueueClaimRepository(
        table="delayed_message_queue", status_column="status", pending_status="pending",
        completed_status="completed",
        eligible_predicate=("status = 'pending' AND scheduled_for <= NOW() "
                            "AND (expires_at IS NULL OR expires_at > NOW())" + account_filter),
        order_by="scheduled_for ASC, id ASC",
        claim_assignments=", processing_started_at = NOW(), updated_at = NOW()",
        stale_scope_predicate="fanvue_account_id = %s" if account_scoped else "TRUE",
    )


def claim_due_items(*, worker_instance_id: str, fanvue_account_id: int | None = None,
                    limit: int = 25, lease_seconds: int = 300) -> list[dict]:
    return _claims(fanvue_account_id is not None).claim_due_items(
        worker_instance_id=worker_instance_id, lease_seconds=lease_seconds, limit=limit,
        predicate_params=(fanvue_account_id,) if fanvue_account_id is not None else (),
        stale_scope_params=(fanvue_account_id,) if fanvue_account_id is not None else (),
    )


def renew_claim(queue_id: int, *, worker_instance_id: str, lease_seconds: int = 300) -> dict:
    return _claims().renew_claim(queue_id, worker_instance_id=worker_instance_id, lease_seconds=lease_seconds)


def release_claim(queue_id: int, *, worker_instance_id: str) -> dict:
    return _claims().release_claim(queue_id, worker_instance_id=worker_instance_id)


def complete_claim(queue_id: int, *, worker_instance_id: str, fanvue_message_id: str | None = None) -> dict:
    return _claims().complete_claim(queue_id, worker_instance_id=worker_instance_id,
                                    assignments="completed_at = NOW(), fanvue_message_id = %s, updated_at = NOW()",
                                    params=(fanvue_message_id,))


def fail_claim(queue_id: int, *, worker_instance_id: str, failure_reason: str) -> dict:
    return _claims().fail_claim(
        queue_id, worker_instance_id=worker_instance_id,
        assignments="status = 'failed', retry_count = retry_count + 1, last_error = %s, updated_at = NOW()",
        params=(failure_reason,),
    )


def recover_stale_claims(*, limit: int = 100) -> list[dict]:
    return _claims().recover_stale_claims(limit=limit)


def ensure_delayed_message_queue_table():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.delayed_message_queue') AS table_ref;")
            row = cur.fetchone()
    if not row or not row["table_ref"]:
        raise RuntimeError(
            "Missing public.delayed_message_queue. Run forward migrations before using DelayedMessageQueueRepository."
        )


def create_delayed_message(
    fanvue_user_id,
    message_body: str,
    scheduled_for,
    fanvue_account_id: int,
    payload: dict | None = None,
    expires_at=None,
    max_retries: int = 3,
):
    if not fanvue_account_id:
        raise ValueError("fanvue_account_id is required for delayed messages")

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO delayed_message_queue (
                    fanvue_account_id,
                    fanvue_user_id,
                    message_body,
                    payload,
                    status,
                    scheduled_for,
                    expires_at,
                    max_retries,
                    created_at,
                    updated_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    'pending',
                    %s,
                    %s,
                    %s,
                    NOW(),
                    NOW()
                )
                RETURNING id;
                """,
                (
                    fanvue_account_id,
                    str(fanvue_user_id),
                    message_body,
                    Json(payload or {}),
                    scheduled_for,
                    expires_at,
                    max_retries,
                ),
            )

            row = cur.fetchone()
            conn.commit()

            return row["id"]


def fetch_due_delayed_messages(
    fanvue_account_id: int | None = None,
    limit: int = 25,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            params = []

            account_filter = ""

            if fanvue_account_id:
                account_filter = """
                AND fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    id,
                    fanvue_account_id,
                    fanvue_user_id,
                    message_body,
                    payload,
                    status,
                    scheduled_for,
                    expires_at,
                    retry_count,
                    max_retries
                FROM delayed_message_queue
                WHERE status = 'pending'
                AND scheduled_for <= NOW()

                {account_filter}

                AND (
                    expires_at IS NULL
                    OR expires_at > NOW()
                )
                ORDER BY scheduled_for ASC, id ASC
                LIMIT %s;
                """,
                tuple(params),
            )

            return cur.fetchall()


def mark_delayed_message_processing(
    queue_id: int,
    fanvue_account_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE delayed_message_queue
                SET
                    status = 'processing',
                    processing_started_at = NOW(),
                    updated_at = NOW()
                WHERE id = %s
                AND fanvue_account_id = %s;
                """,
                (
                    queue_id,
                    fanvue_account_id,
                ),
            )

            conn.commit()


def mark_delayed_message_completed(
    queue_id: int,
    fanvue_account_id: int,
    fanvue_message_id: str | None = None,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE delayed_message_queue
                SET
                    status = 'completed',
                    completed_at = NOW(),
                    fanvue_message_id = %s,
                    updated_at = NOW()
                WHERE id = %s
                AND fanvue_account_id = %s;
                """,
                (
                    fanvue_message_id,
                    queue_id,
                    fanvue_account_id,
                ),
            )

            conn.commit()


def mark_delayed_message_failed(
    queue_id: int,
    fanvue_account_id: int,
    failure_reason: str,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE delayed_message_queue
                SET
                    status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = %s,
                    updated_at = NOW()
                WHERE id = %s
                AND fanvue_account_id = %s;
                """,
                (
                    failure_reason,
                    queue_id,
                    fanvue_account_id,
                ),
            )

            conn.commit()


def fetch_retryable_delayed_messages(
    fanvue_account_id: int | None = None,
    retry_limit: int = 3,
    limit: int = 25,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            params = [retry_limit]

            account_filter = ""

            if fanvue_account_id:
                account_filter = """
                AND fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    id,
                    fanvue_account_id,
                    fanvue_user_id,
                    message_body,
                    payload,
                    retry_count,
                    max_retries
                FROM delayed_message_queue
                WHERE status = 'failed'
                AND retry_count < %s

                {account_filter}

                ORDER BY updated_at ASC, id ASC
                LIMIT %s;
                """,
                tuple(params),
            )

            return cur.fetchall()


def reset_delayed_message_for_retry(
    queue_id: int,
    fanvue_account_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE delayed_message_queue
                SET
                    status = 'pending',
                    updated_at = NOW()
                WHERE id = %s
                AND fanvue_account_id = %s;
                """,
                (
                    queue_id,
                    fanvue_account_id,
                ),
            )

            conn.commit()


def cancel_delayed_message(
    queue_id: int,
    fanvue_account_id: int,
    reason: str = "cancelled",
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE delayed_message_queue
                SET
                    status = 'cancelled',
                    cancelled_at = NOW(),
                    last_error = %s,
                    updated_at = NOW()
                WHERE id = %s
                AND fanvue_account_id = %s
                AND status IN ('pending', 'failed');
                """,
                (
                    reason,
                    queue_id,
                    fanvue_account_id,
                ),
            )

            conn.commit()


def expire_old_delayed_messages(
    fanvue_account_id: int | None = None,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            params = []

            account_filter = ""

            if fanvue_account_id:
                account_filter = """
                AND fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            cur.execute(
                f"""
                UPDATE delayed_message_queue
                SET
                    status = 'expired',
                    expired_at = NOW(),
                    updated_at = NOW()
                WHERE status = 'pending'
                AND expires_at IS NOT NULL
                AND expires_at <= NOW()

                {account_filter}

                RETURNING id;
                """,
                tuple(params),
            )

            rows = cur.fetchall()
            conn.commit()

            return rows


def get_delayed_message_queue_counts(
    fanvue_account_id: int | None = None,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            params = []

            where_clause = ""

            if fanvue_account_id:
                where_clause = """
                WHERE fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            cur.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (
                        WHERE status = 'pending'
                    ) AS pending,

                    COUNT(*) FILTER (
                        WHERE status = 'processing'
                    ) AS processing,

                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                    ) AS completed,

                    COUNT(*) FILTER (
                        WHERE status = 'failed'
                    ) AS failed,

                    COUNT(*) FILTER (
                        WHERE status = 'cancelled'
                    ) AS cancelled,

                    COUNT(*) FILTER (
                        WHERE status = 'expired'
                    ) AS expired

                FROM delayed_message_queue

                {where_clause};
                """,
                tuple(params),
            )

            return cur.fetchone()


def fetch_recent_delayed_messages(
    fanvue_account_id: int | None = None,
    limit: int = 25,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            params = []

            where_clause = ""

            if fanvue_account_id:
                where_clause = """
                WHERE fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    id,
                    fanvue_account_id,
                    fanvue_user_id,
                    message_body,
                    status,
                    retry_count,
                    max_retries,
                    last_error,
                    scheduled_for,
                    created_at,
                    updated_at,
                    processing_started_at,
                    worker_instance_id,
                    claimed_at,
                    lease_expires_at,
                    completed_at,
                    cancelled_at,
                    expired_at

                FROM delayed_message_queue

                {where_clause}

                ORDER BY id DESC
                LIMIT %s;
                """,
                tuple(params),
            )

            return cur.fetchall()
