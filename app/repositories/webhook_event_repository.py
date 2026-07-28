import json
import uuid
from datetime import datetime, timedelta

from app.database import get_db_connection
from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


_claims = AtomicQueueClaimRepository(
    table="webhook_events", status_column="status", pending_status="received",
    completed_status="processed",
    eligible_predicate=("status = 'received' OR (status = 'failed' AND next_retry_at IS NOT NULL "
                        "AND next_retry_at <= NOW())"),
    order_by="received_at ASC, id ASC",
    claim_assignments=", processing_attempts = processing_attempts + 1",
)


def claim_due_items(*, worker_instance_id: str, limit: int = 25, lease_seconds: int = 300) -> list[dict]:
    return _claims.claim_due_items(worker_instance_id=worker_instance_id, lease_seconds=lease_seconds, limit=limit)


def renew_claim(webhook_event_id: int, *, worker_instance_id: str, lease_seconds: int = 300) -> dict:
    return _claims.renew_claim(webhook_event_id, worker_instance_id=worker_instance_id, lease_seconds=lease_seconds)


def release_claim(webhook_event_id: int, *, worker_instance_id: str) -> dict:
    return _claims.release_claim(webhook_event_id, worker_instance_id=worker_instance_id)


def complete_claim(webhook_event_id: int, *, worker_instance_id: str) -> dict:
    return _claims.complete_claim(
        webhook_event_id, worker_instance_id=worker_instance_id,
        assignments="processed_at = NOW(), last_error = NULL, next_retry_at = NULL",
    )


def fail_claim(webhook_event_id: int, *, worker_instance_id: str, error_message: str,
               retry_delay_minutes: int = 5) -> dict:
    return _claims.fail_claim(
        webhook_event_id, worker_instance_id=worker_instance_id,
        assignments=("status = 'failed', retry_count = retry_count + 1, last_error = %s, "
                     "failed_at = NOW(), next_retry_at = NOW() + (%s * INTERVAL '1 minute')"),
        params=(error_message, max(1, int(retry_delay_minutes))),
    )


def recover_stale_claims(*, limit: int = 100) -> list[dict]:
    return _claims.recover_stale_claims(limit=limit)


def create_webhook_event(event: dict):
    """
    STEP 11.4
    Persist normalized webhook event into webhook_events table.
    """

    sql = """
        INSERT INTO webhook_events (
            internal_event_id,
            external_event_id,
            event_type,
            fanvue_account_id,
            fanvue_user_id,
            status,
            payload,
            headers,
            received_at
        )
        VALUES (
            %s,
            %s,
            %s,
            %s,
            %s,
            %s,
            %s::jsonb,
            %s::jsonb,
            %s
        )
        ON CONFLICT (external_event_id)
            WHERE external_event_id IS NOT NULL
        DO NOTHING
        RETURNING id;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    uuid.UUID(event["internal_event_id"]),
                    event["external_event_id"],
                    event["event_type"],
                    event["fanvue_account_id"],
                    event["fanvue_user_id"],
                    event["status"],
                    json.dumps(event["payload"]),
                    json.dumps(event["headers"]),
                    event["received_at"],
                )
            )

            row = cursor.fetchone()

            if row is None:
                webhook_event_id = None
            elif isinstance(row, dict):
                webhook_event_id = row["id"]
            else:
                webhook_event_id = row[0]

        conn.commit()

    return webhook_event_id


def get_webhook_event_by_external_id(external_event_id: str):
    """
    STEP 11.6
    Lookup existing webhook event by Fanvue external event id.
    """

    if not external_event_id:
        return None

    sql = """
        SELECT id
        FROM webhook_events
        WHERE external_event_id = %s
        LIMIT 1;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (external_event_id,))
            return cursor.fetchone()


def get_unprocessed_webhook_events(limit: int = 25):
    """
    STEP 11.7 + 11.16

    Fetch webhook events ready for processing.

    Includes:
    - newly received events
    - failed events whose retry time has arrived
    """

    sql = """
        SELECT
            id,
            internal_event_id,
            external_event_id,
            event_type,
            fanvue_account_id,
            fanvue_user_id,
            payload,
            received_at,
            status,
            retry_count,
            next_retry_at
        FROM webhook_events
        WHERE
            status = 'received'
            OR (
                status = 'failed'
                AND next_retry_at IS NOT NULL
                AND next_retry_at <= NOW()
            )
        ORDER BY received_at ASC
        LIMIT %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (limit,))
            return cursor.fetchall()


def mark_webhook_event_processing(webhook_event_id: int):
    """
    STEP 11.16
    Mark webhook event as actively processing.
    """

    sql = """
        UPDATE webhook_events
        SET
            status = 'processing',
            processing_attempts = processing_attempts + 1
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (webhook_event_id,))

        conn.commit()

    return True


def mark_webhook_event_processed(webhook_event_id: int):
    """
    STEP 11.7
    Mark webhook event as processed.
    """

    sql = """
        UPDATE webhook_events
        SET
            status = 'processed',
            processed_at = NOW(),
            last_error = NULL,
            next_retry_at = NULL
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (webhook_event_id,))

        conn.commit()

    return True


def mark_webhook_event_failed(
    webhook_event_id: int,
    error_message: str,
    retry_delay_minutes: int = 5,
):
    """
    STEP 11.15 + 11.16

    Mark webhook event as failed and retryable.
    """

    next_retry_at = (
        datetime.utcnow()
        + timedelta(minutes=retry_delay_minutes)
    )

    sql = """
        UPDATE webhook_events
        SET
            status = 'failed',
            retry_count = retry_count + 1,
            last_error = %s,
            failed_at = NOW(),
            next_retry_at = %s
        WHERE id = %s;
    """

    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                sql,
                (
                    error_message,
                    next_retry_at,
                    webhook_event_id,
                )
            )

        conn.commit()

    return True


def list_webhook_events_for_account(
    fanvue_account_id: int,
    limit: int = 250,
):
    """Return persisted webhook activity without processing or retrying it."""
    sql = """
        SELECT
            id, internal_event_id, external_event_id, event_type,
            fanvue_account_id, fanvue_user_id, status, received_at,
            processed_at, failed_at, retry_count, next_retry_at,
            last_error, processing_attempts
            , worker_instance_id, claimed_at, lease_expires_at
        FROM webhook_events
        WHERE fanvue_account_id = %s::text
        ORDER BY received_at DESC, id DESC
        LIMIT %s
    """
    with get_db_connection() as conn:
        with conn.cursor() as cursor:
            cursor.execute(sql, (fanvue_account_id, limit))
            return cursor.fetchall()
