from datetime import datetime, timedelta

from app.repositories.wall_post_repository import (
    init_wall_post_tables,
    enqueue_wall_post,
    fetch_due_wall_post_queue,
    mark_wall_post_processing,
    mark_wall_post_completed,
    mark_wall_post_failed,
)


def main():
    print(
        "\n=== WALL SCHEDULER REPOSITORY TEST ===\n"
    )

    # =====================================================
    # INIT TABLES
    # =====================================================

    print(
        "[1] Initializing wall tables..."
    )

    init_wall_post_tables()

    print(
        "✅ Tables initialized\n"
    )

    # =====================================================
    # ENQUEUE TEST
    # =====================================================

    print(
        "[2] Creating scheduled wall queue item..."
    )

    scheduled_for = (
        datetime.utcnow() - timedelta(minutes=1)
    )

    queue_item = enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=1,
        scheduled_for=scheduled_for,
    )

    print(
        "✅ Queue Item Created:"
    )

    print(queue_item)
    print()

    queue_id = queue_item["id"]

    # =====================================================
    # FETCH DUE QUEUE
    # =====================================================

    print(
        "[3] Fetching due wall queue..."
    )

    due_queue = fetch_due_wall_post_queue()

    print(
        f"✅ Due Queue Count: {len(due_queue)}"
    )

    for item in due_queue:
        print(item)

    print()

    # =====================================================
    # PROCESSING TEST
    # =====================================================

    print(
        "[4] Marking queue item processing..."
    )

    processing_result = (
        mark_wall_post_processing(
            queue_id
        )
    )

    print(
        "✅ Processing Result:"
    )

    print(processing_result)
    print()

    # =====================================================
    # COMPLETION TEST
    # =====================================================

    print(
        "[5] Marking queue item completed..."
    )

    completed_result = (
        mark_wall_post_completed(
            queue_id
        )
    )

    print(
        "✅ Completed Result:"
    )

    print(completed_result)
    print()

    # =====================================================
    # FAILURE / RETRY TEST
    # =====================================================

    print(
        "[6] Creating retry test queue item..."
    )

    retry_item = enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=2,
        scheduled_for=scheduled_for,
    )

    retry_queue_id = retry_item["id"]

    failed_result = (
        mark_wall_post_failed(
            queue_id=retry_queue_id,
            error_message="Test retry failure",
            retry=True,
        )
    )

    print(
        "✅ Retry Result:"
    )

    print(failed_result)
    print()

    # =====================================================
    # FINAL FAILED TEST
    # =====================================================

    print(
        "[7] Creating permanent failure test..."
    )

    failed_item = enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=3,
        scheduled_for=scheduled_for,
    )

    failed_queue_id = failed_item["id"]

    permanent_failure = (
        mark_wall_post_failed(
            queue_id=failed_queue_id,
            error_message="Permanent failure",
            retry=False,
        )
    )

    print(
        "✅ Permanent Failure Result:"
    )

    print(permanent_failure)
    print()

    print(
        "🚀 WALL SCHEDULER REPOSITORY TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()