from app.services.automated_reaction_duplicate_protection_service import (
    AutomatedReactionDuplicateProtectionService,
)


def main():
    service = (
        AutomatedReactionDuplicateProtectionService()
    )

    print(
        "\n=== 3D.18.4 DUPLICATE REACTION TEST ===\n"
    )

    safe_result = (
        service.validate_duplicate_reaction(
            monetization_event={
                "external_event_id": (
                    "purchase_event_123"
                ),
                "fanvue_user_id": (
                    "fanvue_user_abc"
                ),
            },
            reaction_type="purchase_thank_you",
            reaction_history=[],
        )
    )

    print("safe reaction")
    print(safe_result)

    assert safe_result["success"] is True
    assert safe_result["blocked"] is False
    print("PASS\n")

    duplicate_event_result = (
        service.validate_duplicate_reaction(
            monetization_event={
                "external_event_id": (
                    "purchase_event_123"
                ),
                "fanvue_user_id": (
                    "fanvue_user_abc"
                ),
            },
            reaction_type="purchase_thank_you",
            reaction_history=[
                {
                    "event_id": (
                        "purchase_event_123"
                    ),
                    "reaction_type": (
                        "purchase_thank_you"
                    ),
                    "fanvue_user_id": (
                        "fanvue_user_abc"
                    ),
                }
            ],
        )
    )

    print("duplicate event")
    print(duplicate_event_result)

    assert (
        duplicate_event_result["success"]
        is False
    )

    assert (
        duplicate_event_result["blocked"]
        is True
    )

    assert (
        duplicate_event_result["reason"]
        == "duplicate_event_reaction"
    )

    print("PASS\n")

    duplicate_user_result = (
        service.validate_duplicate_reaction(
            monetization_event={
                "external_event_id": (
                    "purchase_event_999"
                ),
                "fanvue_user_id": (
                    "fanvue_user_abc"
                ),
            },
            reaction_type="purchase_thank_you",
            reaction_history=[
                {
                    "event_id": (
                        "older_event"
                    ),
                    "reaction_type": (
                        "purchase_thank_you"
                    ),
                    "fanvue_user_id": (
                        "fanvue_user_abc"
                    ),
                }
            ],
        )
    )

    print("duplicate user reaction type")
    print(duplicate_user_result)

    assert (
        duplicate_user_result["success"]
        is False
    )

    assert (
        duplicate_user_result["blocked"]
        is True
    )

    assert (
        duplicate_user_result["reason"]
        == "duplicate_user_reaction_type"
    )

    print("PASS\n")

    print(
        "✅ 3D.18.4 Duplicate Reaction Protection passed"
    )


if __name__ == "__main__":
    main()