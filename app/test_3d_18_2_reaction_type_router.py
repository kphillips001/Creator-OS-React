from app.services.automated_reaction_type_router_service import (
    AutomatedReactionTypeRouterService,
)


def main():
    service = AutomatedReactionTypeRouterService()

    test_cases = [
        {
            "name": "purchase maps to purchase_thank_you",
            "event": {
                "event_type": "purchase_received",
            },
            "decision": {},
            "expected": "purchase_thank_you",
        },
        {
            "name": "unlock maps to unlock_followup",
            "event": {
                "event_type": "unlock_confirmation",
            },
            "decision": {},
            "expected": "unlock_followup",
        },
        {
            "name": "tip maps to tip_thank_you",
            "event": {
                "event_type": "tip_received",
            },
            "decision": {},
            "expected": "tip_thank_you",
        },
        {
            "name": "subscription maps to subscription_welcome",
            "event": {
                "event_type": "subscription_created",
            },
            "decision": {},
            "expected": "subscription_welcome",
        },
        {
            "name": "premium decision maps to premium_followup",
            "event": {
                "event_type": "purchase_received",
            },
            "decision": {
                "decision": "premium_followup",
            },
            "expected": "premium_followup",
        },
        {
            "name": "whale decision maps to whale_retention_message",
            "event": {
                "event_type": "purchase_received",
            },
            "decision": {
                "decision": "whale_retention",
            },
            "expected": "whale_retention_message",
        },
        {
            "name": "unsupported event blocks safely",
            "event": {
                "event_type": "unknown_event",
            },
            "decision": {},
            "expected": None,
        },
    ]

    print("\n=== 3D.18.2 REACTION TYPE ROUTER TEST ===\n")

    for test in test_cases:
        result = service.resolve_reaction_type(
            monetization_event=test["event"],
            post_purchase_decision=test["decision"],
        )

        print(test["name"])
        print(result)

        if test["expected"]:
            assert result["success"] is True
            assert result["blocked"] is False
            assert result["reaction_type"] == test["expected"]
        else:
            assert result["success"] is False
            assert result["blocked"] is True

        print("PASS\n")

    print("✅ 3D.18.2 Reaction Type Router passed")


if __name__ == "__main__":
    main()