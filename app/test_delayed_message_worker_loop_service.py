from datetime import (
    datetime,
    timedelta,
    timezone,
)

from app.repositories.delayed_message_queue_repository import (
    ensure_delayed_message_queue_table,
    create_delayed_message,
)

from app.services.delayed_message_worker_service import (
    DelayedMessageWorkerService,
)


def main():
    print(
        "\n=== DELAYED WORKER LOOP TEST ===\n"
    )

    ensure_delayed_message_queue_table()

    create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="loop_test_user_1",
        message_body=(
            "Loop delayed message test"
        ),
        scheduled_for=(
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        ),
    )

    print(
        "✅ delayed test message created"
    )

    worker = DelayedMessageWorkerService()

    print(
        "\n✅ Running one visible worker cycle...\n"
    )

    results = worker.process_due_messages()

    print("Worker results:")
    print(results)

    print(
        "\n✅ DELAYED WORKER LOOP TEST PASSED\n"
    )


if __name__ == "__main__":
    main()