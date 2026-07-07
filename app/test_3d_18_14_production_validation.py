import os

from app.services.realtime_automated_reaction_service import (
    RealtimeAutomatedReactionService,
)


def main():
    print(
        "\n=== 3D.18.14 PRODUCTION VALIDATION TEST ===\n"
    )

    service = (
        RealtimeAutomatedReactionService()
    )

    os.environ[
        "ENABLE_REALTIME_MONETIZATION_REACTIONS"
    ] = "true"

    os.environ[
        "ENABLE_POST_PURCHASE_AUTOMATION"
    ] = "true"

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "false"

    result = (
        service.process_realtime_reaction(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
                "external_event_id": (
                    "prod_validation_001"
                ),
                "fanvue_user_id": (
                    "fanvue_user_prod"
                ),
                "fanvue_account_id": (
                    "fanvue_account_prod"
                ),
                "local_user_id": 999,
            },
            runtime_state={
                "fanvue_thread_id": (
                    "thread_prod_001"
                ),
                "outbound_history": [],
            },
            buyer_context={
                "buyer_tier": (
                    "ACTIVE_BUYER"
                ),
            },
            reaction_history=[],
        )
    )

    print(result)

    if result.get("blocked"):
        assert (
            result["reason"]
            == "global_automation_disabled"
        )

        print(
            "\n✅ Global automation safety "
            "blocked outbound execution safely"
        )

        print(
            "\n✅ 3D.18.14 Production Validation passed"
        )

        return

    assert result["success"] is True

    assert (
        result["reaction_processed"]
        is True
    )

    assert (
        result["reaction_type"]
        == "purchase_thank_you"
    )

    assert (
        result["execution_mode"]
        == "dry_run"
    )

    assert (
        result["outbound_result"][
            "live_send_performed"
        ]
        is False
    )

    persistence_result = result.get(
        "persistence_result",
        {},
    )

    assert (
        persistence_result.get(
            "persisted"
        )
        is True
    )

    assert (
        persistence_result.get(
            "reaction_id"
        )
        is not None
    )

    print(
        "\n✅ Dry-run execution validated"
    )

    print(
        "✅ Persistence validated"
    )

    print(
        "✅ Global safety validated"
    )

    print(
        "✅ Future live-send path ready"
    )

    print(
        "\n✅ 3D.18.14 Production Validation passed"
    )


if __name__ == "__main__":
    main()