from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.3 PREMIUM INTIMACY SUPPRESSION TEST")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    memory = {
        "runtime_mode": "premium_gate",
        "spender_confidence": "high",
        "premium_sexting_allowed": True,
    }

    buyer = {}

    runtime_mode = service._safe_lower(
        memory.get("runtime_mode")
    )

    spender_confidence = service._safe_lower(
        memory.get("spender_confidence")
    )

    premium_allowed = service._truthy(
        memory.get("premium_sexting_allowed")
    )

    reasons = []

    if runtime_mode in service.PREMIUM_RUNTIME_BLOCK_MODES:
        reasons.append(
            f"premium_runtime_mode:{runtime_mode}"
        )

    if (
        spender_confidence
        in service.HIGH_CONFIDENCE_VALUES
    ):
        reasons.append(
            f"high_spender_confidence:{spender_confidence}"
        )

    if premium_allowed:
        reasons.append(
            "premium_sexting_allowed"
        )

    print("Suppression reasons:")
    print(reasons)

    assert "premium_runtime_mode:premium_gate" in reasons

    assert (
        "high_spender_confidence:high"
        in reasons
    )

    assert "premium_sexting_allowed" in reasons

    print("\n✅ 3D.14.3 PASSED")


if __name__ == "__main__":
    run_test()