from app.repositories import chat_message_repository


def test_recent_messages_for_gpt_is_account_scoped(monkeypatch):
    captured = {}

    def recent(**kwargs):
        captured.update(kwargs)
        return [{"sender_type": "user", "text": "hello", "raw_payload": {}}]

    monkeypatch.setattr(chat_message_repository, "get_recent_messages", recent)
    messages = chat_message_repository.get_recent_messages_for_gpt(
        fanvue_account_id=7, thread_id=1, limit=4,
    )

    assert captured == {
        "fanvue_account_id": 7,
        "thread_id": 1,
        "limit": 4,
        "exclude_message_uuid": None,
    }
    assert messages == [{"role": "user", "content": "hello"}]


if __name__ == "__main__":
    test_recent_messages_for_gpt()
