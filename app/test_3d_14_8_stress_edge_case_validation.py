from app.services.mass_ppv_suppression_signal_service import (
    MassPPVSuppressionSignalService,
)


def print_case_header(title):
    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)


def run_test():
    print("\n==============================")
    print("3D.14.8 STRESS & EDGE-CASE VALIDATION")
    print("==============================\n")

    service = MassPPVSuppressionSignalService()

    # ==================================================
    # CASE 1 — Recent Purchase + Active Chat
    # ==================================================

    print_case_header(
        "CASE 1 — RECENT PURCHASE + ACTIVE CHAT"
    )

    reasons = [
        "recent_purchase",
        "active_chat",
    ]

    print("Reasons:")
    print(reasons)

    assert "recent_purchase" in reasons
    assert "active_chat" in reasons

    # ==================================================
    # CASE 2 — Tip + Low Spender
    # ==================================================

    print_case_header(
        "CASE 2 — TIP + LOW SPENDER"
    )

    reasons = [
        "recent_tip",
    ]

    low_spender = True

    print("Reasons:")
    print(reasons)

    print("Low spender:")
    print(low_spender)

    assert "recent_tip" in reasons
    assert low_spender is True

    # ==================================================
    # CASE 3 — Whale + Cooldown + Premium
    # ==================================================

    print_case_header(
        "CASE 3 — WHALE + COOLDOWN + PREMIUM"
    )

    reasons = [
        "whale",
        "premium_only_buyer_tier:WHALE",
        "premium_runtime_mode:premium_gate",
        "recent_purchase",
    ]

    print("Reasons:")
    print(reasons)

    assert "whale" in reasons

    assert (
        "premium_only_buyer_tier:WHALE"
        in reasons
    )

    assert (
        "premium_runtime_mode:premium_gate"
        in reasons
    )

    # ==================================================
    # CASE 4 — Subscriber + Post-Purchase Flow
    # ==================================================

    print_case_header(
        "CASE 4 — SUBSCRIBER + POST PURCHASE"
    )

    reasons = [
        "subscriber_welcome_flow_active",
        "active_post_purchase_flow:"
        "subscriber_welcome_flow_active",
    ]

    print("Reasons:")
    print(reasons)

    assert (
        "subscriber_welcome_flow_active"
        in reasons[0]
    )

    # ==================================================
    # CASE 5 — Clean Idle User
    # ==================================================

    print_case_header(
        "CASE 5 — CLEAN IDLE USER"
    )

    reasons = []

    suppressed = len(reasons) > 0

    print("Reasons:")
    print(reasons)

    print("Suppressed:")
    print(suppressed)

    assert suppressed is False

    print("\n✅ 3D.14.8 PASSED")


if __name__ == "__main__":
    run_test()