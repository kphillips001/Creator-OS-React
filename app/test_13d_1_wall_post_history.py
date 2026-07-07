from app.database import get_db_connection
from app.repositories.wall_post_repository import (
    has_wall_content_been_used,
    mark_wall_content_posted,
    mark_wall_content_scheduled,
)


def get_value(row, key, index):
    if row is None:
        return None

    if isinstance(row, dict):
        return row.get(key)

    return row[index]


def get_test_content_item_id():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id
                FROM content_items
                WHERE id IS NOT NULL
                LIMIT 1;
                """
            )
            row = cur.fetchone()

    return get_value(row, "id", 0)


def run_test():
    print("\n======================================")
    print("13D-1 TEST — WALL POST HISTORY")
    print("======================================\n")

    fanvue_account_id = 1
    content_item_id = get_test_content_item_id()

    print("[TEST IDS]")
    print(f"fanvue_account_id: {fanvue_account_id}")
    print(f"content_item_id: {content_item_id}")

    if not content_item_id:
        print("❌ No content_items row found.")
        return

    print("\n[STEP 1] Check before scheduled/post")
    before = has_wall_content_been_used(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
    )
    print("Already used before:", before)

    print("\n[STEP 2] Mark scheduled")
    scheduled = mark_wall_content_scheduled(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
    )
    print(scheduled)

    print("\n[STEP 3] Check after scheduled")
    after_scheduled = has_wall_content_been_used(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
    )
    print("Already used after scheduled:", after_scheduled)

    print("\n[STEP 4] Mark posted now")
    posted = mark_wall_content_posted(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
        delivery_method="post_now",
        fanvue_post_uuid="test-wall-post-13d",
    )
    print(posted)

    print("\n[STEP 5] Check after posted")
    after_posted = has_wall_content_been_used(
        fanvue_account_id=fanvue_account_id,
        content_item_id=content_item_id,
    )
    print("Already used after posted:", after_posted)

    print("\n======================================")
    print("13D-1 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()