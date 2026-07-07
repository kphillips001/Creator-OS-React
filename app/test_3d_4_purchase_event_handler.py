from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.4 PURCHASE EVENT HANDLER TEST")
    print("======================================\n")

    service = RealtimeMonetizationEventService()

    test_event = {
        "external_event_id": "test_purchase_3d_4_003",
        "event_type": "purchase_received",
        "fanvue_account_id": "test_creator_uuid",
        "fanvue_user_id": "test_user_uuid",
        "payload": {
            "data": {
                "amount": 29.99,
                "currency": "USD",
                "content_tag": "VIP_PURCHASE_TEST",
                "fanvue_media_uuid": "test_purchase_media_uuid",
                "purchase_type": "VIP",
            }
        },
    }

    result = service.process_event(test_event)

    print("\nRESULT:")
    print(result)

    print("\n✅ 3D.4 purchase event handler test complete")


if __name__ == "__main__":
    run_test()