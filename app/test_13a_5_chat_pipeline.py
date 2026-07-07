from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-5 TEST — CHAT PIPELINE")
    print("======================================\n")

    service = FanvueMessageSyncService()

    TEST_USER_UUID = "705b406b-edf0-43ce-93ca-b6e7e9aa3750"

    # ⚠️ IMPORTANT: Set this to YOUR OWN Fanvue UUID
    MY_USER_UUID = "f45fdd96-8831-4ef5-8f79-0278c29dc747"

    # Step 1: Fetch messages
    result = service.fetch_messages_for_thread(TEST_USER_UUID)

    messages = result.get("messages", [])

    # Step 2: Deduplicate
    dedupe_result = service.dedupe_messages(messages)

    unique_messages = dedupe_result.get("messages", [])

    # Step 3: Process inbound
    inbound = service.process_inbound_messages(
        unique_messages,
        my_user_uuid=MY_USER_UUID,
    )

    print("\n======================================")
    print(f"FINAL INBOUND COUNT: {len(inbound)}")
    print("======================================\n")


if __name__ == "__main__":
    run_test()