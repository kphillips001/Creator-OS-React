import uuid

from app.repositories.user_repository import get_or_create_user_with_memory


def test_user_repository():
    fanvue_user_uuid = str(uuid.uuid4())

    result = get_or_create_user_with_memory(
        fanvue_account_id=1,
        fanvue_user_uuid=fanvue_user_uuid,
        username="test_user_01",
        display_name="Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="test",
    )

    print("User created/loaded successfully!")
    print(result["user"])
    print(result["memory"])


if __name__ == "__main__":
    test_user_repository()