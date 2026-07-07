from app.repositories.chat_message_repository import get_recent_messages


def test_recent_messages():
    messages = get_recent_messages(thread_id=1, limit=4)

    print("\n----- RECENT CHAT -----")
    for msg in messages:
        speaker = "user" if msg["sender_type"] == "user" else "assistant"
        print(f"[{msg['sent_at']}] {speaker}: {msg['text']}")
    print("-----------------------\n")


if __name__ == "__main__":
    test_recent_messages()