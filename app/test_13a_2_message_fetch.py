from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-2 TEST — MESSAGE FETCH")
    print("======================================\n")

    service = FanvueMessageSyncService()

    # ⚠️ Use one UUID from your thread fetch output
    TEST_USER_UUID = "705b406b-edf0-43ce-93ca-b6e7e9aa3750"

    result = service.fetch_messages_for_thread(
        fanvue_user_uuid=TEST_USER_UUID,
        page=1,
        size=10,
    )

    print("\n------------- RESULT -------------")
    print(f"success: {result.get('success')}")
    print(f"count: {result.get('count')}")
    print(f"pagination: {result.get('pagination')}")

    messages = result.get("messages", [])

    print("\n------------- MESSAGES -------------")

    for index, msg in enumerate(messages, start=1):
        print(f"\nMESSAGE #{index}")
        print(f"uuid: {msg.get('message_uuid')}")
        print(f"text: {msg.get('text')}")
        print(f"sender: {msg.get('sender_uuid')}")
        print(f"sent_at: {msg.get('sent_at')}")

    print("\n======================================")
    print("13A-2 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()