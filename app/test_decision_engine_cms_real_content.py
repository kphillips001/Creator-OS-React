from app.main import decision_engine


def test_decision_engine_returns_real_cms_content():
    print("\n=== CMS → REAL CONTENT TEST ===")

    # 🔥 USE REAL VALUES FROM YOUR DB
    fanvue_account_id = 1
    fanvue_user_id = 1

    test_memory = {
        "fanvue_account_id": fanvue_account_id,
        "fanvue_user_id": fanvue_user_id,

        "seen_content_tags": [],
        "last_content_tag": None,
        "last_offer_content_tag": None,

        "buyer_tier": "medium",
        "intent_score": 75,
    }

    for offer_type in ["tease", "vip", "premium"]:
        print(f"\nTesting offer_type={offer_type}")

        content = decision_engine._select_cms_content(
            offer_type,
            test_memory,
        )

        print("Selected content:", content)

        assert content is not None, f"❌ No content returned for {offer_type}"
        assert isinstance(content, dict), f"❌ Invalid content format for {offer_type}"

        assert content.get("tag") is not None, "❌ Missing content tag"
        assert content.get("type") is not None, "❌ Missing content type"

    print("\n✅ PASSED: CMS is returning real content correctly")

if __name__ == "__main__":
        test_decision_engine_returns_real_cms_content()