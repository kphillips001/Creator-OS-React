from app.services.buyer_session_service import BuyerSessionService


def run_test():
    print("\n=== 15H-X STEP 6: CLOSE / CONVERSION LOGIC TEST ===\n")

    service = BuyerSessionService()

    tests = [
        {
            "name": "Strong close intent after PPV",
            "message": "yes send it right now",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "ppv_offer_presented",
                "intent_score": 80,
            },
        },
        {
            "name": "Weak reply after PPV",
            "message": "lol maybe",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 3,
                "buyer_session_last_action": "ppv_offer_presented",
                "intent_score": 20,
            },
        },
        {
            "name": "Strong phrase but no PPV shown yet",
            "message": "send it",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_step": 1,
                "buyer_session_last_action": "bridge_message",
                "intent_score": 80,
            },
        },
    ]

    for test in tests:
        result = service.detect_close_intent(
            message=test["message"],
            memory=test["memory"],
        )

        print(test["name"])
        print("Message:", test["message"])
        print("Result:", result)
        print("-" * 50)

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()