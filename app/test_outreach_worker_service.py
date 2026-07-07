from datetime import (
    datetime,
    timedelta,
    UTC,
)

from app.repositories.outreach_queue_repository import (
    enqueue_outreach,
)

from app.services.outreach_worker_service import (
    OutreachWorkerService,
)


def main():

    print(
        "\n=== OUTREACH WORKER SERVICE TEST ===\n"
    )

    scheduled_for = (
        datetime.now(UTC)
        - timedelta(minutes=1)
    )

    print(
        "[1] Creating outreach queue items..."
    )

    enqueue_outreach(
        fanvue_account_id=1,
        fanvue_user_id=1,
        outreach_type="reactivation",
        scheduled_for=scheduled_for,
    )

    enqueue_outreach(
        fanvue_account_id=1,
        fanvue_user_id=2,
        outreach_type="reactivation",
        scheduled_for=scheduled_for,
    )

    print(
        "✅ Outreach queue items created\n"
    )

    print(
        "[2] Running outreach worker..."
    )

    worker = (
        OutreachWorkerService()
    )

    result = (
        worker.process_outreach_queue()
    )

    print(result)
    print()

    print(
        "🚀 OUTREACH WORKER SERVICE TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()