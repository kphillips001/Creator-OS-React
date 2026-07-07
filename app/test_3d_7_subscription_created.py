from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.7 SUBSCRIPTION CREATED TEST")
    print("======================================\n")

    service = RealtimeMonetizationEventService()

    test_event = {
        "external_event_id": (
            "test_subscription_3d_7_001"
        ),
        "event_type": "subscription_created",
        "fanvue_account_id": "test_creator_uuid",
        "fanvue_user_id": "test_user_uuid",
        "payload": {
            "data": {
                "subscription_type": "MONTHLY",
            }
        },
    }

    result = service.process_event(test_event)

    print("\nRESULT:")
    print(result)

    print(
        "\n✅ 3D.7 subscription created test complete"
    )


if __name__ == "__main__":
    run_test()