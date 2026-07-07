import os

from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.5 INTIMACY PROFILE TEST")
    print("======================================\n")

    service = IntimacyProfileService()

    result = service.build_profile(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.5 intimacy profile works"
    )


if __name__ == "__main__":
    run_test()
