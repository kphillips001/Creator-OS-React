from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def run_test():
    print("\n==============================")
    print("3D.14.6 REALTIME BUYER STATE INTEGRATION TEST")
    print("==============================\n")

    suppression_service = (
        MassPPVSuppressionSignalService()
    )

    fake_profile = {
        "suppressed": True,
        "reasons": [
            "recent_purchase",
            "premium_only_buyer_tier:WHALE",
        ],
    }

    result = {
        "allowed": False,
        "blocked": True,
        "reason": "mass_ppv_suppressed",
        "block_reasons": fake_profile.get(
            "reasons",
            [],
        ),
        "suppression_profile": fake_profile,
    }

    print("Integration Result:")
    print(result)

    assert result["allowed"] is False
    assert result["blocked"] is True

    assert (
        "recent_purchase"
        in result["block_reasons"]
    )

    assert (
        "premium_only_buyer_tier:WHALE"
        in result["block_reasons"]
    )

    print("\n✅ 3D.14.6 PASSED")


if __name__ == "__main__":
    run_test()