from app.services.automated_reaction_message_builder_service import (
    AutomatedReactionMessageBuilderService,
)


def main():
    service = AutomatedReactionMessageBuilderService()

    print("\n=== 3D.18.9 REACTION MESSAGE BUILDER TEST ===\n")

    reaction_types = [
        "purchase_thank_you",
        "unlock_followup",
        "tip_thank_you",
        "subscription_welcome",
        "premium_followup",
        "whale_retention_message",
    ]

    for reaction_type in reaction_types:
        result = service.build_message(
            reaction_type=reaction_type,
            monetization_event={
                "external_event_id": "event_123",
                "fanvue_user_id": "fanvue_user_abc",
                "fanvue_account_id": "fanvue_account_abc",
                "local_user_id": 123,
            },
            buyer_context={
                "buyer_tier": "ACTIVE_BUYER",
            },
        )

        print(reaction_type)
        print(result)

        assert result["success"] is True
        assert result["blocked"] is False
        assert result["message_built"] is True
        assert result["message_text"]

        print("PASS\n")

    unsupported_result = service.build_message(
        reaction_type="unknown_reaction",
    )

    print("unsupported reaction")
    print(unsupported_result)

    assert unsupported_result["success"] is False
    assert unsupported_result["blocked"] is True
    assert unsupported_result["reason"] == "unsupported_reaction_type"

    print("PASS\n")

    print("✅ 3D.18.9 Reaction Message Builder passed")


if __name__ == "__main__":
    main()