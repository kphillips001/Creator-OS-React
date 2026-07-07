from datetime import datetime, timedelta, timezone

from app.repositories.delayed_message_queue_repository import (
    ensure_delayed_message_queue_table,
    create_delayed_message,
    fetch_due_delayed_messages,
    mark_delayed_message_processing,
    mark_delayed_message_completed,
    mark_delayed_message_failed,
    fetch_retryable_delayed_messages,
    reset_delayed_message_for_retry,
    cancel_delayed_message,
    expire_old_delayed_messages,
    get_delayed_message_queue_counts,
)


def main():
    print("\n=== DELAYED MESSAGE QUEUE REPOSITORY TEST ===\n")

    ensure_delayed_message_queue_table()

    print("✅ delayed_message_queue table verified")

    due_id = create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="test_user_due",
        message_body="Testing delayed message queue.",
        scheduled_for=(
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        ),
        payload={
            "source": "test",
            "type": "delayed_followup",
        },
        expires_at=(
            datetime.now(timezone.utc)
            + timedelta(hours=1)
        ),
    )

    print(
        f"✅ created due delayed message: {due_id}"
    )

    due_rows = fetch_due_delayed_messages(
        limit=10,
    )

    print("\nDue rows:")
    print(due_rows)

    assert any(
        str(row["id"]) == str(due_id)
        for row in due_rows
    )

    print(
        "✅ fetch_due_delayed_messages executed"
    )

    mark_delayed_message_processing(
        due_id,
    )

    print("✅ marked processing")

    mark_delayed_message_completed(
        due_id,
        fanvue_message_id=(
            "test_fanvue_message_123"
        ),
    )

    print("✅ marked completed")

    failed_id = create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="test_user_failed",
        message_body="Testing delayed retry.",
        scheduled_for=(
            datetime.now(timezone.utc)
            - timedelta(minutes=1)
        ),
    )

    mark_delayed_message_failed(
        failed_id,
        "test failure reason",
    )

    print("✅ marked failed")

    retryable_rows = (
        fetch_retryable_delayed_messages()
    )

    print("\nRetryable rows:")
    print(retryable_rows)

    assert any(
        str(row["id"]) == str(failed_id)
        for row in retryable_rows
    )

    print(
        "✅ retryable failed message fetched"
    )

    reset_delayed_message_for_retry(
        failed_id,
    )

    print(
        "✅ reset failed message for retry"
    )

    cancel_delayed_message(
        failed_id,
        "test cancellation",
    )

    print(
        "✅ cancelled delayed message"
    )

    expired_id = create_delayed_message(
        fanvue_account_id=1,
        fanvue_user_id="test_user_expired",
        message_body="Testing expiration.",
        scheduled_for=(
            datetime.now(timezone.utc)
            - timedelta(hours=2)
        ),
        expires_at=(
            datetime.now(timezone.utc)
            - timedelta(hours=1)
        ),
    )

    print(
        f"✅ created expired delayed message: "
        f"{expired_id}"
    )

    expired_rows = (
        expire_old_delayed_messages()
    )

    print("\nExpired rows:")
    print(expired_rows)

    assert any(
        str(row["id"]) == str(expired_id)
        for row in expired_rows
    )

    print(
        "✅ expire_old_delayed_messages executed"
    )

    counts = (
        get_delayed_message_queue_counts()
    )

    print("\nQueue counts:")
    print(counts)

    print(
        "\n✅ DELAYED MESSAGE QUEUE "
        "REPOSITORY TEST PASSED\n"
    )


if __name__ == "__main__":
    main()