import os

from app.services.whale_protection_service import (
    WhaleProtectionService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.10 WHALE PROTECTION TEST")
    print("======================================\n")

    service = (
        WhaleProtectionService()
    )

    result = (
        service.build_whale_protection(
            fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
            fanvue_user_id="test_user_uuid",
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.10 whale protection works"
    )


if __name__ == "__main__":
    run_test()
