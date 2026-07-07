from app.services.automated_reaction_buyer_session_safety_service import (
    AutomatedReactionBuyerSessionSafetyService,
)


def main():
    service = AutomatedReactionBuyerSessionSafetyService()

    print(
        "\n=== 3D.18.6 BUYER SESSION SAFETY TEST ===\n"
    )

    safe_result = service.validate_buyer_session_safety(
        reaction_type="purchase_thank_you",
        runtime_state={
            "buyer_session_active": False,
        },
    )

    print("no active session")
    print(safe_result)

    assert safe_result["success"] is True
    assert safe_result["blocked"] is False
    assert safe_result["reason"] == "no_active_buyer_session"

    print("PASS\n")

    close_mode_allowed_result = (
        service.validate_buyer_session_safety(
            reaction_type="purchase_thank_you",
            runtime_state={
                "buyer_session_active": True,
                "buyer_session_step": "close",
                "close_mode": True,
            },
        )
    )

    print("soft thank-you allowed during close mode")
    print(close_mode_allowed_result)

    assert close_mode_allowed_result["success"] is True
    assert close_mode_allowed_result["blocked"] is False
    assert (
        close_mode_allowed_result["reason"]
        == "soft_reaction_allowed_during_close_mode"
    )

    print("PASS\n")

    close_mode_blocked_result = (
        service.validate_buyer_session_safety(
            reaction_type="premium_followup",
            runtime_state={
                "buyer_session_active": True,
                "buyer_session_step": "close",
                "close_mode": True,
            },
        )
    )

    print("premium followup blocked during close mode")
    print(close_mode_blocked_result)

    assert close_mode_blocked_result["success"] is False
    assert close_mode_blocked_result["blocked"] is True
    assert (
        close_mode_blocked_result["reason"]
        == "close_mode_reaction_blocked"
    )

    print("PASS\n")

    session_blocked_result = (
        service.validate_buyer_session_safety(
            reaction_type="whale_retention_message",
            runtime_state={
                "buyer_session_active": True,
                "buyer_session_step": "controlled_ppv",
            },
        )
    )

    print("whale retention blocked during controlled PPV")
    print(session_blocked_result)

    assert session_blocked_result["success"] is False
    assert session_blocked_result["blocked"] is True
    assert (
        session_blocked_result["reason"]
        == "buyer_session_reaction_blocked"
    )

    print("PASS\n")

    normal_session_safe_result = (
        service.validate_buyer_session_safety(
            reaction_type="unlock_followup",
            runtime_state={
                "buyer_session_active": True,
                "buyer_session_step": "bridge",
            },
        )
    )

    print("normal active session safe")
    print(normal_session_safe_result)

    assert normal_session_safe_result["success"] is True
    assert normal_session_safe_result["blocked"] is False
    assert (
        normal_session_safe_result["reason"]
        == "buyer_session_reaction_safe"
    )

    print("PASS\n")

    print(
        "✅ 3D.18.6 Buyer Session Safety passed"
    )


if __name__ == "__main__":
    main()