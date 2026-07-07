from app.services.decision_engine_intimacy_integration_service import (
    DecisionEngineIntimacyIntegrationService,
)


def build_memory(
    intimacy_tier,
    spender_confidence,
    runtime_mode,
):
    return {
        "intimacy_context": {
            "intimacy_tier": intimacy_tier,
            "spender_confidence": spender_confidence,
            "premium_sexting_allowed": (
                intimacy_tier == "premium"
            ),
            "explicit_allowed": False,
            "runtime_mode": runtime_mode,
        }
    }


def run_case(
    service,
    title,
    intimacy_tier,
    spender_confidence,
    runtime_mode,
):
    print("\n================================")
    print(title)
    print("================================")

    overrides = service.build_overrides(
        build_memory(
            intimacy_tier,
            spender_confidence,
            runtime_mode,
        )
    )

    for key, value in overrides.items():
        print(f"{key}: {value}")

    return overrides


def run_test():
    print("\n======================================")
    print("3D.10.15H — DECISION ENGINE INTEGRATION")
    print("======================================\n")

    service = (
        DecisionEngineIntimacyIntegrationService()
    )

    run_case(
        service,
        "CASE 1 — WARM USER",
        "warm",
        "low",
        "premium_gate",
    )

    run_case(
        service,
        "CASE 2 — HOT USER",
        "hot",
        "high",
        "premium_gate",
    )

    run_case(
        service,
        "CASE 3 — PREMIUM USER",
        "premium",
        "high",
        "explicit_allowed",
    )

    print("\n======================================")
    print("✅ DECISION ENGINE INTEGRATION COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()