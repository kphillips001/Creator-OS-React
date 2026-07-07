import os

from app.services.buyer_momentum_service import (
    BuyerMomentumService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.12 BUYER MOMENTUM TEST")
    print("======================================\n")

    service = (
        BuyerMomentumService()
    )

    result = (
        service.calculate_momentum(
            fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
            fanvue_user_id="test_user_uuid",
        )
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.12 buyer momentum works"
    )


if __name__ == "__main__":
    run_test()
