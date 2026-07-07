from app.services.offer_service import OfferService


def run_test():
    service = OfferService()

    print("\n===== STEP 6G TEST 1 — DEBUG LOGGING VISIBILITY =====\n")

    memory = {
        "intent_score": 65,
        "exclusive_interest_count": 2,
        "closing_questions_count": 0,
        "offers_shown_count": 1,
        "message_score": 20,
        "messages_since_last_offer": 1,
        "last_offer_type": "tease_offer",
        "intent_signals": [],
        "user_value_tier": "warm",
        "is_whale": False,
        "is_subscriber": True,
        "subscriber_profile": "ACTIVE_SUBSCRIBER",
        "subscriber_rewarm_required": False,
        "current_route": "chat",
    }

    result = service.determine_offer(
        intent_tier="medium",
        mode="tension",
        memory=memory,
    )

    print("\nFINAL RESULT:")
    print(result)
    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()