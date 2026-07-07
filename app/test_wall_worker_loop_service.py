from datetime import (
    datetime,
    timedelta,
    UTC,
)

from app.repositories.wall_post_repository import (
    enqueue_wall_post,
)

from app.services.wall_worker_loop_service import (
    WallWorkerLoopService,
)


def main():

    print(
        "\n=== WALL WORKER LOOP SERVICE TEST ===\n"
    )

    scheduled_for = (
        datetime.now(UTC)
        - timedelta(minutes=1)
    )

    print(
        "[1] Creating due wall queue item..."
    )

    enqueue_wall_post(
        fanvue_account_id=1,
        content_item_id=12,
        scheduled_for=scheduled_for,
    )

    print(
        "✅ Due queue item created\n"
    )

    print(
        "[2] Running wall worker loop once..."
    )

    loop_service = (
        WallWorkerLoopService(
            poll_interval_seconds=5,
        )
    )

    result = (
        loop_service.run_once()
    )

    print(result)
    print()

    print(
        "🚀 WALL WORKER LOOP SERVICE TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()