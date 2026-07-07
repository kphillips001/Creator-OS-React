from app.services.global_send_execution_guard_service import (
    GlobalSendExecutionGuardService,
)


def run_global_automation_off_test():
    print("\n=== 3E.11.1 GLOBAL AUTOMATION OFF TEST ===\n")

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = OFF\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
    )

    service = GlobalSendExecutionGuardService()

    result = service.validate_execution(
        execution_type="global_automation_off_test",
        dry_run=True,
    )

    print("\nRESULT:")
    print(result)

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert result["reason"] == "global_automation_disabled"

    print("\n✅ Global automation OFF correctly blocked execution.\n")


def run_manual_pause_test():
    print("\n=== 3E.11.2 MANUAL PAUSE TEST ===\n")

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = ON\n"
    )

    service = GlobalSendExecutionGuardService()

    result = service.validate_execution(
        execution_type="manual_pause_test",
        dry_run=True,
    )

    print("\nRESULT:")
    print(result)

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert result["reason"] == "manual_pause_enabled"

    print("\n✅ Manual pause correctly blocked execution.\n")


def run_global_live_sends_off_test():
    print("\n=== 3E.11.3 GLOBAL LIVE SENDS OFF TEST ===\n")

    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = OFF\n"
        "- Manual Pause Enabled = OFF\n"
    )

    service = GlobalSendExecutionGuardService()

    result = service.validate_execution(
        execution_type="global_live_sends_off_test",
        dry_run=True,
    )

    print("\nRESULT:")
    print(result)

    assert result["allowed"] is False
    assert result["blocked"] is True
    assert result["reason"] == "global_sends_disabled"

    print("\n✅ Global live sends OFF correctly blocked execution.\n")


def main():
    print("\n=== 3E.11 EMERGENCY SHUTDOWN LAYER TEST ===\n")

    print(
        "Choose test:\n\n"
        "OFF   = Global Automation Enabled OFF\n"
        "PAUSE = Manual Pause Enabled ON\n"
        "LIVE  = Global Live Sends Enabled OFF\n"
    )

    choice = input(
        "Type OFF, PAUSE, or LIVE: "
    ).strip().upper()

    if choice == "OFF":
        run_global_automation_off_test()
    elif choice == "PAUSE":
        run_manual_pause_test()
    elif choice == "LIVE":
        run_global_live_sends_off_test()
    else:
        raise ValueError("Invalid choice. Type OFF, PAUSE, or LIVE.")

    print("\n=== 3E.11 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()