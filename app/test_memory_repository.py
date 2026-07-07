import uuid

from app.repositories.fanvue_account_repository import get_or_create_account
from app.repositories.user_repository import get_or_create_user_with_memory
from app.repositories.memory_repository import (
    increment_message_count,
    update_conversation_mode,
    update_intent_fields,
)


def test_memory_repository():
    account = get_or_create_account(
        username="ava.blackthorne",
        display_name="Ava Blackthorne",
    )

    context = get_or_create_user_with_memory(
        fanvue_account_id=account["id"],
        fanvue_user_uuid=str(uuid.uuid4()),
        username="memory_test_user",
        display_name="Memory Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="test",
    )

    user = context["user"]

    memory = increment_message_count(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
    )
    print("After increment_message_count:")
    print(memory)

    memory = update_conversation_mode(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
        conversation_mode="flirty",
    )
    print("After update_conversation_mode:")
    print(memory)

    memory = update_intent_fields(
        fanvue_account_id=account["id"],
        fanvue_user_id=user["id"],
        intent_score=25.5,
        buyer_tier="medium",
    )
    print("After update_intent_fields:")
    print(memory)


if __name__ == "__main__":
    test_memory_repository()