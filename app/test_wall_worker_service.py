from datetime import (
    datetime,
    timedelta,
    UTC,
)

from app.repositories.wall_post_repository import (
    enqueue_wall_post,
)

from app.services.wall_worker_service import (
    WallWorkerService,
)


def main():

    print(
        "\n=== WALL WORKER SERVICE TEST ===\n"
    )

    # =====================================================
    # CREATE TEST QUEUE ITEMS
    # =====================================================

    print(
        "[1] Creating wall queue items..."
    )

    scheduled_for = (
        datetime.now(UTC)
        - timedelta(minutes=1)
    )

    enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=10,
        scheduled_for=scheduled_for,
    )

    enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=11,
        scheduled_for=scheduled_for,
    )

    print(
        "✅ Queue items created\n"
    )

    # =====================================================
    # RUN WORKER
    # =====================================================

    print(
        "[2] Running wall worker..."
    )

    worker = (
        WallWorkerService()
    )

    result = (
        worker.process_wall_queue()
    )

    print(result)
    print()

    print(
        "🚀 WALL WORKER SERVICE TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()