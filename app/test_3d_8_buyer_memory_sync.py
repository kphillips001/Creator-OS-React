from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.8 BUYER MEMORY SYNC TEST")
    print("======================================\n")

    service = RealtimeMonetizationEventService()

    test_event = {
        "external_event_id": (
            "test_memory_sync_3d_8_004"
        ),
        "event_type": "tip_received",
        "fanvue_account_id": "test_creator_uuid",
        "fanvue_user_id": "test_user_uuid",
        "payload": {
            "data": {
                "amount": 25.00,
                "currency": "USD",
                "purchase_type": "TIP",
            }
        },
    }

    result = service.process_event(test_event)

    print("\nRESULT:")
    print(result)

    print(
        "\n✅ 3D.8 buyer memory sync complete"
    )


if __name__ == "__main__":
    run_test()