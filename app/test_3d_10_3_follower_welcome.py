from app.services.follower_welcome_service import (
    FollowerWelcomeService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.3 FOLLOWER WELCOME TEST")
    print("======================================\n")

    service = FollowerWelcomeService()

    result = service.create_follower_welcome_offer(
        fanvue_user_id="new_follower_001",
        fanvue_account_id="test_creator_uuid",
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.3 follower qualification flow works"
    )


if __name__ == "__main__":
    run_test()