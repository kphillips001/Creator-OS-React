from app.services.subscriber_monetization_service import SubscriberMonetizationService
from app.repositories.memory_repository import (
    get_user_memory_row,
    reset_user_memory,
    update_memory_fields,
)

FANVUE_ACCOUNT_ID = 1
FANVUE_USER_ID = 1


def print_memory(label: str):
    row = get_user_memory_row(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)
    print(f"{label}:")
    print(f"last_subscriber_send_at: {row.get('last_subscriber_send_at')}")
    print(f"subscriber_send_count_24h: {row.get('subscriber_send_count_24h')}")
    print(f"last_subscriber_content_tag: {row.get('last_subscriber_content_tag')}")
    print("-" * 40)


def print_result(label: str, result: dict):
    print(label)
    print(f"Action: {result.get('action')}")
    print(f"Reason: {result.get('reason')}")
    print(f"Content Tag: {result.get('content_tag')}")
    print(f"Base Price: {result.get('base_price')}")
    print(f"Final Price: {result.get('final_price')}")
    print("-" * 40)


def run_test():
    service = SubscriberMonetizationService()

    print("\n===== SUBSCRIBER MONETIZATION SERVICE TEST =====\n")

    # =========================================================
    # TEST 1 — LOW VALUE USER (baseline pricing)
    # =========================================================
    reset_user_memory(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "is_subscriber": True,
            "subscriber_profile": "ACTIVE_SUBSCRIBER",
            "active_persona": "ava",
            "intent_score": 0,
            "exclusive_interest_count": 0,
            "intent_signals": [],
        },
    )

    print("\n--- TEST 1: LOW VALUE USER ---\n")

    print_memory("BEFORE FIRST SEND")

    result_1 = service.process_subscriber_send(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )

    print_result("TEST 1 RESULT:", result_1)

    print_memory("AFTER FIRST SEND")

    # =========================================================
    # TEST 2 — HIGH VALUE / HOT USER (should increase price)
    # =========================================================
    reset_user_memory(FANVUE_ACCOUNT_ID, FANVUE_USER_ID)

    update_memory_fields(
        FANVUE_ACCOUNT_ID,
        FANVUE_USER_ID,
        {
            "is_subscriber": True,
            "subscriber_profile": "ACTIVE_SUBSCRIBER",
            "active_persona": "ava",
            "intent_score": 85,
            "exclusive_interest_count": 3,
            "intent_signals": ["closing_intent"],
        },
    )

    print("\n--- TEST 2: HIGH VALUE USER ---\n")

    print_memory("BEFORE FIRST SEND")

    result_2 = service.process_subscriber_send(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )

    print_result("TEST 2 RESULT:", result_2)

    print_memory("AFTER FIRST SEND")

    # =========================================================
    # TEST 3 — COOLDOWN VALIDATION
    # =========================================================
    print("\n--- TEST 3: COOLDOWN CHECK ---\n")

    result_3 = service.process_subscriber_send(
        fanvue_account_id=FANVUE_ACCOUNT_ID,
        fanvue_user_id=FANVUE_USER_ID,
    )

    print_result("TEST 3 RESULT:", result_3)

    print_memory("AFTER SECOND SEND ATTEMPT")

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()