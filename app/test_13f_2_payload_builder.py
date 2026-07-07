from app.services.content_media_delivery_service import ContentMediaDeliveryService
from app.services.content_payload_builder_service import ContentPayloadBuilderService


def run_test():
    print("\n======================================")
    print("13F-2 TEST — PAYLOAD BUILDER")
    print("======================================\n")

    media_service = ContentMediaDeliveryService()
    payload_builder = ContentPayloadBuilderService()

    fanvue_account_id = 1

    print("[STEP 1] Fetch safe wall media")
    wall_result = media_service.get_media_for_delivery(
        fanvue_account_id=fanvue_account_id,
        destination="wall",
        requested_delivery="wall_post",
        limit=1,
    )

    wall_media = wall_result.get("media", [])

    if not wall_media:
        print("❌ No wall media found. Upload one wall item first.")
        return

    content_record = wall_media[0]

    print("\n[STEP 2] Build valid wall post payload")
    wall_payload = payload_builder.build_wall_post_payload(
        content_record=content_record,
        caption="Test wall caption from 13F-2",
    )
    print(wall_payload)

    print("\n[STEP 3] Try invalid PPV payload from wall media")
    invalid_ppv_payload = payload_builder.build_chat_ppv_payload(
        content_record=content_record,
        caption="This should be blocked",
        price=9.99,
    )
    print(invalid_ppv_payload)

    print("\n======================================")
    print("13F-2 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()