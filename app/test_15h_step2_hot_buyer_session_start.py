from datetime import datetime

from app.repositories.memory_repository import (
    get_user_memory_row,
    reset_user_memory,
)
from app.services.hot_buyer_detection_service import HotBuyerDetectionService


def run_test():
    print("\n=== 15H STEP 2: HOT BUYER SESSION START TEST ===\n")

    fanvue_account_id = 2
    fanvue_user_id = 3

    reset_user_memory(fanvue_account_id, fanvue_user_id)

    service = HotBuyerDetectionService()

    memory = {
        "last_offer_timestamp": datetime.utcnow(),
        "intent_score": 80,
        "messages_since_last_offer": 1,
        "buyer_session_active": False,
    }

    result = service.is_hot_buyer(
        fanvue_account_id,
        fanvue_user_id,
        memory,
    )

    print("Detection Result:", result)

    updated = get_user_memory_row(fanvue_account_id, fanvue_user_id)

    print("\nSession State After Detection:")
    print("Active:", updated.get("buyer_session_active"))
    print("Step:", updated.get("buyer_session_step"))
    print("Last Action:", updated.get("buyer_session_last_action"))


if __name__ == "__main__":
    run_test()