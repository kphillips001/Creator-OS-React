from app.services.subscriber_monetization_service import SubscriberMonetizationService
from app.repositories.memory_repository import update_memory_fields

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def run_test():
    service = SubscriberMonetizationService()

    print("\n===== TEST: SUBSCRIBER PRICE RESISTANCE FLOW =====\n")

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "is_subscriber": True,
            "subscriber_profile": "ACTIVE_SUBSCRIBER",
            "price_resistance_count": 0,
            "discount_used_flag": False,
            "last_offer_price": 30,
        },
    )

    messages = [
        "that's too expensive",
        "still too much",
        "can you go lower",
        "too expensive",
    ]

    offered_price = 30

    for i, msg in enumerate(messages, start=1):
        print(f"\n--- TURN {i} ---")
        result = service.process_price_resistance(
            fanvue_account_id=FANVUE_ACCOUNT_ID,
            fanvue_user_id=FANVUE_USER_ID,
            offered_price=offered_price,
            user_message=msg,
        )
        print(result)

        if result.get("new_price") is not None:
            offered_price = result["new_price"]

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()