from app.repositories.chat_message_repository import get_thread_messages_for_user


def test_chat_replay():
    messages = get_thread_messages_for_user(
        fanvue_account_id=2,
        fanvue_user_id=4,
    )

    print("\n----- CHAT REPLAY -----")
    if not messages:
        print("No messages found.")
        return

    for msg in messages:
        speaker = "USER" if msg["sender_type"] == "user" else "BOT"
        print(f"[{msg['sent_at']}] {speaker}: {msg['text']}")
    print("-----------------------\n")


if __name__ == "__main__":
    test_chat_replay()