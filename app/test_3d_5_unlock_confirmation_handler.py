from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.5 UNLOCK CONFIRMATION TEST")
    print("======================================\n")

    service = RealtimeMonetizationEventService()

    test_event = {
        "external_event_id": (
            "test_unlock_3d_5_004"
        ),
        "event_type": "unlock_confirmation",
        "fanvue_account_id": (
            "test_creator_uuid"
        ),
        "fanvue_user_id": "test_user_uuid",
        "payload": {
            "data": {
                "amount": 19.99,
                "currency": "USD",
                "content_tag": (
                    "PREMIUM_UNLOCK_TEST"
                ),
                "fanvue_media_uuid": (
                    "unlock_media_uuid_001"
                ),
                "purchase_type": "PREMIUM",
            }
        },
    }

    result = service.process_event(test_event)

    print("\nRESULT:")
    print(result)

    print(
        "\n✅ 3D.5 unlock handler test complete"
    )


if __name__ == "__main__":
    run_test()