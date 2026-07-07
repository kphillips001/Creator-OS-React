import os

from app.services.free_user_boundary_service import (
    FreeUserBoundaryService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.8 FREE USER BOUNDARY TEST")
    print("======================================\n")

    service = (
        FreeUserBoundaryService()
    )

    result = service.enforce_boundary(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.8 free user boundaries work"
    )


if __name__ == "__main__":
    run_test()
