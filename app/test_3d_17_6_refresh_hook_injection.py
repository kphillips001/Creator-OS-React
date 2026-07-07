from app.services.decisionengine_refresh_hook_service import (
    DecisionEngineRefreshHookService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6 REFRESH HOOK INJECTION TEST")
    print("==============================\n")

    service = DecisionEngineRefreshHookService()

    result = service.build_refresh_payload(
        monetization_event={
            "event_type": "purchase_received",
        },
        buyer_stats={
            "buyer_tier": "ACTIVE_BUYER",
        },
        memory_sync_result={
            "buyer_tier": "ACTIVE_BUYER",
        },
    )

    print(result)

    injection = result.get(
        "decisionengine_injection"
    )

    assert injection is not None
    assert injection["success"] is True

    assert (
        injection["response_strategy"]
        is not None
    )

    assert (
        injection["suppression_handling"]
        == "suppress_mass_ppv_and_preserve_premium_flow"
    )

    print(
        "\n✅ 3D.17.6 refresh hook injection passed"
    )


if __name__ == "__main__":
    run_test()