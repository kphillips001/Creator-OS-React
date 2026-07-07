from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.13 STRESS EDGE VALIDATION")
    print("======================================\n")

    service = (
        RealtimeMonetizationEventService()
    )

    print("TEST 1 — MISSING EVENT\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event=None,
        )
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_monetization_event"
    )

    print("\nTEST 2 — EMPTY EVENT\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={},
        )
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_monetization_event"
    )

    print("\nTEST 3 — MISSING USER\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
            },
        )
    )

    print(result)

    assert result["success"] is False

    print("\nTEST 4 — TIP EVENT\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": "tip_received",
                "fanvue_user_id": "tipper_123",
                "amount": 250,
            },
        )
    )

    print(result)

    assert result["success"] is True

    assert (
        result["reaction_payload"][
            "payload_type"
        ]
        == "tip_reward"
    )

    print("\nTEST 5 — SUBSCRIPTION EVENT\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": (
                    "subscription_created"
                ),
                "fanvue_user_id": "sub_123",
            },
        )
    )

    print(result)

    assert result["success"] is True

    assert (
        result["reaction_payload"][
            "payload_type"
        ]
        == "subscriber_welcome"
    )

    print("\nTEST 6 — LARGE PURCHASE\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": (
                    "purchase_received"
                ),
                "fanvue_user_id": "whale_999",
                "amount": 5000,
            },
        )
    )

    print(result)

    assert result["success"] is True

    print("\nTEST 7 — RANDOM EVENT TYPE\n")

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": (
                    "strange_unknown_event"
                ),
                "fanvue_user_id": "fan_123",
            },
        )
    )

    print(result)

    assert result["success"] is True

    print("\nTEST 8 — SESSION STATE\n")

    result = (
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

    print(result)

    assert "session" in result

    print(
        "\n✅ 3D.13.13 PASSED"
    )


if __name__ == "__main__":
    run_test()