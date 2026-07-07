from app.services.buyer_session_service import BuyerSessionService


def run_test():
    print("\n=== 15H-X STEP 7: EXIT LOGIC TEST ===\n")

    service = BuyerSessionService()

    tests = [
        {
            "name": "Purchase confirmation exits as converted",
            "message": "I just unlocked it",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "close_mode",
                "buyer_session_ppv_count": 1,
                "intent_score": 80,
            },
        },
        {
            "name": "Rejection exits to cooldown",
            "message": "maybe later",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "close_mode",
                "buyer_session_ppv_count": 1,
                "intent_score": 25,
            },
        },
        {
            "name": "No active session",
            "message": "maybe later",
            "memory": {
                "buyer_session_active": False,
                "buyer_session_step": 0,
                "buyer_session_last_action": None,
                "buyer_session_ppv_count": 0,
                "intent_score": 20,
            },
        },
    ]

    for test in tests:
        result = service.detect_exit_intent(
            message=test["message"],
            memory=test["memory"],
        )

        print(test["name"])
        print("Result:", result)
        print("-" * 50)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()