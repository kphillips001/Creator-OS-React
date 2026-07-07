import os

from app.services.emotional_continuity_service import (
    EmotionalContinuityService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.13 EMOTIONAL CONTINUITY TEST")
    print("======================================\n")

    service = (
        EmotionalContinuityService()
    )

    result = (
        service.evaluate_continuity(
            fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
            fanvue_user_id="test_user_uuid",
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.13 emotional continuity works"
    )


if __name__ == "__main__":
    run_test()
