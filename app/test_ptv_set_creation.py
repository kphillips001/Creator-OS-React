from datetime import datetime

from app.repositories.content_repository import (
    get_content_ready_for_ptv_set_creation,
    update_content_item,
)
from app.services.fanvue_media_upload_service import FanvueMediaUploadService


def run_test():
    print("\n=== 14M STEP 3D.2B: SAVE PPV SEND RESULT TEST ===\n")

    recipient_uuid = "728a5b4c-2459-4128-b454-6c1f601bb450"
    price = 999

    queue = get_content_ready_for_ptv_set_creation(limit=1)

    if not queue:
        print("No content ready for PTV set creation.")
        return

    item = queue[0]

    print("\n[TEST ITEM]")
    print(item)

    service = FanvueMediaUploadService()

    result = service.send_paid_message(
        item=item,
        recipient_uuid=recipient_uuid,
        price=price,
        text="hey you 😏"
    )

    print("\n[SEND RESULT]")
    print(result)

    if result.get("message_uuid"):
        update_content_item(
            item_id=item["id"],
            fields={
                "last_fanvue_message_uuid": result["message_uuid"],
                "last_fanvue_message_status": result["status"],
                "last_fanvue_message_sent_at": datetime.utcnow(),
                "last_fanvue_message_recipient_uuid": recipient_uuid,
                "last_fanvue_message_price": price,
            },
        )

        print("\n[DB SAVE] PPV send result saved to content_items.")
    else:
        print("\n[DB SAVE SKIPPED] No message_uuid returned.")


if __name__ == "__main__":
    run_test()