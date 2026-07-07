from app.main import decision_engine


def run_test():
    print("\n=== 15H-X STEP 6: INTEGRATION TEST ===\n")

    engine = decision_engine

    user_id = "1:999"

    # Inject test memory directly into memory service
    engine.memory.update_user_memory(
        user_id,
        {
            "buyer_session_active": True,
            "buyer_session_step": 3,
            "buyer_session_last_action": "ppv_offer_presented",
            "buyer_session_ppv_count": 1,
            "intent_score": 85,
        },
    )

    message = "yeah send it 😈"

    result = engine.process_message(
        user_id=user_id,
        message=message,
        chat_history=[],
    )

    print("\n--- RESULT ---")
    print(result)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()