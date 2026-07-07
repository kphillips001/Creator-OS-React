import os

from app.services.automated_reaction_execution_mode_service import (
    AutomatedReactionExecutionModeService,
)


def main():
    service = (
        AutomatedReactionExecutionModeService()
    )

    print(
        "\n=== 3D.18.8 EXECUTION MODE TEST ===\n"
    )

    runtime_dry_run = (
        service.determine_execution_mode(
            runtime_state={
                "force_dry_run_mode": True,
            }
        )
    )

    print("runtime forced dry run")
    print(runtime_dry_run)

    assert runtime_dry_run["success"] is True
    assert runtime_dry_run["dry_run"] is True
    assert (
        runtime_dry_run["execution_mode"]
        == "dry_run"
    )

    print("PASS\n")

    runtime_blocked = (
        service.determine_execution_mode(
            runtime_state={
                "disable_all_reactions": True,
            }
        )
    )

    print("runtime blocked")
    print(runtime_blocked)

    assert runtime_blocked["blocked"] is True
    assert (
        runtime_blocked["execution_mode"]
        == "blocked"
    )

    print("PASS\n")

    os.environ[
        "ENABLE_REALTIME_MONETIZATION_REACTIONS"
    ] = "true"

    os.environ[
        "ENABLE_POST_PURCHASE_AUTOMATION"
    ] = "true"

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "false"

    env_dry_run = (
        service.determine_execution_mode()
    )

    print("env dry run")
    print(env_dry_run)

    assert env_dry_run["success"] is True
    assert env_dry_run["dry_run"] is True

    print("PASS\n")

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "true"

    live_send_result = (
        service.determine_execution_mode()
    )

    print("live send mode")
    print(live_send_result)

    assert live_send_result["success"] is True
    assert (
        live_send_result[
            "live_send_allowed"
        ]
        is True
    )

    assert (
        live_send_result[
            "execution_mode"
        ]
        == "live_send"
    )

    print("PASS\n")

    print(
        "✅ 3D.18.8 Execution Mode Service passed"
    )


if __name__ == "__main__":
    main()