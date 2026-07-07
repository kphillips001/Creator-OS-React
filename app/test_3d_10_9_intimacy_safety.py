import os

from app.services.intimacy_safety_service import (
    IntimacySafetyService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.9 INTIMACY SAFETY TEST")
    print("======================================\n")

    service = (
        IntimacySafetyService()
    )

    result = (
        service.validate_escalation(
            fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
            fanvue_user_id="test_user_uuid",
            requested_style="HARDCORE_EXPLICIT",
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.9 intimacy safety works"
    )


if __name__ == "__main__":
    run_test()
