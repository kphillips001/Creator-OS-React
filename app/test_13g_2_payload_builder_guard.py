from app.services.content_payload_builder_service import ContentPayloadBuilderService


def run_test():
    print("\n====================================")
    print("13G-2 PAYLOAD BUILDER GUARD TEST")
    print("====================================\n")

    builder = ContentPayloadBuilderService()

    fanvue_account_id = 1
    fanvue_user_id = 999001

    valid_ppv_content = {
        "content_item_id": 999002,
        "destination": "vip",
        "vault_folder_id": "vip-folder-123",
        "upload_status": "uploaded",
        "fanvue_media_uuid": "media-uuid-ppv-123",
        "fanvue_preview_media_uuid": "preview-uuid-ppv-123",
        "fanvue_full_media_uuid": "full-uuid-ppv-123",
        "content_tag": "test_vip_content_13g_2",
    }

    print("\n--- TEST 1: Build PPV payload with usage guard ON ---")
    result = builder.build_chat_ppv_payload(
        content_record=valid_ppv_content,
        caption="Test PPV caption",
        price=9.99,
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        enforce_usage_guard=True,
    )
    print(result)

    print("\n--- TEST 2: Build teaser payload with usage guard ON ---")
    teaser_content = valid_ppv_content.copy()
    teaser_content["content_item_id"] = 999003
    teaser_content["destination"] = "teaser"
    teaser_content["content_tag"] = "test_teaser_content_13g_2"

    result = builder.build_chat_teaser_payload(
        content_record=teaser_content,
        caption="Test teaser caption",
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        enforce_usage_guard=True,
    )
    print(result)

    print("\n--- TEST 3: Block invalid PPV destination ---")
    invalid_ppv_content = valid_ppv_content.copy()
    invalid_ppv_content["destination"] = "wall"

    result = builder.build_chat_ppv_payload(
        content_record=invalid_ppv_content,
        caption="Invalid PPV caption",
        price=9.99,
        fanvue_account_id=fanvue_account_id,
        fanvue_user_id=fanvue_user_id,
        enforce_usage_guard=True,
    )
    print(result)

    print("\n====================================")
    print("13G-2 TEST COMPLETE")
    print("====================================\n")


if __name__ == "__main__":
    run_test()