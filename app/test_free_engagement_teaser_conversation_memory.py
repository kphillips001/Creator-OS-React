from unittest.mock import patch

from app.repositories.chat_message_repository import get_recent_messages_for_gpt


def test_future_gpt_history_remembers_teaser_without_internal_path():
    rows = [{
        "sender_type": "bot",
        "text": "Thought you might like this 😊",
        "has_media": True,
        "raw_payload": {
            "delivery_kind": "FREE_ENGAGEMENT_TEASER",
            "engagement_strategy": "RE_ENGAGE",
            "asset_id": 42,
            "operation_id": "internal-operation",
        },
    }]
    with patch(
        "app.repositories.chat_message_repository.get_recent_messages",
        return_value=rows,
    ):
        history = get_recent_messages_for_gpt(2, 4)
    assert history == [{
        "role": "assistant",
        "content": "[Ava sent a free teaser image for re engage. Caption: Thought you might like this 😊]",
    }]
    assert "asset" not in history[0]["content"].lower()
    assert "operation" not in history[0]["content"].lower()
    assert "C:/" not in history[0]["content"]
