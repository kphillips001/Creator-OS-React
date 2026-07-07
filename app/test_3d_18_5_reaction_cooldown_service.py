from datetime import datetime, timedelta

from app.services.automated_reaction_cooldown_service import (
    AutomatedReactionCooldownService,
)


def main():
    service = (
        AutomatedReactionCooldownService()
    )

    print(
        "\n=== 3D.18.5 COOLDOWN TEST ===\n"
    )

    now = datetime.utcnow()

    safe_result = (
        service.validate_cooldown(
            reaction_type="purchase_thank_you",
            user_memory={},
            outbound_history=[],
            now=now,
        )
    )

    print("safe cooldown")
    print(safe_result)

    assert safe_result["success"] is True
    assert safe_result["blocked"] is False

    print("PASS\n")

    cooldown_result = (
        service.validate_cooldown(
            reaction_type="purchase_thank_you",
            user_memory={
                "last_purchase_thank_you_at": (
                    now - timedelta(minutes=2)
                ).isoformat()
            },
            outbound_history=[],
            now=now,
        )
    )

    print("cooldown active")
    print(cooldown_result)

    assert cooldown_result["success"] is False
    assert cooldown_result["blocked"] is True
    assert (
        cooldown_result["reason"]
        == "reaction_cooldown_active"
    )

    print("PASS\n")

    outbound_result = (
        service.validate_cooldown(
            reaction_type="purchase_thank_you",
            user_memory={},
            outbound_history=[
                {
                    "sent_at": (
                        now - timedelta(minutes=1)
                    ).isoformat()
                }
            ],
            now=now,
        )
    )

    print("recent outbound activity")
    print(outbound_result)

    assert outbound_result["success"] is False
    assert outbound_result["blocked"] is True
    assert (
        outbound_result["reason"]
        == "recent_outbound_activity"
    )

    print("PASS\n")

    expired_cooldown_result = (
        service.validate_cooldown(
            reaction_type="purchase_thank_you",
            user_memory={
                "last_purchase_thank_you_at": (
                    now - timedelta(minutes=20)
                ).isoformat()
            },
            outbound_history=[],
            now=now,
        )
    )

    print("expired cooldown")
    print(expired_cooldown_result)

    assert (
        expired_cooldown_result["success"]
        is True
    )

    assert (
        expired_cooldown_result["blocked"]
        is False
    )

    print("PASS\n")

    print(
        "✅ 3D.18.5 Cooldown Protection passed"
    )


if __name__ == "__main__":
    main()