from app.services.buyer_classification_service import BuyerClassificationService


def run_test():
    service = BuyerClassificationService()

    test_cases = [
        {
            "label": "Non Buyer",
            "total_spend": 0,
            "purchase_count": 0,
            "is_top_spender": False,
        },
        {
            "label": "Low Spender",
            "total_spend": 9.99,
            "purchase_count": 1,
            "is_top_spender": False,
        },
        {
            "label": "Active Buyer",
            "total_spend": 35.00,
            "purchase_count": 2,
            "is_top_spender": False,
        },
        {
            "label": "High Value",
            "total_spend": 175.00,
            "purchase_count": 5,
            "is_top_spender": False,
        },
        {
            "label": "Whale",
            "total_spend": 650.00,
            "purchase_count": 12,
            "is_top_spender": False,
        },
        {
            "label": "Top Spender Override",
            "total_spend": 80.00,
            "purchase_count": 3,
            "is_top_spender": True,
        },
    ]

    for case in test_cases:
        print(f"\n=== {case['label']} ===")

        result = service.classify_buyer(
            total_spend=case["total_spend"],
            purchase_count=case["purchase_count"],
            is_top_spender=case["is_top_spender"],
        )

        print(result)


if __name__ == "__main__":
    run_test()