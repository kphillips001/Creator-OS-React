from app.database import get_db_connection
from app.services.content_usage_service import ContentUsageService


def get_value(row, key, index):
    if row is None:
        return None

    if isinstance(row, dict):
        return row.get(key)

    return row[index]


def get_test_ids():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, fanvue_account_id
                FROM fanvue_users
                WHERE id IS NOT NULL
                LIMIT 1;
                """
            )
            user_row = cur.fetchone()

            cur.execute(
                """
                SELECT id
                FROM content_items
                WHERE id IS NOT NULL
                LIMIT 1;
                """
            )
            content_row = cur.fetchone()

    fanvue_user_id = get_value(user_row, "id", 0)
    fanvue_account_id = get_value(user_row, "fanvue_account_id", 1)
    content_item_id = get_value(content_row, "id", 0)

    return fanvue_account_id, fanvue_user_id, content_item_id


def run_test():
    print("\n======================================")
    print("13B TEST — DB CONTENT USAGE SERVICE")
    print("======================================\n")

    service = ContentUsageService()

    fanvue_account_id, fanvue_user_id, content_item_id = get_test_ids()

    print("[TEST IDS]")
    print(f"fanvue_account_id: {fanvue_account_id}")
    print(f"fanvue_user_id: {fanvue_user_id}")
    print(f"content_item_id: {content_item_id}")

    if not fanvue_account_id or not fanvue_user_id or not content_item_id:
        print("\n❌ Missing test data.")
        print("Need at least 1 row in fanvue_users and 1 row in content_items.")
        return

    content_tag = "test_tease_13b"

    print("\n[STEP 1] Check content before logging")
    already_seen_before = service.has_seen_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_item_id=content_item_id,
    )

    print("Seen before:", already_seen_before)

    print("\n[STEP 2] Log content usage")
    logged = service.mark_content_seen(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_item_id=content_item_id,
        send_source="13B_TEST",
        fanvue_message_id="test-message-13b",
        caption_used="Test caption for 13B DB tracking",
        price=0.0,
        usage_type="send",
        pipeline="test_13b_db_content_usage",
        classification=content_tag,
    )

    print("Logged row:")
    print(logged)

    print("\n[STEP 3] Check content after logging")
    already_seen_after = service.has_seen_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_item_id=content_item_id,
    )

    print("Seen after:", already_seen_after)

    print("\n[STEP 4] Check content tag")
    tag_seen = service.has_seen_content_tag(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_tag=content_tag,
    )

    print("Tag seen:", tag_seen)

    print("\n======================================")
    print("13B DB CONTENT USAGE TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()