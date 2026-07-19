from app.database import get_db_connection
from app.repositories.atomic_queue_claim_repository import AtomicQueueClaimRepository


def _claims(*, retryable: bool = False) -> AtomicQueueClaimRepository:
    eligible = "status = 'failed' AND retry_count < %s" if retryable else "status = 'pending'"
    return AtomicQueueClaimRepository(
        table="mass_ppv_queue", status_column="status", pending_status="pending",
        completed_status="completed", eligible_predicate=eligible, order_by="id ASC",
        claim_assignments=", processing_started_at = NOW(), updated_at = NOW()",
    )


def claim_due_items(*, worker_instance_id: str, limit: int = 25, lease_seconds: int = 900,
                    retryable: bool = False, retry_limit: int = 3) -> list[dict]:
    return _claims(retryable=retryable).claim_due_items(
        worker_instance_id=worker_instance_id, lease_seconds=lease_seconds, limit=limit,
        predicate_params=(retry_limit,) if retryable else (),
    )


def renew_claim(queue_id: int, *, worker_instance_id: str, lease_seconds: int = 900) -> dict:
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


# =========================================================
# CREATE MASS PPV CAMPAIGN
# =========================================================

def create_mass_ppv_campaign(
    campaign_name: str,
    fanvue_account_id: int,
    content_id: int,
    caption: str,
    price: float,
    scheduled_for=None,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mass_ppv_campaigns (
                    campaign_name,
                    fanvue_account_id,
                    content_id,
                    caption,
                    price,
                    status,
                    scheduled_for,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    %s,
                    %s,
                    %s,
                    'pending',
                    %s,
                    NOW()
                )
                RETURNING id;
                """,
                (
                    campaign_name,
                    fanvue_account_id,
                    content_id,
                    caption,
                    price,
                    scheduled_for,
                ),
            )

            row = cur.fetchone()

        conn.commit()

    return row["id"]


# =========================================================
# CREATE QUEUE ENTRY
# =========================================================

def create_mass_ppv_queue_entry(
    campaign_id: int,
    fanvue_user_id,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO mass_ppv_queue (
                    campaign_id,
                    fanvue_user_id,
                    status,
                    retry_count,
                    created_at
                )
                VALUES (
                    %s,
                    %s,
                    'pending',
                    0,
                    NOW()
                )
                RETURNING id;
                """,
                (
                    campaign_id,
                    str(fanvue_user_id),
                ),
            )

            row = cur.fetchone()

        conn.commit()

    return row["id"]


# =========================================================
# FETCH PENDING QUEUE ITEMS
# =========================================================

def fetch_pending_mass_ppv_queue(
    limit: int = 25,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    campaign_id,
                    fanvue_user_id,
                    retry_count
                FROM mass_ppv_queue
                WHERE status = 'pending'
                ORDER BY id ASC
                LIMIT %s;
                """,
                (limit,),
            )

            rows = cur.fetchall()

    return rows


# =========================================================
# MARK QUEUE ITEM PROCESSING
# =========================================================

def mark_mass_ppv_processing(
    queue_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mass_ppv_queue
                SET
                    status = 'processing',
                    processing_started_at = NOW()
                WHERE id = %s;
                """,
                (queue_id,),
            )

        conn.commit()


# =========================================================
# MARK QUEUE ITEM COMPLETED
# =========================================================

def mark_mass_ppv_completed(
    queue_id: int,
    fanvue_message_id: str | None = None,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mass_ppv_queue
                SET
                    status = 'completed',
                    completed_at = NOW(),
                    fanvue_message_id = %s
                WHERE id = %s;
                """,
                (
                    fanvue_message_id,
                    queue_id,
                ),
            )

        conn.commit()


# =========================================================
# MARK QUEUE ITEM FAILED
# =========================================================

def mark_mass_ppv_failed(
    queue_id: int,
    failure_reason: str,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mass_ppv_queue
                SET
                    status = 'failed',
                    retry_count = retry_count + 1,
                    last_error = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (
                    failure_reason,
                    queue_id,
                ),
            )

        conn.commit()


# =========================================================
# RESET FAILED QUEUE ITEM
# =========================================================

def reset_mass_ppv_failed_item(
    queue_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mass_ppv_queue
                SET
                    status = 'pending',
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (queue_id,),
            )

        conn.commit()


# =========================================================
# FETCH FAILED RETRYABLE ITEMS
# =========================================================

def fetch_retryable_mass_ppv_queue(
    retry_limit: int = 3,
    limit: int = 25,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    campaign_id,
                    fanvue_user_id,
                    retry_count
                FROM mass_ppv_queue
                WHERE status = 'failed'
                AND retry_count < %s
                ORDER BY id ASC
                LIMIT %s;
                """,
                (
                    retry_limit,
                    limit,
                ),
            )

            rows = cur.fetchall()

    return rows


# =========================================================
# UPDATE CAMPAIGN STATUS
# =========================================================

def update_campaign_status(
    campaign_id: int,
    status: str,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE mass_ppv_campaigns
                SET
                    status = %s,
                    updated_at = NOW()
                WHERE id = %s;
                """,
                (
                    status,
                    campaign_id,
                ),
            )

        conn.commit()


# =========================================================
# FETCH CAMPAIGN
# =========================================================

def fetch_campaign(
    campaign_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    campaign_name,
                    fanvue_account_id,
                    content_id,
                    caption,
                    price,
                    status,
                    scheduled_for,
                    created_at
                FROM mass_ppv_campaigns
                WHERE id = %s;
                """,
                (campaign_id,),
            )

            row = cur.fetchone()

    return row


# =========================================================
# FETCH PENDING CAMPAIGNS
# =========================================================

def fetch_pending_campaigns():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    campaign_name,
                    fanvue_account_id,
                    content_id,
                    caption,
                    price,
                    scheduled_for
                FROM mass_ppv_campaigns
                WHERE status = 'pending'
                ORDER BY created_at ASC;
                """
            )

            rows = cur.fetchall()

    return rows


# =========================================================
# CAMPAIGN STATUS
# =========================================================

def get_campaign_status(
    campaign_id: int,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*) as total,
                    COUNT(*) FILTER (
                        WHERE status = 'completed'
                    ) as completed,
                    COUNT(*) FILTER (
                        WHERE status = 'failed'
                    ) as failed,
                    COUNT(*) FILTER (
                        WHERE status = 'pending'
                    ) as pending,
                    COUNT(*) FILTER (
                        WHERE status = 'processing'
                    ) as processing
                FROM mass_ppv_queue
                WHERE campaign_id = %s;
                """,
                (campaign_id,),
            )

            row = cur.fetchone()

    return {
        "total": row["total"],
        "completed": row["completed"],
        "failed": row["failed"],
        "pending": row["pending"],
        "processing": row["processing"],
    }


# =========================================================
# PENDING COUNT
# =========================================================

def get_pending_queue_count():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM mass_ppv_queue
                WHERE status = 'pending';
                """
            )

            row = cur.fetchone()

    return row["count"]


# =========================================================
# FAILED COUNT
# =========================================================

def get_failed_queue_count():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM mass_ppv_queue
                WHERE status = 'failed';
                """
            )

            row = cur.fetchone()

    return row["count"]


# =========================================================
# COMPLETED COUNT
# =========================================================

def get_completed_queue_count():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) AS count
                FROM mass_ppv_queue
                WHERE status = 'completed';
                """
            )

            row = cur.fetchone()

    return row["count"]

# =========================================================
# FETCH FANVUE USER FOR MASS PPV QUEUE
# =========================================================
def fetch_mass_ppv_user_for_queue(
    fanvue_user_id,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    fanvue_user_uuid,
                    username,
                    display_name,
                    relationship_status,
                    is_follower,
                    is_subscriber
                FROM fanvue_users
                WHERE id::text = %s
                LIMIT 1;
                """,
                (
                    str(fanvue_user_id),
                ),
            )

            row = cur.fetchone()
            return row
        
# =========================================================
# MASS PPV DASHBOARD — CAMPAIGN MONITOR
# =========================================================
def fetch_mass_ppv_campaign_dashboard_rows(
    fanvue_account_id: int | None = None,
    limit: int = 50,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:

            params = []

            where_clause = ""

            if fanvue_account_id:
                where_clause = """
                WHERE c.fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    c.id,
                    c.campaign_name,
                    c.fanvue_account_id,
                    c.content_id,
                    c.caption,
                    c.price,
                    c.status,
                    c.scheduled_for,
                    c.created_at,
                    c.updated_at,

                    COUNT(q.id) AS total_queue,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'pending'
                    ) AS pending_count,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'processing'
                    ) AS processing_count,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'completed'
                    ) AS completed_count,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'failed'
                    ) AS failed_count,
                    COALESCE(SUM(q.retry_count), 0) AS retry_count

                FROM mass_ppv_campaigns c
                LEFT JOIN mass_ppv_queue q
                    ON q.campaign_id = c.id

                {where_clause}

                GROUP BY
                    c.id,
                    c.campaign_name,
                    c.fanvue_account_id,
                    c.content_id,
                    c.caption,
                    c.price,
                    c.status,
                    c.scheduled_for,
                    c.created_at,
                    c.updated_at
                ORDER BY c.created_at DESC
                LIMIT %s;
                """,
                tuple(params),
            )

            return cur.fetchall()
        
# =========================================================
# MASS PPV DASHBOARD — QUEUE VIEWER
# =========================================================
def fetch_mass_ppv_queue_dashboard_rows(
    fanvue_account_id: int | None = None,
    status: str | None = None,
    limit: int = 100,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:

            where_clauses = []
            params = []

            if fanvue_account_id:
                where_clauses.append(
                    "c.fanvue_account_id = %s"
                )
                params.append(fanvue_account_id)

            if status and status != "all":
                where_clauses.append(
                    "q.status = %s"
                )
                params.append(status)

            where_sql = ""

            if where_clauses:
                where_sql = (
                    "WHERE "
                    + " AND ".join(where_clauses)
                )

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    q.id,
                    q.campaign_id,
                    c.campaign_name,
                    c.fanvue_account_id,
                    q.fanvue_user_id,
                    fu.username,
                    fu.fanvue_user_uuid,
                    q.status,
                    q.retry_count,
                    q.last_error,
                    q.fanvue_message_id,
                    q.created_at,
                    q.updated_at,
                    q.processing_started_at,
                    q.worker_instance_id,
                    q.claimed_at,
                    q.lease_expires_at,
                    q.completed_at
                FROM mass_ppv_queue q
                LEFT JOIN mass_ppv_campaigns c
                    ON c.id = q.campaign_id
                LEFT JOIN fanvue_users fu
                    ON fu.id::text = q.fanvue_user_id::text

                {where_sql}

                ORDER BY q.id DESC
                LIMIT %s;
                """,
                tuple(params),
            )

            return cur.fetchall()


# =========================================================
# MASS PPV DASHBOARD — BASIC ANALYTICS
# =========================================================
def fetch_mass_ppv_campaign_analytics_rows(
    fanvue_account_id: int | None = None,
    limit: int = 50,
):
    with get_db_connection() as conn:
        with conn.cursor() as cur:

            params = []

            where_clause = ""

            if fanvue_account_id:
                where_clause = """
                WHERE c.fanvue_account_id = %s
                """
                params.append(fanvue_account_id)

            params.append(limit)

            cur.execute(
                f"""
                SELECT
                    c.id AS campaign_id,
                    c.campaign_name,
                    c.fanvue_account_id,
                    c.content_id,
                    c.price,
                    c.status,

                    COUNT(q.id) AS queued_total,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'completed'
                    ) AS sent_total,
                    COUNT(q.id) FILTER (
                        WHERE q.status = 'failed'
                    ) AS failed_total,
                    COALESCE(SUM(q.retry_count), 0) AS retry_total,

                    COUNT(cul.id) FILTER (
                        WHERE cul.usage_type IN (
                            'open',
                            'opened',
                            'view',
                            'viewed'
                        )
                    ) AS opened_total,

                    COUNT(cul.id) FILTER (
                        WHERE cul.usage_type IN (
                            'purchase',
                            'purchased',
                            'unlock',
                            'unlocked'
                        )
                    ) AS purchased_total

                FROM mass_ppv_campaigns c
                LEFT JOIN mass_ppv_queue q
                    ON q.campaign_id = c.id
                LEFT JOIN content_usage_log cul
                    ON cul.content_item_id = c.content_id
                    AND cul.fanvue_account_id = c.fanvue_account_id

                {where_clause}

                GROUP BY
                    c.id,
                    c.campaign_name,
                    c.fanvue_account_id,
                    c.content_id,
                    c.price,
                    c.status
                ORDER BY c.id DESC
                LIMIT %s;
                """,
                tuple(params),
            )

            rows = cur.fetchall()

    analytics_rows = []

    for row in rows:
        queued_total = row.get("queued_total") or 0
        sent_total = row.get("sent_total") or 0
        opened_total = row.get("opened_total") or 0
        purchased_total = row.get("purchased_total") or 0

        open_rate = 0
        purchase_rate = 0

        if sent_total:
            open_rate = round(
                (opened_total / sent_total) * 100,
                2,
            )
            purchase_rate = round(
                (purchased_total / sent_total) * 100,
                2,
            )

        analytics_row = dict(row)
        analytics_row["open_rate"] = open_rate
        analytics_row["purchase_rate"] = purchase_rate

        analytics_rows.append(analytics_row)

    return analytics_rows
