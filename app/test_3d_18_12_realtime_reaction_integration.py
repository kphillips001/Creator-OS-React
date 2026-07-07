import os

from app.services.realtime_automated_reaction_service import (
    RealtimeAutomatedReactionService,
)


def main():
    service = (
        RealtimeAutomatedReactionService()
    )

    print(
        "\n=== 3D.18.12 REALTIME REACTION TEST ===\n"
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
                    "rt_event_123"
                ),
                "fanvue_user_id": (
                    "fanvue_user_abc"
                ),
                "fanvue_account_id": (
                    "fanvue_account_abc"
                ),
                "local_user_id": 123,
            },
            runtime_state={
                "fanvue_thread_id": (
                    "thread_123"
                )
            },
            buyer_context={
                "buyer_tier": (
                    "ACTIVE_BUYER"
                )
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
            "\n✅ 3D.18.12 Realtime Reaction Integration passed "
            "(blocked safely by global automation safety)"
        )

        return

    assert result["success"] is True

    assert (
        result["reaction_processed"]
        is True
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

    print(
        "\n✅ 3D.18.12 Realtime Reaction Integration passed"
    )


if __name__ == "__main__":
    main()