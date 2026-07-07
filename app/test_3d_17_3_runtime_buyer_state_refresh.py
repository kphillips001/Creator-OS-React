from app.services.runtime_buyer_state_refresh_service import (
    RuntimeBuyerStateRefreshService,
)


def run_test():
    print("\n==============================")
    print(" 3D.17.3 RUNTIME BUYER STATE")
    print("==============================\n")

    service = RuntimeBuyerStateRefreshService()

    result = service.refresh_runtime_state(
        buyer_memory_context={
            "buyer_tier": "ACTIVE_BUYER",
            "total_spend": 125.00,
            "owned_content_count": 6,
            "repeat_purchase_score": 45,
            "is_whale": False,
            "is_subscriber": True,
        }
    )

    print("[RUNTIME BUYER STATE]")
    print(result)

    required_keys = [
        "success",
        "buyer_tier",
        "spender_confidence",
        "runtime_mode",
        "premium_allowed",
        "continuation_eligible",
        "mass_ppv_blocked",
        "cooldowns_active",
        "total_spend",
        "owned_content_count",
        "repeat_purchase_score",
    ]

    for key in required_keys:
        assert key in result, f"Missing key: {key}"
        print(f"{key}: ✅ PASS")

    assert result["success"] is True
    assert result["buyer_tier"] == "ACTIVE_BUYER"
    assert result["premium_allowed"] is True
    assert result["runtime_mode"] == "premium_gate"
    assert result["continuation_eligible"] is True

    print("\n✅ 3D.17.3 TEST COMPLETE")
    print("Runtime buyer-state refresh is operational.")


if __name__ == "__main__":
    run_test()