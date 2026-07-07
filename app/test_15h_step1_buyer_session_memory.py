from app.repositories.memory_repository import (
    create_user_memory_row,
    get_user_memory_row,
    update_memory_fields,
)

def run_test():
    print("\n=== 15H STEP 1: BUYER SESSION MEMORY TEST ===\n")

    fanvue_account_id = 2
    fanvue_user_id = 3

    # Create fresh row
    # create_user_memory_row(fanvue_account_id, fanvue_user_id)

    # Update session fields
    update_memory_fields(fanvue_account_id, fanvue_user_id, {
        "buyer_session_active": True,
        "buyer_session_step": 2,
        "buyer_session_ppv_count": 3,
        "buyer_session_last_action": "ppv",
    })

    memory = get_user_memory_row(fanvue_account_id, fanvue_user_id)

    print("Active:", memory.get("buyer_session_active"))
    print("Step:", memory.get("buyer_session_step"))
    print("PPV Count:", memory.get("buyer_session_ppv_count"))
    print("Last Action:", memory.get("buyer_session_last_action"))

if __name__ == "__main__":
    run_test()