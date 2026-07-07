from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-3 TEST — INCREMENTAL SYNC")
    print("======================================\n")

    service = FanvueMessageSyncService()

    TEST_USER_UUID = "705b406b-edf0-43ce-93ca-b6e7e9aa3750"

    # Simulate "we already saw this message"
    LAST_SEEN_TIMESTAMP = "2025-09-10T00:00:00.000Z"

    result = service.fetch_new_messages_for_thread(
        fanvue_user_uuid=TEST_USER_UUID,
        last_seen_timestamp=LAST_SEEN_TIMESTAMP,
    )

    print("\n------------- RESULT -------------")
    print(f"success: {result.get('success')}")
    print(f"count: {result.get('count')}")

    messages = result.get("messages", [])

    print("\n------------- NEW MESSAGES -------------")

    for index, msg in enumerate(messages, start=1):
        print(f"\nMESSAGE #{index}")
        print(f"uuid: {msg.get('message_uuid')}")
        print(f"text: {msg.get('text')}")
        print(f"sent_at: {msg.get('sent_at')}")

    print("\n======================================")
    print("13A-3 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()