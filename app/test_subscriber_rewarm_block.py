from datetime import datetime, timedelta, timezone

from app.services.subscriber_monetization_service import SubscriberMonetizationService
from app.repositories.memory_repository import update_memory_fields

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def run_test():
    service = SubscriberMonetizationService()

    print("\n===== TEST: SUBSCRIBER REWARM BLOCK =====\n")

    now = datetime.now(timezone.utc)

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "is_subscriber": True,
            "subscriber_profile": "ACTIVE_SUBSCRIBER",
            "relationship_status": "subscriber",
            "active_persona": "ava",
            "last_active_at": now - timedelta(days=8),
            "last_subscriber_send_at": now - timedelta(days=5),
            "subscriber_reentry_count": 0,
            "subscriber_fatigue_flag": False,
            "subscriber_rewarm_required": False,
        },
    )

    result = service.process_subscriber_send(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )

    print("RESULT:")
    print(result)

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()