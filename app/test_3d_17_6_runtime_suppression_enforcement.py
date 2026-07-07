from app.services.runtime_suppression_enforcement_service import (
    RuntimeSuppressionEnforcementService,
)


def run_test():
    print("\n==============================")
    print("3D.17.6.7 SUPPRESSION TEST")
    print("==============================\n")

    service = (
        RuntimeSuppressionEnforcementService()
    )

    working_memory = {
        "buyer_tier": "WHALE",
        "runtime_retention_mode": (
            "whale_retention"
        ),
        "runtime_ppv_energy": "high",
        "cooldowns_active": True,
    }

    result = (
        service.enforce_runtime_suppression(
            working_memory=working_memory
        )
    )

    print(result)

    assert result["success"] is True
    assert (
        result["suppression_triggered"]
        is True
    )

    print(
        "\n✅ 3D.17.6.7 runtime suppression "
        "enforcement passed"
    )


if __name__ == "__main__":
    run_test()