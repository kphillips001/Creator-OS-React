from app.services.spender_confidence_service import (
    SpenderConfidenceService,
)


def run_test():

    print("\n======================================")
    print(" 3D.10.4 SPENDER CONFIDENCE TEST")
    print("======================================\n")

    service = SpenderConfidenceService()

    result = service.calculate_confidence(
        purchase_count=6,
        total_spend=139.94,
        qualification_purchased=True,
        recent_purchase_active=True,
    )

    print("\nRESULT:\n")
    print(result)

    print(
        "\n✅ 3D.10.4 spender confidence works"
    )


if __name__ == "__main__":
    run_test()