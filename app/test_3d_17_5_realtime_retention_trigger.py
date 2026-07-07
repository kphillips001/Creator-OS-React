from app.services.realtime_retention_trigger_service import (
    RealtimeRetentionTriggerService,
)


def run_test():
    print("\n==============================")
    print(" 3D.17.5 RETENTION TRIGGER")
    print("==============================\n")

    service = (
        RealtimeRetentionTriggerService()
    )

    result = service.build_retention_route(
        continuation_route={
            "continuation_type": (
                "premium_continuation"
            ),
            "escalation_level": "high",
        },
        runtime_buyer_state={
            "runtime_mode": "premium_gate",
        },
        buyer_memory_context={
            "buyer_tier": "ACTIVE_BUYER",
            "total_spend": 350.00,
        },
    )

    print("[RETENTION ROUTE]")
    print(result)

    required_keys = [
        "success",
        "retention_strategy",
        "followup_allowed",
        "emotional_continuation",
        "monetization_continuation",
        "premium_routing",
        "suppression_active",
        "runtime_mode",
        "buyer_tier",
    ]

    for key in required_keys:
        assert key in result, f"Missing key: {key}"
        print(f"{key}: ✅ PASS")

    assert result["success"] is True

    assert (
        result["retention_strategy"]
        == "premium_escalation"
    )

    assert (
        result["followup_allowed"]
        is True
    )

    assert (
        result["premium_routing"]
        is True
    )

    assert (
        result["emotional_continuation"]
        is True
    )

    print("\n✅ 3D.17.5 TEST COMPLETE")
    print(
        "Realtime retention trigger layer is operational."
    )


if __name__ == "__main__":
    run_test()