from app.services.realtime_monetization_event_service import (
    RealtimeMonetizationEventService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.12 REALTIME EVENT WIRING")
    print("======================================\n")

    service = (
        RealtimeMonetizationEventService()
    )

    result = (
        service.execute_realtime_reaction_pipeline(
            monetization_event={
                "event_type": "purchase_received",
                "fanvue_user_id": "fan_123",
                "fanvue_account_id": (
                    "acct_456"
                ),
                "amount": 49.99,
            }
        )
    )

    print(result)

    assert result["success"] is True

    assert "decision" in result

    assert "execution_plan" in result

    assert "reaction_payload" in result

    assert "outbound" in result

    assert "scheduled_followup" in result

    print(
        "\n✅ 3D.13.12 PASSED"
    )


if __name__ == "__main__":
    run_test()