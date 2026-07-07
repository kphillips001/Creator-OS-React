from app.main import decision_engine


def run_test():
    print("\n=== 15H-X STEP 7: INTEGRATION TEST ===\n")

    engine = decision_engine

    user_id = "1:999"

    # Inject test memory directly into memory service
    engine.memory.update_user_memory(
        user_id,
        {
            "buyer_session_active": True,
            "buyer_session_step": 3,
            "buyer_session_last_action": "close_mode",
            "buyer_session_ppv_count": 1,
            "intent_score": 80,
        },
    )

    message = "I just unlocked it"

    result = engine.process_message(
        user_id=user_id,
        message=message,
        chat_history=[],
    )

    print("\n--- RESULT ---")
    print(result)

    refreshed = engine.memory.get_user_memory(user_id)

    print("\n--- MEMORY AFTER ---")
    print("buyer_session_active:", refreshed.get("buyer_session_active"))
    print("buyer_session_step:", refreshed.get("buyer_session_step"))
    print("buyer_session_last_action:", refreshed.get("buyer_session_last_action"))
    print("buyer_session_cooldown_until:", refreshed.get("buyer_session_cooldown_until"))
    print("conversation_mode:", refreshed.get("conversation_mode"))
    print("current_route:", refreshed.get("current_route"))

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()