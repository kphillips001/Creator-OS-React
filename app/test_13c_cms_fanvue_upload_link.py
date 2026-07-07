from app.database import get_db_connection
from app.services.cms_fanvue_upload_link_service import CMSFanvueUploadLinkService


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
    print("13C TEST — CMS → FANVUE UPLOAD LINK")
    print("======================================\n")

    service = CMSFanvueUploadLinkService()

    fanvue_account_id = 1
    content_item_id = get_test_content_item_id()

    print("[TEST IDS]")
    print(f"fanvue_account_id: {fanvue_account_id}")
    print(f"content_item_id: {content_item_id}")

    if not content_item_id:
        print("❌ No content_items row found. Upload/approve one CMS item first.")
        return

    print("\n[STEP 1] Create upload link")
    link = service.create_upload_link(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
        upload_intent="wall_image",
        delivery_method="post_now",
    )
    print(link)

    print("\n[STEP 2] Mark uploading")
    uploading = service.mark_uploading(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
    )
    print(uploading)

    print("\n[STEP 3] Mark uploaded")
    uploaded = service.mark_uploaded(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
        fanvue_media_uuid="test-media-uuid-13c",
        fanvue_preview_media_uuid="test-preview-uuid-13c",
        fanvue_full_media_uuid="test-full-uuid-13c",
        vault_folder_id="test-folder-13c",
    )
    print(uploaded)

    print("\n[STEP 4] Fetch upload link")
    fetched = service.get_upload_link(
        content_item_id=content_item_id,
        fanvue_account_id=fanvue_account_id,
    )
    print(fetched)

    print("\n======================================")
    print("13C TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()