from app.services.subscriber_negotiation_service import SubscriberNegotiationService
from app.repositories.memory_repository import (
    get_user_memory_row,
    update_memory_fields,
)

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def print_memory(label: str):
    row = get_user_memory_row(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)
    print(label)
    print(f"price_resistance_count: {row.get('price_resistance_count')}")
    print(f"discount_used_flag: {row.get('discount_used_flag')}")
    print(f"last_offer_price: {row.get('last_offer_price')}")
    print("-" * 40)


def run_test():
    service = SubscriberNegotiationService()

    print("\n===== SUBSCRIBER NEGOTIATION PERSISTENCE TEST =====\n")

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "price_resistance_count": 0,
            "discount_used_flag": False,
            "last_offer_price": 30,
        },
    )

    print_memory("BEFORE NEGOTIATION")

    user_memory = get_user_memory_row(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)

    result = service.process_negotiation_turn(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
        user_memory=user_memory,
        offered_price=30,
        user_message="that's too expensive",
    )

    print("NEGOTIATION RESULT:")
    print(result)
    print("-" * 40)

    print_memory("AFTER NEGOTIATION")

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()