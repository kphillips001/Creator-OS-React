from datetime import (
    datetime,
    timedelta,
    UTC,
)

from app.repositories.outreach_queue_repository import (
    ensure_outreach_queue_table,
    enqueue_outreach,
    fetch_due_outreach_queue,
    mark_outreach_processing,
    mark_outreach_completed,
    mark_outreach_failed,
)


def main():

    print(
        "\n=== OUTREACH QUEUE REPOSITORY TEST ===\n"
    )

    print(
        "[1] Initializing outreach queue table..."
    )

    ensure_outreach_queue_table()

    print(
        "✅ Outreach queue table initialized\n"
    )

    scheduled_for = (
        datetime.now(UTC)
        - timedelta(minutes=1)
    )

    print(
        "[2] Creating outreach queue item..."
    )

    queue_item = enqueue_outreach(
        fanvue_account_id=1,
        fanvue_user_id=1,
        outreach_type="reactivation",
        scheduled_for=scheduled_for,
    )

    print(queue_item)
    print()

    queue_id = queue_item["id"]

    print(
        "[3] Fetching due outreach queue..."
    )

    due_items = fetch_due_outreach_queue()

    print(
        f"Due Outreach Count: {len(due_items)}"
    )

    for item in due_items[:5]:
        print(item)

    print()

    print(
        "[4] Marking outreach processing..."
    )

    processing = mark_outreach_processing(
        queue_id
    )

    print(processing)
    print()

    print(
        "[5] Marking outreach completed..."
    )

    completed = mark_outreach_completed(
        queue_id
    )

    print(completed)
    print()

    print(
        "[6] Testing retry failure..."
    )

    retry_item = enqueue_outreach(
        fanvue_account_id=1,
        fanvue_user_id=2,
        outreach_type="reactivation",
        scheduled_for=scheduled_for,
    )

    retry_result = mark_outreach_failed(
        queue_id=retry_item["id"],
        error_message="Test retry failure",
        retry=True,
    )

    print(retry_result)
    print()

    print(
        "[7] Testing permanent failure..."
    )

    failed_item = enqueue_outreach(
        fanvue_account_id=1,
        fanvue_user_id=3,
        outreach_type="reactivation",
        scheduled_for=scheduled_for,
    )

    failed_result = mark_outreach_failed(
        queue_id=failed_item["id"],
        error_message="Permanent failure",
        retry=False,
    )

    print(failed_result)
    print()

    print(
        "🚀 OUTREACH QUEUE REPOSITORY TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()