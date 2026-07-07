from app.services.post_purchase_continuation_service import (
    PostPurchaseContinuationService,
)


def run_test():
    print("\n==============================")
    print(" 3D.17.4 CONTINUATION ROUTING")
    print("==============================\n")

    service = (
        PostPurchaseContinuationService()
    )

    result = service.determine_continuation(
        monetization_event={
            "event_type": "purchase_created",
        },
        buyer_memory_context={
            "buyer_tier": "ACTIVE_BUYER",
            "total_spend": 325.00,
        },
        runtime_buyer_state={
            "runtime_mode": "premium_gate",
            "premium_allowed": True,
            "continuation_eligible": True,
        },
    )

    print("[CONTINUATION ROUTE]")
    print(result)

    required_keys = [
        "success",
        "continuation_eligible",
        "continuation_type",
        "escalation_level",
        "retention_mode",
        "suppression_active",
        "runtime_mode",
        "premium_allowed",
        "buyer_tier",
    ]

    for key in required_keys:
        assert key in result, f"Missing key: {key}"
        print(f"{key}: ✅ PASS")

    assert result["success"] is True
    assert result["continuation_eligible"] is True
    assert (
        result["continuation_type"]
        == "premium_continuation"
    )
    assert (
        result["retention_mode"]
        == "premium"
    )

    print("\n✅ 3D.17.4 TEST COMPLETE")
    print(
        "Post-purchase continuation routing is operational."
    )


if __name__ == "__main__":
    run_test()