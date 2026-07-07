from app.services.outreach_service import OutreachService
from unittest.mock import patch

def run_test():
    service = OutreachService()

    user_memory = {
        "fanvue_account_id": 1,
        "fanvue_user_id": 999777,
        "username": "test_follower",
        "user_type": "follower",
        "relationship_status": "follower",
        "user_value_tier": "cold",
        "attention_tier": "medium",
        "outreach_attempts": 0,
        "outreach_ignore_count": 0,
        "outreach_response_count": 0,
        "outreach_status": "eligible",
        "is_subscriber": False,
        "is_whale": False,
        "offer_state": "none",
        "post_offer_nudge_count": 0,
        "last_nudge_timestamp": None,
        "last_outreach_at": None,
        "last_inbound_at": None,
        "last_content_sent_at": None,
    }

    print("\n========================================")
    print("13I.3A OUTREACH TEASE PREVIEW TEST")
    print("========================================\n")

    with patch("random.random", return_value=0.1):
        preview = service.build_outreach_preview(user_memory)

    print(preview)

    print("\n========================================")
    print("[DONE] Outreach tease preview test complete")
    print("========================================\n")


if __name__ == "__main__":
    run_test()