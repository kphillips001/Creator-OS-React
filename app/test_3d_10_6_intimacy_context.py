import os

from app.services.intimacy_context_service import (
    IntimacyContextService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.6 INTIMACY CONTEXT TEST")
    print("======================================\n")

    service = IntimacyContextService()

    result = service.build_gpt_context(
        fanvue_account_id=int(os.environ["TEST_FANVUE_ACCOUNT_ID"]),
        fanvue_user_id="test_user_uuid",
    )

    print("\nGPT CONTEXT:\n")
    print(result["gpt_context"])

    print(
        "\n✅ 3D.10.6 GPT intimacy context works"
    )


if __name__ == "__main__":
    run_test()
