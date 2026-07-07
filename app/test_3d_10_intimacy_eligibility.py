import os

from app.services.intimacy_eligibility_service import (
    IntimacyEligibilityService,
)


def run_test():
    print("\n======================================")
    print(" 3D.10 INTIMACY ELIGIBILITY TEST")
    print("======================================\n")

    service = IntimacyEligibilityService()

    result = service.get_intimacy_profile(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nINTIMACY PROFILE RESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10 intimacy eligibility test complete"
    )


if __name__ == "__main__":
    run_test()
