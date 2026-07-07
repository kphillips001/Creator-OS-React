from app.repositories.fanvue_message_sync_repository import (
    upsert_fanvue_thread,
    save_fanvue_message,
    get_fanvue_messages_for_thread,
)


def run_test():
    print("\n=== 14AC-2: FANVUE MESSAGE REPOSITORY TEST ===\n")

    test_thread_id = "test_thread_14ac_001"
    test_user_uuid = "test_user_uuid_14ac_001"
    test_account_id = 1
    test_message_id = "test_message_14ac_001"

    print("1. Upserting test thread...")

    thread = upsert_fanvue_thread(
        thread_id=test_thread_id,
        fanvue_user_uuid=test_user_uuid,
        fanvue_account_id=test_account_id,
    )

    print("Thread result:")
    print(thread)

    print("\n2. Saving test message...")

    result_1 = save_fanvue_message(
        fanvue_message_id=test_message_id,
        thread_id=test_thread_id,
        fanvue_user_uuid=test_user_uuid,
        fanvue_account_id=test_account_id,
        direction="inbound",
        message_text="hey, what are you up to?",
        message_type="chat",
    )

    print("First save result:")
    print(result_1)

    print("\n3. Attempting duplicate save...")

    result_2 = save_fanvue_message(
        fanvue_message_id=test_message_id,
        thread_id=test_thread_id,
        fanvue_user_uuid=test_user_uuid,
        fanvue_account_id=test_account_id,
        direction="inbound",
        message_text="hey, what are you up to?",
        message_type="chat",
    )

    print("Duplicate save result:")
    print(result_2)

    print("\n4. Fetching messages for thread...")

    messages = get_fanvue_messages_for_thread(
        thread_id=test_thread_id,
        limit=20,
    )

    print(f"Messages found: {len(messages)}")

    for msg in messages:
        print(msg)

    print("\n=== 14AC-2 TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()