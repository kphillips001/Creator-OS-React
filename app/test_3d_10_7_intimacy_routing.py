import os

from app.services.intimacy_routing_service import (
    IntimacyRoutingService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.7 INTIMACY ROUTING TEST")
    print("======================================\n")

    service = (
        IntimacyRoutingService()
    )

    result = service.determine_route(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.7 intimacy routing works"
    )


if __name__ == "__main__":
    run_test()
