from app.database import get_db_connection
from app.services.cms_fanvue_media_sync_service import CMSFanvueMediaSyncService


def get_value(row, key, index):
    if row is None:
        return None

    if isinstance(row, dict):
        return row.get(key)

    return row[index]


def get_test_content_item():
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM content_items
                WHERE file_path IS NOT NULL
                ORDER BY id DESC
                LIMIT 1;
                """
            )
            row = cur.fetchone()

    return dict(row) if row else None


def run_test():
    print("\n======================================")
    print("13E TEST — MEDIA ID STORAGE")
    print("======================================\n")

    service = CMSFanvueMediaSyncService()

    fanvue_account_id = 1
    content_item = get_test_content_item()

    if not content_item:
        print("❌ No content_items row with file_path found.")
        return

    print("[TEST CONTENT ITEM]")
    print(f"id: {content_item.get('id')}")
    print(f"file_path: {content_item.get('file_path')}")

    result = service.upload_and_store_media_ids(
        content_item=content_item,
        fanvue_account_id=fanvue_account_id,
        upload_intent="wall_image",
        delivery_method="post_now",
    )

    print("\n------------- RESULT -------------")
    print(result)

    print("\n======================================")
    print("13E TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()