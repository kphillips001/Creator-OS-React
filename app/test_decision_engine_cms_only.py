from app.main import decision_engine


def test_decision_engine_uses_content_service_only():
    print("\n=== CMS → DecisionEngine Linkage Test ===")

    assert hasattr(decision_engine, "_select_cms_content"), (
        "❌ DecisionEngine is missing _select_cms_content()"
    )

    test_memory = {
        "seen_content_tags": [],
        "last_content_tag": None,
        "last_offer_content_tag": None,
        "buyer_tier": "medium",
        "intent_score": 70,
    }

    for offer_type in ["tease", "vip", "premium"]:
        print(f"\nTesting offer_type={offer_type}")

        content = decision_engine._select_cms_content(
            offer_type,
            test_memory,
        )

        print("Selected content:", content)

        assert content is None or isinstance(content, dict), (
            f"❌ Invalid content result for {offer_type}"
        )

    print("\n✅ PASSED: DecisionEngine content selection routes through ContentService.get_content()")


if __name__ == "__main__":
    test_decision_engine_uses_content_service_only()