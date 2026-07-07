from app.services.fanvue_message_sync_service import FanvueMessageSyncService


def run_test():
    print("\n======================================")
    print("13A-1 TEST — FANVUE THREAD FETCH")
    print("======================================\n")

    service = FanvueMessageSyncService()

    result = service.fetch_chat_threads(
        page=1,
        size=10,
        sort_by="most_recent_messages",
    )

    print("\n------------- RESULT -------------")
    print(f"success: {result.get('success')}")
    print(f"count: {result.get('count')}")
    print(f"pagination: {result.get('pagination')}")

    threads = result.get("threads", [])

    print("\n------------- THREADS -------------")

    for index, thread in enumerate(threads, start=1):
        print(f"\nTHREAD #{index}")
        print(f"user_uuid: {thread.get('fanvue_user_uuid')}")
        print(f"handle: {thread.get('handle')}")
        print(f"display_name: {thread.get('display_name')}")
        print(f"last_message_at: {thread.get('last_message_at')}")
        print(f"unread_messages_count: {thread.get('unread_messages_count')}")
        print(f"last_message_uuid: {thread.get('last_message_uuid')}")
        print(f"last_message_text: {thread.get('last_message_text')}")

    print("\n======================================")
    print("13A-1 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()