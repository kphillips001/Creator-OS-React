from app.services.decisionengine_refresh_hook_service import (
    DecisionEngineRefreshHookService,
)


def run_test():
    print("\n==============================")
    print(" 3D.17.1 REFRESH HOOK")
    print("==============================\n")

    service = (
        DecisionEngineRefreshHookService()
    )

    result = service.build_refresh_payload(
        monetization_event={
            "fanvue_user_id": "1",
            "event_type": "purchase_created",
        },
        buyer_stats={
            "purchase_count": 5,
        },
        memory_sync_result={
            "memory_row": {
                "buyer_tier": "ACTIVE_BUYER",
                "owned_content_count": 7,
            }
        },
        intimacy_reinforcement={
            "intimacy_score": 85,
        },
        runtime_state={
            "session_active": True,
        },
        reaction_pipeline_result={
            "decision": "thank_you_only",
        },
    )

    print("[REFRESH PAYLOAD]")
    print(result)

    checks = {
        "success": result.get("success") is True,
        "fanvue_user_id":
            result.get("fanvue_user_id") == "1",

        "decisionengine_refresh_required":
            result.get(
                "decisionengine_refresh_required"
            ) is True,

        "buyer_memory_refresh_completed":
            result.get(
                "buyer_memory_refresh_completed"
            ) is True,

        "runtime_refresh_completed":
            result.get(
                "runtime_refresh_completed"
            ) is True,

        "ownership intelligence exists":
            "ownership_intelligence" in result,

        "automation flags exist":
            "automation_allowed" in result,

        "continuation eligibility exists":
            "continuation_eligible" in result,
    }

    for label, passed in checks.items():
        print(
            f"{label}: "
            f"{'✅ PASS' if passed else '❌ FAIL'}"
        )

        assert passed, label

    print("\n✅ 3D.17.1 TEST COMPLETE")
    print("DecisionEngine refresh hook is operational.")


if __name__ == "__main__":
    run_test()