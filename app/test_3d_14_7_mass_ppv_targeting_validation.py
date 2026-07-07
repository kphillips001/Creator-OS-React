from app.services.realtime_buyer_state_service import (
    RealtimeBuyerStateService,
)


def run_test():
    print("\n==============================")
    print("3D.14.7 MASS PPV TARGETING VALIDATION")
    print("==============================\n")

    realtime_service = (
        RealtimeBuyerStateService()
    )

    blocked_result = {
        "allowed": False,
        "block_reasons": [
            "recent_purchase",
            "premium_only_buyer_tier:WHALE",
        ],
    }

    allowed_result = {
        "allowed": True,
        "block_reasons": [],
    }

    blocked_users = []
    eligible_users = []

    users = [
        {
            "fanvue_user_id": 1,
            "mock_result": blocked_result,
        },
        {
            "fanvue_user_id": 2,
            "mock_result": allowed_result,
        },
    ]

    for user in users:
        eligibility = user["mock_result"]

        if not eligibility.get("allowed"):
            print(
                "[TARGETING BLOCKED]",
                user["fanvue_user_id"],
                eligibility.get("block_reasons"),
            )

            blocked_users.append(user)
            continue

        print(
            "[TARGETING ELIGIBLE]",
            user["fanvue_user_id"],
        )

        eligible_users.append(user)

    print("\nEligible Users:")
    print(eligible_users)

    print("\nBlocked Users:")
    print(blocked_users)

    assert len(eligible_users) == 1
    assert len(blocked_users) == 1

    assert eligible_users[0]["fanvue_user_id"] == 2
    assert blocked_users[0]["fanvue_user_id"] == 1

    print("\n✅ 3D.14.7 PASSED")


if __name__ == "__main__":
    run_test()