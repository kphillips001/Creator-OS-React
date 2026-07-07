import uuid
from datetime import datetime, timedelta

from app.repositories.fanvue_message_sync_repository import (
    upsert_fanvue_thread,
    save_fanvue_message,
)


def generate_id(prefix: str):
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def run_test():
    print("\n=== 14AC-3: MOCK CONVERSATION BUILDER ===\n")

    fanvue_account_id = 1
    fanvue_user_uuid = generate_id("user")
    thread_id = generate_id("thread")

    print(f"Creating mock thread: {thread_id}")

    upsert_fanvue_thread(
        thread_id=thread_id,
        fanvue_user_uuid=fanvue_user_uuid,
        fanvue_account_id=fanvue_account_id,
        last_message_at=datetime.utcnow(),
    )

    # Simulated conversation timeline
    base_time = datetime.utcnow() - timedelta(minutes=30)

    messages = [
        ("inbound", "hey"),
        ("outbound", "hey you 😏"),
        ("inbound", "what are you doing"),
        ("outbound", "just relaxing… what about you?"),
        ("inbound", "thinking about you tbh"),
        ("outbound", "mmm I like that… what exactly were you thinking about?"),
        ("inbound", "you in something tight"),
        ("outbound", "you’d like that wouldn’t you 😈"),
        ("inbound", "yeah… a lot"),
        ("outbound", "maybe I should show you something…"),
    ]

    print("\nInserting messages...\n")

    for i, (direction, text) in enumerate(messages):
        message_id = generate_id("msg")

        sent_at = base_time + timedelta(minutes=i * 2)

        result = save_fanvue_message(
            fanvue_message_id=message_id,
            thread_id=thread_id,
            fanvue_user_uuid=fanvue_user_uuid,
            fanvue_account_id=fanvue_account_id,
            direction=direction,
            message_text=text,
            message_type="chat",
            sent_at=sent_at,
        )

        print(f"{direction.upper()} | {text}")
        print(result)
        print("-----")

    print("\n=== MOCK CONVERSATION COMPLETE ===\n")
    print(f"Thread ID: {thread_id}")
    print(f"User UUID: {fanvue_user_uuid}")
    print("\nUse this thread_id for next steps.\n")


if __name__ == "__main__":
    run_test()