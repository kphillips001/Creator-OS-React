from app.services.fanvue_vault_assignment_service import FanvueVaultAssignmentService


def run_test():
    print("\n========================================")
    print("13D-2 TEST — VAULT ASSIGNMENT")
    print("========================================\n")

    service = FanvueVaultAssignmentService()

    test_cases = [
        {"intent": "teaser_image"},
        {"intent": "vip_image"},
        {"intent": "premium_image"},
        {"intent": "wall_image", "delivery": "post_now"},
        {"intent": "wall_image", "delivery": "scheduled"},
    ]

    for case in test_cases:
        intent = case["intent"]
        delivery = case.get("delivery")

        result = service.assign_destination(
            upload_intent=intent,
            delivery_method=delivery,
        )

        print(f"\nIntent: {intent} | Delivery: {delivery}")
        print(result)

    print("\n========================================")
    print("13D-2 TEST COMPLETE")
    print("========================================\n")


if __name__ == "__main__":
    run_test()