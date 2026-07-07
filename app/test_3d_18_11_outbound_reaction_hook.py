from app.services.automated_reaction_outbound_service import (
    AutomatedReactionOutboundService,
)


def main():
    service = (
        AutomatedReactionOutboundService()
    )

    print(
        "\n=== 3D.18.11 OUTBOUND HOOK TEST ===\n"
    )

    dry_run_result = (
        service.execute_reaction(
            message_payload={
                "reaction_type": (
                    "purchase_thank_you"
                ),
                "message_text": (
                    "Aww thank you babe 💕"
                ),
            },
            execution_mode_result={
                "execution_mode": (
                    "dry_run"
                )
            },
        )
    )

    print("dry run execution")
    print(dry_run_result)

    assert dry_run_result["success"] is True
    assert dry_run_result["dry_run"] is True
    assert (
        dry_run_result[
            "live_send_performed"
        ]
        is False
    )

    print("PASS\n")

    live_mode_result = (
        service.execute_reaction(
            message_payload={
                "reaction_type": (
                    "tip_thank_you"
                ),
                "message_text": (
                    "You’re too sweet 💕"
                ),
            },
            execution_mode_result={
                "execution_mode": (
                    "live_send"
                )
            },
        )
    )

    print("future live send mode")
    print(live_mode_result)

    assert live_mode_result["success"] is True
    assert (
        live_mode_result[
            "future_live_send"
        ]
        is True
    )

    assert (
        live_mode_result[
            "live_send_performed"
        ]
        is False
    )

    print("PASS\n")

    blocked_result = (
        service.execute_reaction(
            message_payload={
                "reaction_type": (
                    "unlock_followup"
                ),
                "message_text": (
                    "Mmm you unlocked it 😏"
                ),
            },
            execution_mode_result={
                "execution_mode": (
                    "blocked"
                )
            },
        )
    )

    print("blocked execution")
    print(blocked_result)

    assert blocked_result["success"] is False
    assert blocked_result["blocked"] is True

    print("PASS\n")

    print(
        "✅ 3D.18.11 Outbound Reaction Hook passed"
    )


if __name__ == "__main__":
    main()