from app.services.fanvue_outbound_reaction_service import (
    FanvueOutboundReactionService,
)


def run_test():
    print("\n======================================")
    print(" 3D.13.11 FANVUE OUTBOUND INTEGRATION")
    print("======================================\n")

    service = (
        FanvueOutboundReactionService()
    )

    print("TEST 1 — THANK YOU PAYLOAD\n")

    result = (
        service.build_outbound_reaction(
            reaction_payload={
                "fanvue_user_id": "fan_123",
                "payload_type": (
                    "thank_you_message"
                ),
                "requires_gpt_generation": True,
                "queue_for_delivery": True,
            }
        )
    )

    print(result)

    assert result["success"] is True

    assert (
        result["delivery_status"]
        == "prepared"
    )

    print("\nTEST 2 — UUID GENERATED\n")

    assert result["outbound_id"]

    print(result["outbound_id"])

    print("\nTEST 3 — DELIVERY ATTEMPTS\n")

    assert (
        result["delivery_attempts"]
        == 0
    )

    assert (
        result["max_delivery_attempts"]
        == 3
    )

    print("\nTEST 4 — WORKER CLAIM\n")

    assert (
        result["worker_claimed"]
        is False
    )

    print("\nTEST 5 — MISSING PAYLOAD\n")

    result = (
        service.build_outbound_reaction(
            reaction_payload={}
        )
    )

    print(result)

    assert result["success"] is False

    assert (
        result["reason"]
        == "missing_reaction_payload"
    )

    print(
        "\n✅ 3D.13.11 PASSED"
    )


if __name__ == "__main__":
    run_test()