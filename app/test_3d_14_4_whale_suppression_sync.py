from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.4 WHALE SUPPRESSION SYNC TEST")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    buyer_tier = "WHALE"
    value_tier = "HIGH_VALUE"

    reasons = []

    if buyer_tier in service.PROTECTED_BUYER_TIERS:
        reasons.append(
            f"protected_buyer_tier:{buyer_tier}"
        )

    if (
        buyer_tier
        in service.PREMIUM_ONLY_BUYER_TIERS
    ):
        reasons.append(
            f"premium_only_buyer_tier:{buyer_tier}"
        )

    if value_tier in service.PROTECTED_BUYER_TIERS:
        reasons.append(
            f"protected_value_tier:{value_tier}"
        )

    if (
        value_tier
        in service.PREMIUM_ONLY_VALUE_TIERS
    ):
        reasons.append(
            f"premium_only_value_tier:{value_tier}"
        )

    premium_only_treatment = (
        buyer_tier
        in service.PREMIUM_ONLY_BUYER_TIERS
        or value_tier
        in service.PREMIUM_ONLY_VALUE_TIERS
    )

    print("Reasons:")
    print(reasons)

    print("\nPremium-only treatment:")
    print(premium_only_treatment)

    assert (
        "protected_buyer_tier:WHALE"
        in reasons
    )

    assert (
        "premium_only_buyer_tier:WHALE"
        in reasons
    )

    assert (
        "premium_only_value_tier:HIGH_VALUE"
        in reasons
    )

    assert premium_only_treatment is True

    print("\n✅ 3D.14.4 PASSED")


if __name__ == "__main__":
    run_test()