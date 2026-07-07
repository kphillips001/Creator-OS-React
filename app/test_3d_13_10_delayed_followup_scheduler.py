from datetime import datetime, timedelta

from app.services.delayed_followup_scheduler_service import (
    DelayedFollowupSchedulerService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.10 DELAYED FOLLOWUP SCHEDULER")
    print("======================================\n")

    service = (
        DelayedFollowupSchedulerService()
    )

    execute_at = (
        datetime.utcnow()
        + timedelta(minutes=60)
    ).isoformat()

    print("TEST 1 — STANDARD SCHEDULE\n")

    result = (
        service.build_scheduled_followup(
            queue_payload={
                "fanvue_user_id": "fan_123",
                "execute_at": execute_at,
                "followup_type": (
                    "premium_reengagement"
                ),
            }
        )
    )

    print(result)

    assert result["success"] is True

    assert (
        result["status"]
        == "scheduled"
    )

    assert result["retry_count"] == 0

    print("\nTEST 2 — UUID GENERATED\n")

    assert result["scheduler_id"]

    print(result["scheduler_id"])

    print("\nTEST 3 — EXECUTION LOCK\n")

    assert (
        result["execution_locked"]
        is False
    )

    print("\nTEST 4 — WORKER CLAIM\n")

    assert (
        result["worker_claimed"]
        is False
    )

    print("\nTEST 5 — MISSING PAYLOAD\n")

    result = (
        service.build_scheduled_followup(
            queue_payload={}
        )
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_queue_payload"
    )

    print(
        "\n✅ 3D.13.10 PASSED"
    )


if __name__ == "__main__":
    run_test()