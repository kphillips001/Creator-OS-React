from app.services.outreach_runner import OutreachRunner


def run_off_switch_test():
    print("\n=== 3E.5 OFF-SWITCH TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Outreach Enabled = OFF\n"
    )

    runner = OutreachRunner()

    result = runner.run_outreach_cycle(
        fanvue_account_id=2,
        limit=1,
        dry_run=True,
    )

    print("\nOFF-SWITCH RESULT:")
    print(result)

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["status"] == "blocked"
    assert result["processed_count"] == 0
    assert result["candidate_count"] == 0
    assert result["reason"] == "outreach_disabled"

    print("\n✅ OFF switch correctly blocked outreach execution.\n")


def run_on_dry_run_test():
    print("\n=== 3E.5 ON DRY-RUN TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Outreach Enabled = ON\n"
    )

    runner = OutreachRunner()

    result = runner.run_outreach_cycle(
        fanvue_account_id=2,
        limit=1,
        dry_run=True,
    )

    print("\nON DRY-RUN RESULT:")
    print(result)

    assert result["success"] is True
    assert result["blocked"] is False
    assert result["status"] == "complete"
    assert result["dry_run"] is True
    assert result["reason"] == "dry_run_allowed"
    assert (
        result["execution_guard_result"]["reason"]
        == "dry_run_allowed"
    )

    print("\n✅ ON dry-run allowed outreach orchestration safely.\n")


def main():
    print("\n=== 3E.5 OUTREACH EXECUTION GUARD TEST ===\n")

    print(
        "Run this test twice:\n\n"
        "1) First with Outreach Enabled OFF\n"
        "   Expected: outreach_disabled\n\n"
        "2) Then with Outreach Enabled ON\n"
        "   Expected: dry_run_allowed\n"
    )

    choice = input(
        "Type OFF to run the OFF-switch test, "
        "or ON to run the dry-run test: "
    ).strip().upper()

    if choice == "OFF":
        run_off_switch_test()
    elif choice == "ON":
        run_on_dry_run_test()
    else:
        raise ValueError(
            "Invalid choice. Type OFF or ON."
        )

    print("\n=== 3E.5 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()