import uuid

from app.services.payload_builder_service import PayloadBuilderService
from app.repositories.content_usage_repository import log_content_usage


def run_test():
    print("\n=== 15F TEST: PAYLOAD BUILDER DUPLICATE BLOCK ===\n")

    service = PayloadBuilderService()

    fanvue_account_id = 1
    fanvue_user_uuid = "test-user-duplicate-123"

    content_item = {
        "id": 8,
        "fanvue_preview_media_uuid": "test-preview-uuid-123",
        "fanvue_full_media_uuid": "test-full-uuid-456",
    }

    print("STEP 1: Log content as already sent")
    log_content_usage(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_uuid=fanvue_user_uuid,
        content_item_id=content_item["id"],
        send_source="test_duplicate_block",
        caption_used="Already sent caption",
        price=9.99,
        pipeline="test",
        classification="VIP",
    )

    print("\nSTEP 2: Try building payload for same user/content")
    payload = service.build_paid_ppv_payload(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_uuid=fanvue_user_uuid,
        content_item=content_item,
        caption="This should be blocked 😈",
        price=9.99,
        sending_message_uuid=str(uuid.uuid4()),
    )

    print("\n--- PAYLOAD RESULT ---")

    if payload is None:
        print("\n✅ PASS: Duplicate payload was blocked")
    else:
        print("\n❌ FAIL: Duplicate payload was NOT blocked")

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()
