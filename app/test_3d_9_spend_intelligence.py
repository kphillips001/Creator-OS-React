import os

from app.services.spend_intelligence_service import (
    SpendIntelligenceService,
)


def run_test():
    print("\n======================================")
    print(" 3D.9 SPEND INTELLIGENCE TEST")
    print("======================================\n")

    service = SpendIntelligenceService()

    result = service.get_spend_intelligence(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nSPEND INTELLIGENCE RESULT:\n")
    print(result)

    print(
        "\n✅ 3D.9 spend intelligence test complete"
    )


if __name__ == "__main__":
    run_test()
