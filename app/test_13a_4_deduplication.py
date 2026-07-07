from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-4 TEST — DEDUPLICATION")
    print("======================================\n")

    service = FanvueMessageSyncService()

    TEST_USER_UUID = "705b406b-edf0-43ce-93ca-b6e7e9aa3750"

    # First fetch
    result_1 = service.fetch_messages_for_thread(TEST_USER_UUID)

    messages_1 = result_1.get("messages", [])

    print(f"\nFirst fetch messages: {len(messages_1)}")

    dedupe_result_1 = service.dedupe_messages(messages_1)

    seen_set = dedupe_result_1.get("seen_message_uuids")

    print(f"Unique after first run: {len(dedupe_result_1['messages'])}")

    # Second fetch (same messages again)
    result_2 = service.fetch_messages_for_thread(TEST_USER_UUID)

    messages_2 = result_2.get("messages", [])

    print(f"\nSecond fetch messages: {len(messages_2)}")

    dedupe_result_2 = service.dedupe_messages(
        messages_2,
        seen_message_uuids=seen_set,
    )

    print(f"Unique after second run: {len(dedupe_result_2['messages'])}")
    print(f"Skipped duplicates: {dedupe_result_2['skipped']}")

    print("\n======================================")
    print("13A-4 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()