from app.services.outreach_mass_ppv_coordination_service import (
    OutreachMassPPVCoordinationService,
)


def assert_equal(actual, expected, label):
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected}, got {actual}")


def main():
    print("\n=== SECTION 13 OUTREACH → MASS PPV COORDINATION TEST ===\n")

    service = OutreachMassPPVCoordinationService()

    ignored_user = {
        "fanvue_user_id": 101,
        "outreach_attempts": 3,
        "outreach_ignore_count": 3,
        "purchase_count": 0,
        "total_spend": 0,
        "user_value_tier": "low",
    }

    result = service.evaluate(ignored_user)
    print("Ignored user:", result)

    assert_equal(result["allow_outreach"], False, "ignored_user allow_outreach")
    assert_equal(result["allow_mass_ppv"], True, "ignored_user allow_mass_ppv")
    assert_equal(
        result["recommended_action"],
        "stop_outreach_keep_mass_ppv",
        "ignored_user action",
    )

    engaged_user = {
        "fanvue_user_id": 102,
        "outreach_attempts": 1,
        "outreach_ignore_count": 0,
        "outreach_response_count": 1,
        "purchase_count": 0,
        "total_spend": 0,
        "user_value_tier": "low",
    }

    result = service.evaluate(engaged_user)
    print("Engaged user:", result)

    assert_equal(result["allow_outreach"], True, "engaged_user allow_outreach")
    assert_equal(result["allow_mass_ppv"], True, "engaged_user allow_mass_ppv")
    assert_equal(result["mass_ppv_priority"], "boosted", "engaged_user ppv priority")

    time_waster = {
        "fanvue_user_id": 103,
        "outreach_attempts": 1,
        "outreach_ignore_count": 0,
        "inbound_message_count": 12,
        "ignored_offer_count": 2,
        "purchase_count": 0,
        "total_spend": 0,
        "user_value_tier": "low",
    }

    result = service.evaluate(time_waster)
    print("Time-waster:", result)

    assert_equal(result["allow_outreach"], False, "time_waster allow_outreach")
    assert_equal(result["allow_mass_ppv"], True, "time_waster allow_mass_ppv")
    assert_equal(
        result["recommended_action"],
        "throttle_chat_keep_mass_ppv",
        "time_waster action",
    )

    whale = {
        "fanvue_user_id": 104,
        "is_whale": True,
        "purchase_count": 10,
        "total_spend": 500,
    }

    result = service.evaluate(whale)
    print("Whale:", result)

    assert_equal(result["allow_outreach"], False, "whale allow_outreach")
    assert_equal(result["allow_mass_ppv"], False, "whale allow_mass_ppv")
    assert_equal(result["recommended_action"], "protect_user", "whale action")

    print("\n✅ SECTION 13 COORDINATION TEST PASSED\n")


if __name__ == "__main__":
    main()