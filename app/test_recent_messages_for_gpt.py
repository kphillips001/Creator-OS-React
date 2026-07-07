from app.repositories.chat_message_repository import get_recent_messages_for_gpt


def test_recent_messages_for_gpt():
    messages = get_recent_messages_for_gpt(thread_id=1, limit=4)

    print("\n----- GPT READY MESSAGES -----")
    for msg in messages:
        print(msg)
    print("------------------------------\n")


if __name__ == "__main__":
    test_recent_messages_for_gpt()