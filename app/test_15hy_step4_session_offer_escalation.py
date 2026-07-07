from app.services.buyer_session_service import BuyerSessionService


def run_test():
    print("\n=== 15H-Y STEP 4: SESSION OFFER ESCALATION TEST ===\n")

    service = BuyerSessionService()

    # ------------------------------------------
    # TEST CASES
    # ------------------------------------------

    test_cases = [
        {
            "name": "STEP 1 → TEASE",
            "memory": {
                "buyer_session_step": 1,
                "intent_score": 20,
                "user_value_tier": "low",
                "buyer_tier": "NON_BUYER",
                "is_whale": False,
            },
        },
        {
            "name": "STEP 2 → VIP",
            "memory": {
                "buyer_session_step": 2,
                "intent_score": 50,
                "user_value_tier": "medium",
                "buyer_tier": "ACTIVE_BUYER",
                "is_whale": False,
            },
        },
        {
            "name": "STEP 3 → PREMIUM",
            "memory": {
                "buyer_session_step": 3,
                "intent_score": 80,
                "user_value_tier": "medium",
                "buyer_tier": "ACTIVE_BUYER",
                "is_whale": False,
            },
        },
        {
            "name": "HIGH VALUE OVERRIDE → PREMIUM",
            "memory": {
                "buyer_session_step": 1,
                "intent_score": 20,
                "user_value_tier": "high",
                "buyer_tier": "HIGH_VALUE",
                "is_whale": False,
            },
        },
        {
            "name": "WHALE OVERRIDE → PREMIUM",
            "memory": {
                "buyer_session_step": 1,
                "intent_score": 10,
                "user_value_tier": "low",
                "buyer_tier": "LOW_SPENDER",
                "is_whale": True,
            },
        },
    ]

    # ------------------------------------------
    # RUN TESTS
    # ------------------------------------------

    for test in test_cases:
        print(f"\n--- {test['name']} ---")

        result = service.get_session_offer_tier(test["memory"])

        print("Result:")
        print(result)


if __name__ == "__main__":
    run_test()