from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


def run_global_override_test():
    print("\n=== 3E.11.4 GLOBAL OVERRIDE TEST ===\n")

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = OFF\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- ALL module switches = ON\n"
    )

    service = GlobalSendExecutionGuardService()

    result = service.validate_execution(
        execution_type="master_override_test",
        dry_run=True,
    )

    print("\nRESULT:")
    print(result)

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert result["reason"] == "global_automation_disabled"

    print(
        "\n✅ Master override correctly blocked ALL execution.\n"
    )


def main():
    run_global_override_test()

    print("\n=== 3E.11.4 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()