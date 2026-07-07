from app.services.buyer_session_service import BuyerSessionService


def run_test():
    print("\n=== 19D: BUYER SESSION TEST ===\n")

    service = BuyerSessionService()

    tests = [
        {
            "name": "Strong close",
            "message": "bettt send it now 😈",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "ppv_offer_presented",
                "buyer_session_ppv_count": 1,
            },
        },
        {
            "name": "Converted",
            "message": "okay I unlocked it",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "ppv",
                "buyer_session_ppv_count": 1,
            },
        },
        {
            "name": "Rejection",
            "message": "eh maybe later honestly",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "wait",
                "buyer_session_ppv_count": 1,
            },
        },
    ]

    for test in tests:
        print(f"\n--- {test['name']} ---")
        print("Message:", test["message"])

        close_result = service.detect_close_intent(
            test["message"],
            test["memory"],
        )

        exit_result = service.detect_exit_intent(
            test["message"],
            test["memory"],
        )

        print("CLOSE RESULT:", close_result)
        print("EXIT RESULT:", exit_result)
        print("-" * 50)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()