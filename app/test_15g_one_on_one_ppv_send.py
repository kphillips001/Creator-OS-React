from datetime import datetime

from app.services.one_on_one_ppv_send_service import OneOnOnePPVSendService
from app.repositories.memory_repository import (
    update_memory_fields,
    get_user_memory_row,
)


def run_test():
    print("\n=== 15G TEST: ONE-ON-ONE PPV SEND ORCHESTRATION ===\n")

    service = OneOnOnePPVSendService()

    content_item = {
        "id": 8,
        "classification": "VIP",
        "tier": "vip_offer",
        "suggested_tags": ["mirror", "tight outfit", "curves", "tease"],
        "safe_summary": "Creator is posing in a tight outfit with a teasing mirror-style vibe.",
        "fanvue_preview_media_uuid": "test-preview-uuid-123",
        "fanvue_full_media_uuid": "test-full-uuid-456",
    }

    fanvue_account_id = 1
    fanvue_user_id = 1001

    # --------------------------------------------------
    # SET HOT BUYER TEST CONDITIONS
    # --------------------------------------------------

    update_memory_fields(fanvue_account_id, fanvue_user_id, {
        "last_offer_timestamp": datetime.utcnow(),
        "intent_score": 80,
        "messages_since_last_offer": 1,
    })

    result = service.send_ppv_to_user(
        fanvue_account_id=fanvue_account_id,
        fanvue_user_uuid=fanvue_user_id,
        thread_id="thread_dedf82b76f",
        content_item=content_item,
        price=9.99,
        dry_run=True,
    )

    print("\n--- RESULT ---")
    print(result)

    memory_after = get_user_memory_row(fanvue_account_id, fanvue_user_id)

    print("\n--- BUYER SESSION AFTER PPV FLOW ---")
    print("Active:", memory_after.get("buyer_session_active"))
    print("Step:", memory_after.get("buyer_session_step"))
    print("Last Action:", memory_after.get("buyer_session_last_action"))

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()