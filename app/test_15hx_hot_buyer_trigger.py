from app.main import decision_engine, memory_service
from app.repositories.memory_repository import get_user_memory_row


def run_test():
    print("\n=== 15H-X TEST: HOT BUYER → SESSION TRIGGER ===\n")

    user_id = "1:999"
    fanvue_account_id = 1
    fanvue_user_id = 999

    # Clear in-memory test state
    memory_service.clear_user_memory(user_id)

    test_messages = [
        "hey",
        "that looks good",
        "damn I want that",
        "how much is it?",
    ]

    for msg in test_messages:
        print(f"\nUSER: {msg}")

        result = decision_engine.process_message(
            user_id=user_id,
            message=msg,
            chat_history=[],
        )

        print(f"BOT: {result['response']}")

        db_memory = get_user_memory_row(
            fanvue_account_id,
            fanvue_user_id,
        )

        print("\n--- BUYER SESSION MEMORY (DB) ---")

        if not db_memory:
            print("No DB memory row found.")
        else:
            print(f"buyer_session_active: {db_memory.get('buyer_session_active')}")
            print(f"buyer_session_step: {db_memory.get('buyer_session_step')}")
            print(f"buyer_session_last_action: {db_memory.get('buyer_session_last_action')}")
            print(f"buyer_session_ppv_count: {db_memory.get('buyer_session_ppv_count')}")

        print("---------------------------------")


if __name__ == "__main__":
    run_test()