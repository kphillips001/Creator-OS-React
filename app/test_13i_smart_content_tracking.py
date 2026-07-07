from app.repositories.content_repository import (
    get_smart_content_for_user,
    log_content_usage,
    has_user_seen_content,
)


TEST_FANVUE_ACCOUNT_ID = 1
TEST_FANVUE_USER_ID = 999001


def run_test():
    print("\n========================================")
    print("13I.2 SMART CONTENT TRACKING TEST")
    print("========================================\n")

    classification = "TEASE"

    print("[STEP 1] Get smart content before logging usage")
    content = get_smart_content_for_user(
        classification=classification,
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
    )

    print(content)

    if not content:
        print("[STOP] No content found for test.")
        return

    content_id = content["id"]

    print("\n[STEP 2] Confirm user has NOT seen content yet")
    seen_before = has_user_seen_content(
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
        content_item_id=content_id,
    )
    print(f"seen_before={seen_before}")

    print("\n[STEP 3] Log content usage")
    log_content_usage(
        content_item_id=content_id,
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
        usage_type="test_send",
        pipeline="cms_smart_selection_test",
        classification=classification,
        message_text="Test content send",
        price=19.99,
        metadata={"test": True, "source": "test_13i_smart_content_tracking"},
    )
    print("[LOGGED] content usage saved")

    print("\n[STEP 4] Confirm user HAS seen content now")
    seen_after = has_user_seen_content(
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
        content_item_id=content_id,
    )
    print(f"seen_after={seen_after}")

    print("\n[STEP 5] Try smart content selection again")
    next_content = get_smart_content_for_user(
        classification=classification,
        fanvue_account_id=TEST_FANVUE_ACCOUNT_ID,
        fanvue_user_id=TEST_FANVUE_USER_ID,
    )

    print(next_content)

    print("\n========================================")
    print("[DONE] Smart content tracking test complete")
    print("========================================\n")


if __name__ == "__main__":
    run_test()