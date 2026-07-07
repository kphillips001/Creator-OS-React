from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.14 PRODUCTION VALIDATION")
    print("======================================\n")

    service = (
        RealtimeMonetizationEventService()
    )

    validation_events = [
        {
            "name": "PURCHASE EVENT",
            "event": {
                "event_type": "purchase_received",
                "fanvue_user_id": "buyer_001",
                "amount": 49,
            },
        },
        {
            "name": "TIP EVENT",
            "event": {
                "event_type": "tip_received",
                "fanvue_user_id": "tipper_001",
                "amount": 250,
            },
        },
        {
            "name": "SUBSCRIPTION EVENT",
            "event": {
                "event_type": "subscription_created",
                "fanvue_user_id": "sub_001",
            },
        },
        {
            "name": "UNKNOWN EVENT",
            "event": {
                "event_type": "weird_custom_event",
                "fanvue_user_id": "fan_unknown",
            },
        },
    ]

    results = []

    for item in validation_events:
        print(f"\nTEST — {item['name']}\n")

        result = (
            service.execute_realtime_reaction_pipeline(
                monetization_event=item["event"],
            )
        )

        print(result)

        results.append(result)

        assert result["success"] is True

    print("\nTEST — SESSION STATE\n")

    session_result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
                "fanvue_user_id": "fan_close",
                "amount": 99,
            },
            runtime_state={
                "close_flow_active": True,
            },
        )
    )

    print(session_result)

    assert (
        session_result["success"]
        is True
    )

    assert (
        session_result["session"][
            "success"
        ]
        is True
    )

    print("\nTEST — DUPLICATE STABILITY\n")

    duplicate_event = {
        "event_type": "purchase_received",
        "fanvue_user_id": "dup_user",
        "external_event_id": "evt_duplicate_001",
        "amount": 25,
    }

    first_result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event=duplicate_event,
        )
    )

    second_result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event=duplicate_event,
        )
    )

    print(first_result)
    print(second_result)

    assert (
        first_result["success"]
        is True
    )

    assert (
        second_result["success"]
        is True
    )

    assert (
        second_result["duplicate"][
            "duplicate"
        ]
        is False
    )

    print("\n======================================")
    print("✅ 3D.13.14 PASSED")
    print("======================================\n")


if __name__ == "__main__":
    run_test()