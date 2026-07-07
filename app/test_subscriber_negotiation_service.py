from app.services.subscriber_negotiation_service import SubscriberNegotiationService


def run_test():
    service = SubscriberNegotiationService()

    print("\n===== SUBSCRIBER NEGOTIATION SERVICE TEST =====\n")

    tests = [
        {
            "label": "No resistance",
            "memory": {
                "price_resistance_count": 0,
                "discount_used_flag": False,
            },
            "price": 30,
            "message": "send it",
        },
        {
            "label": "First resistance",
            "memory": {
                "price_resistance_count": 0,
                "discount_used_flag": False,
            },
            "price": 30,
            "message": "that's too expensive",
        },
        {
            "label": "Second resistance",
            "memory": {
                "price_resistance_count": 1,
                "discount_used_flag": False,
            },
            "price": 30,
            "message": "still too much",
        },
        {
            "label": "Third resistance",
            "memory": {
                "price_resistance_count": 2,
                "discount_used_flag": False,
            },
            "price": 30,
            "message": "can you go lower",
        },
        {
            "label": "Discount already used",
            "memory": {
                "price_resistance_count": 3,
                "discount_used_flag": True,
            },
            "price": 30,
            "message": "too expensive",
        },
    ]

    for test in tests:
        print(f"--- {test['label']} ---")
        result = service.get_negotiation_action(
            user_memory=test["memory"],
            offered_price=test["price"],
            user_message=test["message"],
        )
        print(result)
        print("-" * 40)

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()