from app.services.buyer_session_service import BuyerSessionService


def run_test():
    print("\n=== 15H STEP 3A: BUYER SESSION SERVICE TEST ===\n")

    service = BuyerSessionService()

    tests = [
        {
            "name": "No active session",
            "memory": {
                "buyer_session_active": False,
            },
        },
        {
            "name": "Session just started",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_ppv_count": 0,
                "buyer_session_last_action": "session_start",
            },
        },
        {
            "name": "Bridge already sent",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_ppv_count": 0,
                "buyer_session_last_action": "bridge_message",
            },
        },
        {
            "name": "PPV already sent",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_ppv_count": 1,
                "buyer_session_last_action": "ppv",
            },
        },
        {
            "name": "Max PPVs reached",
            "memory": {
                "buyer_session_active": True,
                "buyer_session_ppv_count": 3,
                "buyer_session_last_action": "ppv",
            },
        },
    ]

    for test in tests:
        result = service.decide_next_action(test["memory"])
        print(f"{test['name']}: {result}")

    print("\n=== TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()