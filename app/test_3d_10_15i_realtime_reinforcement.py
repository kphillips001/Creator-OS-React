from app.services.realtime_intimacy_reinforcement_service import (
    RealtimeIntimacyReinforcementService,
)


def run_case(service, title, event_type):
    print("\n================================")
    print(title)
    print("================================")

    memory = {
        "intimacy_context": {
            "intimacy_tier": "cold",
            "spender_confidence": "low",
            "premium_sexting_allowed": False,
            "runtime_mode": "safe_chat",
        }
    }

    result = service.merge_into_intimacy_context(
        existing_memory=memory,
        event_type=event_type,
        payload={},
    )

    context = result["intimacy_context"]

    for key, value in context.items():
        print(f"{key}: {value}")

    return context


def run_test():
    print("\n======================================")
    print("3D.10.15I — REALTIME REINFORCEMENT TEST")
    print("======================================\n")

    service = RealtimeIntimacyReinforcementService()

    purchase_context = run_case(
        service,
        "CASE 1 — PURCHASE CREATED",
        "purchase_created",
    )

    tip_context = run_case(
        service,
        "CASE 2 — TIP CREATED",
        "tip_created",
    )

    subscription_context = run_case(
        service,
        "CASE 3 — SUBSCRIPTION CREATED",
        "subscription_created",
    )

    assert purchase_context["intimacy_tier"] == "premium"
    assert purchase_context["spender_confidence"] == "high"
    assert purchase_context["premium_sexting_allowed"] is True

    assert tip_context["intimacy_tier"] == "hot"
    assert tip_context["spender_confidence"] == "high"

    assert subscription_context["intimacy_tier"] == "warm"
    assert subscription_context["spender_confidence"] == "medium"

    print("\n======================================")
    print("✅ REALTIME REINFORCEMENT TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()