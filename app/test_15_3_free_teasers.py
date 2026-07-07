from app.main import decision_engine


def print_result(label, result):
    print(f"\n--- {label} RESULT ---")
    print("response:", result.get("response"))
    print("send_offer:", result.get("send_offer"))
    print("offer:", result.get("offer"))
    print("intent:", result.get("intent"))
    print("mode:", result.get("mode"))
    print("----------------------\n")


def run_test():
    print("\n=== 15.3 FREE TEASERS INTEGRATION TEST ===\n")

    engine = decision_engine

    # Use stable test users so memory/content usage behavior is repeatable.
    medium_user_id = "1:153"
    high_user_id = "1:154"

    # --------------------------------------------------
    # TEST 1 — Medium intent should route to TEASE/free warmup
    # --------------------------------------------------

    print("\n[TEST 1] Medium-intent user should receive TEASE/free teaser content\n")

    engine.memory.update_user_memory(
        medium_user_id,
        {
            "buyer_session_active": False,
            "buyer_session_step": 0,
            "buyer_session_last_action": None,
            "buyer_session_ppv_count": 0,
            "intent_score": 35,
            "buyer_tier": "warm",
            "conversation_mode": "flirty",
            "subscriber_engagement_mode": "flirty",
            "engagement_tier": "MEDIUM",
            "messages_since_last_offer": 5,
            "offer_state": None,
            "last_offer_type": None,
            "last_offer_timestamp": None,
            "last_offer_content_tag": None,
            "last_offer_price": None,
            "post_offer_nudge_count": 0,
            "last_nudge_timestamp": None,
            "last_nudge_type": None,
        },
    )

    medium_message = "I'm curious, what would you send me first?"

    medium_result = engine.process_message(
        user_id=medium_user_id,
        message=medium_message,
        chat_history=[],
    )

    print_result("MEDIUM INTENT / TEASER", medium_result)

    medium_offer = medium_result.get("offer", {}) or {}
    medium_content = medium_offer.get("content", {}) or {}

    print("[ASSERTIONS]")
    print("Expected offer_type: tease OR teaser")
    print("Actual offer_type:", medium_offer.get("offer_type"))
    print("Expected price: 0")
    print("Actual price:", medium_offer.get("price"))
    print("Expected is_free_teaser: True")
    print("Actual is_free_teaser:", medium_offer.get("is_free_teaser"))
    print("Selected content tag:", medium_content.get("tag"))
    print("Selected content tier:", medium_content.get("tier"))

    # --------------------------------------------------
    # TEST 2 — Same medium user again should trigger duplicate protection
    # --------------------------------------------------

    print("\n[TEST 2] Same user again should block duplicate teaser if same content is selected\n")

    duplicate_result = engine.process_message(
        user_id=medium_user_id,
        message=medium_message,
        chat_history=[],
    )

    print_result("DUPLICATE TEASER CHECK", duplicate_result)

    duplicate_offer = duplicate_result.get("offer", {}) or {}

    print("[ASSERTIONS]")
    print("Expected duplicate behavior: send_offer False OR different unused content")
    print("Actual send_offer:", duplicate_result.get("send_offer"))
    print("Actual offer_type:", duplicate_offer.get("offer_type"))
    print("Actual description:", duplicate_offer.get("description"))

    # --------------------------------------------------
    # TEST 3 — High intent should keep VIP/PREMIUM paid routing
    # --------------------------------------------------

    print("\n[TEST 3] High-intent user should keep VIP/PREMIUM paid content routing\n")

    engine.memory.update_user_memory(
        high_user_id,
        {
            "buyer_session_active": False,
            "buyer_session_step": 0,
            "buyer_session_last_action": None,
            "buyer_session_ppv_count": 0,
            "intent_score": 85,
            "buyer_tier": "hot",
            "conversation_mode": "tension",
            "subscriber_engagement_mode": "tension",
            "engagement_tier": "HIGH",
            "messages_since_last_offer": 5,
            "offer_state": None,
            "last_offer_type": None,
            "last_offer_timestamp": None,
            "last_offer_content_tag": None,
            "last_offer_price": None,
            "post_offer_nudge_count": 0,
            "last_nudge_timestamp": None,
            "last_nudge_type": None,
        },
    )

    high_message = "yeah I want the good stuff, send it"

    high_result = engine.process_message(
        user_id=high_user_id,
        message=high_message,
        chat_history=[],
    )

    print_result("HIGH INTENT / PAID PPV", high_result)

    high_offer = high_result.get("offer", {}) or {}
    high_content = high_offer.get("content", {}) or {}

    print("[ASSERTIONS]")
    print("Expected offer_type: vip OR premium")
    print("Actual offer_type:", high_offer.get("offer_type"))
    print("Expected price: greater than 0 if content exists")
    print("Actual price:", high_offer.get("price"))
    print("Expected is_free_teaser: False or missing")
    print("Actual is_free_teaser:", high_offer.get("is_free_teaser"))
    print("Selected content tag:", high_content.get("tag"))
    print("Selected content tier:", high_content.get("tier"))
    print("Selected content tag:", duplicate_result.get("offer", {}).get("content", {}).get("tag"))

    print("\n=== 15.3 FREE TEASERS TEST COMPLETE ===\n")


if __name__ == "__main__":
    run_test()