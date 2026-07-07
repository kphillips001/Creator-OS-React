from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.1–3D.3 MONETIZATION EVENT TEST")
    print("======================================\n")

    service = RealtimeMonetizationEventService()

    test_event = {
        "external_event_id": "test_purchase_3d_004",
        "event_type": "purchase_received",
        "fanvue_account_id": "test_creator_uuid",
        "fanvue_user_id": "test_user_uuid",
        "payload": {
            "data": {
                "amount": 19.99,
                "currency": "USD",
                "content_tag": "VIP_TEST",
                "fanvue_media_uuid": "test_media_uuid",
                "purchase_type": "VIP",
            }
        },
    }

    result = service.process_event(test_event)

    print("\nRESULT:")
    print(result)

    print("\n✅ 3D.1–3D.3 test complete")


if __name__ == "__main__":
    run_test()