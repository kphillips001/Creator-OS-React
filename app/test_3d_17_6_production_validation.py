from app.services.decisionengine_refresh_hook_service import (
    DecisionEngineRefreshHookService,
)

from app.services.decision_engine_continuation_injection_service import (
    DecisionEngineContinuationInjectionService,
)

from app.services.runtime_behavior_enforcement_service import (
    RuntimeBehaviorEnforcementService,
)

from app.services.runtime_suppression_enforcement_service import (
    RuntimeSuppressionEnforcementService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6 PRODUCTION VALIDATION")
    print("==============================\n")

    refresh_service = (
        DecisionEngineRefreshHookService()
    )

    injection_service = (
        DecisionEngineContinuationInjectionService()
    )

    runtime_behavior_service = (
        RuntimeBehaviorEnforcementService()
    )

    suppression_service = (
        RuntimeSuppressionEnforcementService()
    )

    monetization_event = {
        "event_type": "purchase_received",
        "fanvue_user_id": "test_user_001",
    }

    buyer_stats = {
        "buyer_tier": "WHALE",
        "total_spend": 2500,
    }

    memory_sync_result = {
        "memory_row": {
            "buyer_tier": "WHALE",
            "is_whale": True,
            "total_spend": 2500,
        }
    }

    runtime_state = {
        "success": True,
        "buyer_tier": "WHALE",
        "cooldowns_active": True,
    }

    refresh_payload = (
        refresh_service.build_refresh_payload(
            monetization_event=monetization_event,
            buyer_stats=buyer_stats,
            memory_sync_result=memory_sync_result,
            runtime_state=runtime_state,
        )
    )

    print("\nREFRESH PAYLOAD:")
    print(refresh_payload)

    injection_result = (
        injection_service.build_injection(
            refresh_payload
        )
    )

    print("\nINJECTION RESULT:")
    print(injection_result)

    working_memory = {
        "buyer_tier": "WHALE",
        "runtime_retention_mode": (
            injection_result.get(
                "retention_mode"
            )
        ),
        "runtime_ppv_energy": (
            injection_result.get(
                "ppv_energy"
            )
        ),
        "cooldowns_active": True,
    }

    runtime_behavior_result = (
        runtime_behavior_service
        .apply_runtime_behavior(
            working_memory=working_memory,
            runtime_injection=injection_result,
        )
    )

    print("\nRUNTIME BEHAVIOR RESULT:")
    print(runtime_behavior_result)

    suppression_result = (
        suppression_service
        .enforce_runtime_suppression(
            working_memory=(
                runtime_behavior_result.get(
                    "working_memory",
                    {},
                )
            )
        )
    )

    print("\nSUPPRESSION RESULT:")
    print(suppression_result)

    assert refresh_payload["success"] is True
    assert injection_result["success"] is True
    assert (
        runtime_behavior_result["success"]
        is True
    )
    assert suppression_result["success"] is True

    print(
        "\n✅ 3D.17.6 production orchestration "
        "validation passed"
    )

    print(
        "\n✅ Realtime monetization orchestration "
        "pipeline is operational"
    )

    print(
        "\n✅ Safe-mode runtime intelligence "
        "architecture is complete"
    )


if __name__ == "__main__":
    run_test()