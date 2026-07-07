from datetime import datetime, timedelta

from app.repositories.delayed_message_queue_repository import (
    ensure_delayed_message_queue_table,
    create_delayed_message,
)

from app.services.delayed_message_worker_service import (
    DelayedMessageWorkerService,
)


def main():
    print(
        "\n=== DELAYED MESSAGE WORKER TEST ===\n"
    )

    ensure_delayed_message_queue_table()

    create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="worker_test_user_1",
        message_body=(
            "Delayed follow-up test message 1"
        ),
        scheduled_for=(
            datetime.utcnow()
            - timedelta(minutes=1)
        ),
    )

    create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="worker_test_user_2",
        message_body=(
            "Delayed follow-up test message 2"
        ),
        scheduled_for=(
            datetime.utcnow()
            - timedelta(minutes=1)
        ),
    )

    print(
        "✅ test delayed messages created"
    )

    worker = (
        DelayedMessageWorkerService()
    )

    results = (
        worker.process_due_messages()
    )

    print("\nWorker Results:\n")

    for result in results:
        print(result)

    print(
        "\n✅ DELAYED MESSAGE WORKER TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()