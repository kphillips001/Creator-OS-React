from app.services.response_behavior_service import ResponseBehaviorService


def run_test():
    print("\n=== 15.6 RESPONSE BEHAVIOR SERVICE TEST ===\n")

    service = ResponseBehaviorService()

    test_cases = [
        {
            "name": "Close-ready buyer",
            "classifier_result": {
                "intent_level": "high",
                "buying_intent": True,
                "close_ready": True,
                "user_state": "ready_to_buy",
                "objection_type": "none",
                "recommended_action": "close",
                "buyer_likelihood": "high",
            },
        },
        {
            "name": "Price objection",
            "classifier_result": {
                "intent_level": "medium",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "hesitant",
                "objection_type": "price",
                "recommended_action": "build_tension",
                "buyer_likelihood": "medium",
            },
        },
        {
            "name": "Hesitation / delay",
            "classifier_result": {
                "intent_level": "medium",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "hesitant",
                "objection_type": "hesitation",
                "recommended_action": "chat",
                "buyer_likelihood": "medium",
            },
        },
        {
            "name": "Content/value question",
            "classifier_result": {
                "intent_level": "medium",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "curious",
                "objection_type": "content_specific",
                "recommended_action": "build_tension",
                "buyer_likelihood": "medium",
            },
        },
        {
            "name": "Technical/support issue",
            "classifier_result": {
                "intent_level": "low",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "cold",
                "objection_type": "technical",
                "recommended_action": "support",
                "buyer_likelihood": "low",
            },
        },
        {
            "name": "Curious warm user",
            "classifier_result": {
                "intent_level": "medium",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "curious",
                "objection_type": "none",
                "recommended_action": "build_tension",
                "buyer_likelihood": "medium",
            },
        },
        {
            "name": "Offer-ready user",
            "classifier_result": {
                "intent_level": "high",
                "buying_intent": True,
                "close_ready": False,
                "user_state": "engaged",
                "objection_type": "none",
                "recommended_action": "offer",
                "buyer_likelihood": "high",
            },
        },
        {
            "name": "Low-intent user",
            "classifier_result": {
                "intent_level": "low",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "cold",
                "objection_type": "none",
                "recommended_action": "chat",
                "buyer_likelihood": "low",
            },
        },
        {
            "name": "Low-effort time-waster",
            "classifier_result": {
                "intent_level": "low",
                "buying_intent": False,
                "close_ready": False,
                "user_state": "cold",
                "objection_type": "none",
                "recommended_action": "chat",
                "buyer_likelihood": "low",
            },
            "memory": {
                "effort_mode": "low",
            },
        },
    ]

    for case in test_cases:
        print("--------------------------------------------------")
        print(f"TEST: {case['name']}")
        print("--------------------------------------------------")

        result = service.determine_behavior(
            classifier_result=case["classifier_result"],
            memory=case.get("memory", {}),
        )

        print("response_strategy:", result.get("response_strategy"))
        print("pressure_level:", result.get("pressure_level"))
        print("tone_mode:", result.get("tone_mode"))
        print("should_sell:", result.get("should_sell"))
        print("should_send_offer:", result.get("should_send_offer"))
        print("should_handle_objection:", result.get("should_handle_objection"))
        print("should_downgrade_effort:", result.get("should_downgrade_effort"))
        print("behavior_notes:", result.get("behavior_notes"))
        print()

    print("=== 15.6 RESPONSE BEHAVIOR SERVICE TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()