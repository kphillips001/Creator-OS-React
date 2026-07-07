from datetime import (
    datetime,
    timedelta,
    UTC,
)

from app.services.wall_scheduler_service import (
    WallSchedulerService,
)


def main():

    print(
        "\n=== WALL SCHEDULER SERVICE TEST ===\n"
    )

    service = (
        WallSchedulerService()
    )

    # =====================================================
    # FIRST SCHEDULE
    # =====================================================

    print(
        "[1] Scheduling wall content..."
    )

    scheduled_for = (
        datetime.now(UTC)
        + timedelta(minutes=5)
    )

    result = service.schedule_wall_post(
        fanvue_account_id=1,
        content_item_id=9,
        scheduled_for=scheduled_for,
    )

    print(result)
    print()

    # =====================================================
    # DUPLICATE PROTECTION TEST
    # =====================================================

    print(
        "[2] Testing duplicate protection..."
    )

    duplicate_result = (
        service.schedule_wall_post(
            fanvue_account_id=1,
            content_item_id=9,
            scheduled_for=scheduled_for,
        )
    )

    print(duplicate_result)
    print()

    print(
        "🚀 WALL SCHEDULER SERVICE TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()