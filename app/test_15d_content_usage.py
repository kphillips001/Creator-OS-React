from app.repositories.content_usage_repository import (
    has_user_seen_content,
    log_content_usage,
)


def run_test():
    print("\n=== 15D TEST: CONTENT USAGE + DUPLICATE PROTECTION ===\n")

    fanvue_account_id = 1
    fanvue_user_uuid = "test-user-123"
    content_item_id = 8

    print("STEP 1: Check BEFORE logging")
    seen_before = has_user_seen_content(
        fanvue_account_id,
        fanvue_user_uuid,
        content_item_id,
    )
    print(f"Seen before? {seen_before}")

    print("\nSTEP 2: Log usage")
    log_content_usage(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_uuid=fanvue_user_uuid,
        content_item_id=content_item_id,
        send_source="test",
        caption_used="Test caption",
        price=9.99,
        pipeline="mass_ppv",
        classification="VIP",
    )

    print("\nSTEP 3: Check AFTER logging")
    seen_after = has_user_seen_content(
        fanvue_account_id,
        fanvue_user_uuid,
        content_item_id,
    )
    print(f"Seen after? {seen_after}")

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()