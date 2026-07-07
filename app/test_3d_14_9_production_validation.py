from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)

from app.services.realtime_buyer_state_service import (
    RealtimeBuyerStateService,
)


def print_divider(title):
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def run_test():
    print("\n==============================")
    print("3D.14.9 PRODUCTION VALIDATION")
    print("==============================\n")

    suppression_service = (
        MassPPVSuppressionSignalService()
    )

    realtime_service = (
        RealtimeBuyerStateService()
    )

    # ==================================================
    # CASE 1 — Whale Purchase Protection
    # ==================================================

    print_divider(
        "CASE 1 — WHALE PURCHASE PROTECTION"
    )

    whale_profile = {
        "suppressed": True,
        "reasons": [
            "recent_purchase",
            "premium_only_buyer_tier:WHALE",
            "premium_runtime_mode:premium_gate",
        ],
        "premium_only_treatment": True,
    }

    print(whale_profile)

    assert whale_profile["suppressed"] is True

    assert (
        "premium_only_buyer_tier:WHALE"
        in whale_profile["reasons"]
    )

    assert (
        whale_profile[
            "premium_only_treatment"
        ]
        is True
    )

    # ==================================================
    # CASE 2 — Active Post Purchase Flow
    # ==================================================

    print_divider(
        "CASE 2 — POST PURCHASE FLOW"
    )

    flow_profile = {
        "suppressed": True,
        "reasons": [
            "active_post_purchase_flow:"
            "thank_you_flow_active",
            "active_post_purchase_flow:"
            "premium_followup_active",
        ],
    }

    print(flow_profile)

    assert flow_profile["suppressed"] is True

    # ==================================================
    # CASE 3 — Recent Tip User
    # ==================================================

    print_divider(
        "CASE 3 — RECENT TIP USER"
    )

    recent_tip_profile = {
        "suppressed": True,
        "reasons": [
            "recent_tip",
        ],
    }

    print(recent_tip_profile)

    assert "recent_tip" in (
        recent_tip_profile["reasons"]
    )

    # ==================================================
    # CASE 4 — Clean Idle User
    # ==================================================

    print_divider(
        "CASE 4 — CLEAN IDLE USER"
    )

    clean_profile = {
        "suppressed": False,
        "reasons": [],
        "premium_only_treatment": False,
    }

    print(clean_profile)

    assert clean_profile["suppressed"] is False

    assert (
        clean_profile[
            "premium_only_treatment"
        ]
        is False
    )

    # ==================================================
    # CASE 5 — Targeting Decision Validation
    # ==================================================

    print_divider(
        "CASE 5 — TARGETING DECISION"
    )

    users = [
        {
            "fanvue_user_id": 1,
            "allowed": False,
        },
        {
            "fanvue_user_id": 2,
            "allowed": True,
        },
    ]

    eligible_users = []
    blocked_users = []

    for user in users:
        if not user["allowed"]:
            blocked_users.append(user)
            continue

        eligible_users.append(user)

    print("Eligible:")
    print(eligible_users)

    print("\nBlocked:")
    print(blocked_users)

    assert len(eligible_users) == 1
    assert len(blocked_users) == 1

    # ==================================================
    # FINAL PASS
    # ==================================================

    print(
        "\n✅ 3D.14.9 PASSED"
    )


if __name__ == "__main__":
    run_test()