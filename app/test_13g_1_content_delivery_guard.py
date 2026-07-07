from app.services.content_delivery_guard_service import ContentDeliveryGuardService


def run_test():
    print("\n====================================")
    print("13G-1 CONTENT DELIVERY GUARD TEST")
    print("====================================\n")

    guard = ContentDeliveryGuardService()

    fanvue_account_id = 1
    fanvue_user_id = 999001

    valid_content = {
        "content_item_id": 999001,
        "destination": "vip",
        "vault_folder_id": "vip-folder-123",
        "upload_status": "uploaded",
        "fanvue_media_uuid": "media-uuid-123",
        "fanvue_preview_media_uuid": "preview-uuid-123",
        "fanvue_full_media_uuid": "full-uuid-123",
        "content_tag": "test_vip_content_13g_1",
    }

    print("\n--- TEST 1: Valid VIP content for chat_ppv ---")
    result = guard.can_deliver_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_record=valid_content,
        requested_delivery="chat_ppv",
    )
    print(result)

    print("\n--- TEST 2: Invalid VIP content for wall_post ---")
    result = guard.can_deliver_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_record=valid_content,
        requested_delivery="wall_post",
    )
    print(result)

    print("\n--- TEST 3: Content not uploaded ---")
    not_uploaded_content = valid_content.copy()
    not_uploaded_content["upload_status"] = "pending"

    result = guard.can_deliver_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_record=not_uploaded_content,
        requested_delivery="chat_ppv",
    )
    print(result)

    print("\n--- TEST 4: Missing media UUID ---")
    missing_uuid_content = valid_content.copy()
    missing_uuid_content["fanvue_media_uuid"] = None
    missing_uuid_content["fanvue_preview_media_uuid"] = None
    missing_uuid_content["fanvue_full_media_uuid"] = None

    result = guard.can_deliver_content(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        content_record=missing_uuid_content,
        requested_delivery="chat_ppv",
    )
    print(result)

    print("\n====================================")
    print("13G-1 TEST COMPLETE")
    print("====================================\n")


if __name__ == "__main__":
    run_test()