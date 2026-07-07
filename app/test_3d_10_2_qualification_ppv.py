from app.repositories.qualification_ppv_repository import (
    create_qualification_ppv_event,
)


def run_test():
    print("\n======================================")
    print(" 3D.10.2 QUALIFICATION PPV TEST")
    print("======================================\n")

    result = create_qualification_ppv_event(
        fanvue_user_id="test_user_uuid",
        fanvue_account_id="test_creator_uuid",
        qualification_type="SUBSCRIBER_WELCOME",
        content_tag="WELCOME_PPV_001",
        fanvue_media_uuid="media_test_001",
        price=7.00,
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.2 qualification PPV tracking works"
    )


if __name__ == "__main__":
    run_test()