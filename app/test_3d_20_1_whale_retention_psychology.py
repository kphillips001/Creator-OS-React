from app.services.whale_retention_psychology_service import (
    WhaleRetentionPsychologyService,
)


def print_header(title: str):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def print_result(result: dict):
    for key, value in result.items():
        print(f"{key}: {value}")


def main():
    service = WhaleRetentionPsychologyService()

    # --------------------------------------------------
    # TEST 1 — ACTIVE WHALE
    # --------------------------------------------------

    print_header(
        "TEST 1 — ACTIVE WHALE"
    )

    result = (
        service.build_retention_profile(
            buyer_memory={
                "buyer_tier": "WHALE",
                "is_whale": True,
                "total_spend": 2400,
                "purchase_count": 18,
                "total_tip_amount": 320,
            },
            conversation_state={
                "conversation_mode": "tension",
                "intent_score": 65,
                "sexual_engagement_only": False,
                "monetization_intent": True,
            },
            runtime_state={
                "premium_freshness_state": "fresh",
            },
        )
    )

    print_result(result)

    # --------------------------------------------------
    # TEST 2 — HIGH VALUE USER
    # --------------------------------------------------

    print_header(
        "TEST 2 — HIGH VALUE USER"
    )

    result = (
        service.build_retention_profile(
            buyer_memory={
                "buyer_tier": "HIGH_VALUE",
                "total_spend": 420,
                "purchase_count": 7,
                "total_tip_amount": 55,
            },
            conversation_state={
                "conversation_mode": "flirty",
                "intent_score": 45,
                "sexual_engagement_only": False,
                "monetization_intent": True,
            },
            runtime_state={
                "premium_freshness_state": "warm",
            },
        )
    )

    print_result(result)

    # --------------------------------------------------
    # TEST 3 — DORMANT WHALE
    # --------------------------------------------------

    print_header(
        "TEST 3 — DORMANT WHALE"
    )

    result = (
        service.build_retention_profile(
            buyer_memory={
                "buyer_tier": "WHALE",
                "is_whale": True,
                "total_spend": 3100,
                "purchase_count": 24,
            },
            conversation_state={
                "conversation_mode": "casual",
                "intent_score": 18,
                "sexual_engagement_only": False,
                "monetization_intent": False,
            },
            runtime_state={
                "premium_freshness_state": "cold",
                "dormant_whale": True,
            },
        )
    )

    print_result(result)

    # --------------------------------------------------
    # TEST 4 — EXPLICIT WITHOUT BUYING INTENT
    # --------------------------------------------------

    print_header(
        "TEST 4 — EXPLICIT WITHOUT BUYING INTENT"
    )

    result = (
        service.build_retention_profile(
            buyer_memory={
                "buyer_tier": "HIGH_VALUE",
                "total_spend": 800,
                "purchase_count": 11,
            },
            conversation_state={
                "conversation_mode": "tension",
                "intent_score": 28,
                "sexual_engagement_only": True,
                "monetization_intent": False,
            },
            runtime_state={
                "premium_freshness_state": "warm",
            },
        )
    )

    print_result(result)

    # --------------------------------------------------
    # TEST 5 — NON BUYER
    # --------------------------------------------------

    print_header(
        "TEST 5 — NON BUYER"
    )

    result = (
        service.build_retention_profile(
            buyer_memory={
                "buyer_tier": "NON_BUYER",
                "total_spend": 0,
                "purchase_count": 0,
            },
            conversation_state={
                "conversation_mode": "casual",
                "intent_score": 10,
                "sexual_engagement_only": False,
                "monetization_intent": False,
            },
            runtime_state={},
        )
    )

    print_result(result)

    print("\n")
    print("=" * 70)
    print("3D.20.1 TEST COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()