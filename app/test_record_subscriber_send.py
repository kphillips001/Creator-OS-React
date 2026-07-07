from app.repositories.memory_repository import (
    create_user_memory_row,
    get_user_memory_row,
    record_subscriber_send,
)

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def run_test():
    print("\n===== RECORD SUBSCRIBER SEND TEST =====\n")

    row = create_user_memory_row(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)
    print("Initial row created/fetched.")

    before = get_user_memory_row(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)
    print("\nBEFORE:")
    print(f"last_subscriber_send_at: {before.get('last_subscriber_send_at')}")
    print(f"subscriber_send_count_24h: {before.get('subscriber_send_count_24h')}")
    print(f"last_subscriber_content_tag: {before.get('last_subscriber_content_tag')}")

    updated = record_subscriber_send(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        "vip_tease_001",
    )

    print("\nAFTER:")
    print(f"last_subscriber_send_at: {updated.get('last_subscriber_send_at')}")
    print(f"subscriber_send_count_24h: {updated.get('subscriber_send_count_24h')}")
    print(f"last_subscriber_content_tag: {updated.get('last_subscriber_content_tag')}")

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()