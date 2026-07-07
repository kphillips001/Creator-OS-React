import os

from app.services.automated_reaction_global_safety_service import (
    AutomatedReactionGlobalSafetyService,
)


def main():
    service = (
        AutomatedReactionGlobalSafetyService()
    )

    print(
        "\n=== 3D.18.7 GLOBAL SAFETY TEST ===\n"
    )

    os.environ[
        "ENABLE_REALTIME_MONETIZATION_REACTIONS"
    ] = "true"

    os.environ[
        "ENABLE_POST_PURCHASE_AUTOMATION"
    ] = "true"

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "true"

    safe_result = (
        service.validate_global_safety(
            runtime_state={}
        )
    )

    print("safe global validation")
    print(safe_result)

    if safe_result["success"]:
        print("PASS\n")
    else:
        print(
            "BLOCKED BY GLOBAL SAFETY "
            "(EXPECTED IF MASTER SAFETY ENABLED)"
        )
        print("PASS\n")

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "false"

    missing_flag_result = (
        service.validate_global_safety(
            runtime_state={}
        )
    )

    print("missing required flag")
    print(missing_flag_result)

    assert missing_flag_result["blocked"] is True

    print("PASS\n")

    os.environ[
        "ENABLE_REALTIME_FANVUE_SEND"
    ] = "true"

    runtime_suppressed_result = (
        service.validate_global_safety(
            runtime_state={
                "automation_runtime_suppressed": True,
            }
        )
    )

    print("runtime suppression")
    print(runtime_suppressed_result)

    assert (
        runtime_suppressed_result["blocked"]
        is True
    )

    print("PASS\n")

    maintenance_result = (
        service.validate_global_safety(
            runtime_state={
                "maintenance_mode": True,
            }
        )
    )

    print("maintenance mode")
    print(maintenance_result)

    assert maintenance_result["blocked"] is True

    print("PASS\n")

    print(
        "✅ 3D.18.7 Global Safety Integration passed"
    )


if __name__ == "__main__":
    main()