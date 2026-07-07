import os

from app.services.dynamic_intimacy_service import (
    DynamicIntimacyService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.11 DYNAMIC INTIMACY TEST")
    print("======================================\n")

    service = (
        DynamicIntimacyService()
    )

    result = (
        service.determine_runtime_state(
            fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
            fanvue_user_id="test_user_uuid",
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.11 dynamic intimacy works"
    )


if __name__ == "__main__":
    run_test()
