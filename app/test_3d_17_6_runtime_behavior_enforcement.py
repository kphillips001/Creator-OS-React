from app.services.runtime_behavior_enforcement_service import (
    RuntimeBehaviorEnforcementService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6.5 RUNTIME ENFORCEMENT TEST")
    print("==============================\n")

    service = RuntimeBehaviorEnforcementService()

    working_memory = {
        "conversation_mode": "conversion",
    }

    runtime_injection = {
        "response_strategy": "premium_retention",
        "retention_mode": "whale_retention",
        "ppv_energy": "low_pressure",
        "emotional_continuation": (
            "exclusive_emotional_continuity"
        ),
    }

    result = service.apply_runtime_behavior(
        working_memory=working_memory,
        runtime_injection=runtime_injection,
    )

    print(result)

    assert result["success"] is True
    assert (
        result["working_memory"][
            "response_strategy"
        ]
        == "premium_retention"
    )

    print(
        "\n✅ 3D.17.6.5 runtime behavior "
        "enforcement passed"
    )


if __name__ == "__main__":
    run_test()