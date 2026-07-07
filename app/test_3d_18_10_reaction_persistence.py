from app.services.automated_reaction_persistence_service import (
    AutomatedReactionPersistenceService,
)


def main():
    service = AutomatedReactionPersistenceService()

    print("\n=== 3D.18.10 REACTION PERSISTENCE TEST ===\n")

    result = service.persist_reaction(
        message_payload={
            "external_event_id": "event_3d_18_10_test",
            "fanvue_user_id": "fanvue_user_test",
            "fanvue_account_id": "fanvue_account_test",
            "local_user_id": 123,
            "reaction_type": "purchase_thank_you",
            "message_text": "Aww thank you babe 💕",
        },
        execution_mode_result={
            "execution_mode": "dry_run",
            "dry_run": True,
            "live_send_allowed": False,
        },
        status="planned",
    )

    print(result)

    assert result["success"] is True
    assert result["persisted"] is True
    assert result["reaction_id"]
    assert result["reaction_type"] == "purchase_thank_you"
    assert result["status"] == "planned"

    print("\n✅ 3D.18.10 Reaction Persistence passed")


if __name__ == "__main__":
    main()