from app.services.qualification_escalation_service import (
    QualificationEscalationService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.2 ESCALATION SYNC TEST")
    print("======================================\n")

    service = QualificationEscalationService()

    result = service.process_successful_qualification_purchase(
        fanvue_user_id="test_user_uuid",
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.2 escalation sync works"
    )


if __name__ == "__main__":
    run_test()