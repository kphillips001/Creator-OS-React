from app.services.decisionengine_refresh_hook_service import (
    DecisionEngineRefreshHookService,
)


def run_test():
    print("\n==============================")
    print(" 3D.17.2 BUYER MEMORY REFRESH")
    print("==============================\n")

    service = DecisionEngineRefreshHookService()

    result = service.build_buyer_memory_context(
        memory_sync_result={
            "memory_row": {
                "buyer_tier": "ACTIVE_BUYER",
                "user_value_tier": "ACTIVE_BUYER",
                "total_spend": 125.00,
                "purchase_count": 6,
                "total_tip_amount": 40.00,
                "recent_purchase_active": True,
                "recent_tip_active": False,
                "is_spender": True,
                "is_whale": False,
                "is_subscriber": True,
                "subscription_status": "ACTIVE",
                "owned_content_count": 4,
                "owned_vip_count": 3,
                "owned_premium_count": 1,
                "recent_owned_content_tags": [
                    "VIP_SET_01",
                    "PREMIUM_SET_01",
                ],
                "collector_score": 40,
                "repeat_purchase_score": 39,
            }
        }
    )

    print("[BUYER MEMORY CONTEXT]")
    print(result)

    required_keys = [
        "success",
        "buyer_memory_available",
        "memory_row",
        "buyer_tier",
        "user_value_tier",
        "total_spend",
        "purchase_count",
        "owned_content_count",
        "recent_owned_content_tags",
        "collector_score",
        "repeat_purchase_score",
    ]

    for key in required_keys:
        assert key in result, f"Missing key: {key}"
        print(f"{key}: ✅ PASS")

    assert result["success"] is True
    assert result["buyer_memory_available"] is True
    assert result["buyer_tier"] == "ACTIVE_BUYER"
    assert result["owned_content_count"] == 4

    print("\n✅ 3D.17.2 TEST COMPLETE")
    print("Buyer memory refresh propagation is operational.")


if __name__ == "__main__":
    run_test()