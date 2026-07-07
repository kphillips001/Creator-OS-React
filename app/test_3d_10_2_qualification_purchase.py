from app.services.qualification_ppv_service import (
    QualificationPPVService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.2 QUALIFICATION PURCHASE TEST")
    print("======================================\n")

    service = QualificationPPVService()

    result = service.process_qualification_purchase(
        qualification_event_id=1,
        purchase_event_id=999,
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.2 qualification purchase handling works"
    )


if __name__ == "__main__":
    run_test()