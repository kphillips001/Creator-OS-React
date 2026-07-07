from app.services.subscriber_monetization_service import SubscriberMonetizationService
from app.repositories.memory_repository import reset_user_memory, update_memory_fields

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def run_test():
    service = SubscriberMonetizationService()

    print("\n===== TEST: SUBSCRIBER SERVICE HARD GUARD =====\n")

    # Reset and force this user to be NON-subscriber
    reset_user_memory(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "is_subscriber": False,
            "relationship_status": "follower",
            "active_persona": "ava",
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