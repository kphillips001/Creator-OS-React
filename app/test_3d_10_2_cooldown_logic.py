from app.services.qualification_cooldown_service import (
    QualificationCooldownService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.2 COOLDOWN LOGIC TEST")
    print("======================================\n")

    service = QualificationCooldownService()

    result = service.process_ignored_qualification_ppv(
        fanvue_user_id="test_user_uuid",
        qualification_event_id=1,
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.2 cooldown logic works"
    )


if __name__ == "__main__":
    run_test()