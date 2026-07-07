from app.services.outreach_scheduler_service import (
    OutreachSchedulerService,
)


def main():

    print(
        "\n=== OUTREACH SCHEDULER SERVICE TEST ===\n"
    )

    service = (
        OutreachSchedulerService()
    )

    print(
        "[1] Scheduling outreach..."
    )

    result = service.schedule_outreach(
        fanvue_account_id=1,
        fanvue_user_id=1,
        outreach_type="reactivation",
    )

    print(result)
    print()

    print(
        "🚀 OUTREACH SCHEDULER SERVICE TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()