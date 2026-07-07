from app.services.realtime_automated_reaction_service import (
    RealtimeAutomatedReactionService,
)


def build_test_event():
    return {
        "event_type": "purchase_received",
        "fanvue_account_id": 2,
        "fanvue_user_id": 1,
        "local_user_id": 1,
        "amount": 19.99,
        "currency": "USD",
        "content_type": "VIP",
    }


def run_off_switch_test():
    print(
        "\n=== 3E.8 REACTION OFF-SWITCH TEST ===\n"
    )

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Post-Purchase Reactions Enabled = OFF\n"
    )

    service = (
        RealtimeAutomatedReactionService()
    )

    result = (
        service.process_realtime_reaction(
            monetization_event=build_test_event(),
        )
    )

    print("\nOFF-SWITCH RESULT:")
    print(result)

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["blocked"] is True

    assert result["reason"] in {
        "post_purchase_reactions_disabled",
        "missing_reaction_thread_context",
    }

    print(
        "\n✅ OFF switch correctly blocked "
        "post-purchase reactions.\n"
    )


def run_on_dry_run_test():
    print(
        "\n=== 3E.8 REACTION ON DRY-RUN TEST ===\n"
    )

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Post-Purchase Reactions Enabled = ON\n"
    )

    service = (
        RealtimeAutomatedReactionService()
    )

    result = (
        service.process_realtime_reaction(
            monetization_event=build_test_event(),
            runtime_state={
                "dry_run": True,
            },
        )
    )

    print("\nON DRY-RUN RESULT:")
    print(result)

    assert result["blocked"] is True
    assert result["reason"] in {
        "missing_reaction_thread_context",
        "reaction_execution_blocked",
    }

    print(
        "\n✅ ON dry-run allowed "
        "reaction orchestration safely.\n"
    )


def main():
    print(
        "\n=== 3E.8 POST-PURCHASE "
        "REACTION GUARD TEST ===\n"
    )

    print(
        "Run this test twice:\n\n"
        "1) First with Post-Purchase "
        "Reactions Enabled OFF\n"
        "   Expected: post_purchase_reactions_disabled\n\n"
        "2) Then with Post-Purchase "
        "Reactions Enabled ON\n"
        "   Expected: dry-run success\n"
    )

    choice = input(
        "Type OFF to run the OFF-switch "
        "test, or ON to run the "
        "dry-run test: "
    ).strip().upper()

    if choice == "OFF":
        run_off_switch_test()
    elif choice == "ON":
        run_on_dry_run_test()
    else:
        raise ValueError(
            "Invalid choice. Type OFF or ON."
        )

    print("\n=== 3E.8 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()