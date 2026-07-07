from datetime import datetime, timedelta
from app.services.subscriber_send_rules_service import SubscriberSendRulesService


def run_rule_tests(service):
    test_profiles = [
        "NEW_SUBSCRIBER",
        "ACTIVE_SUBSCRIBER",
        "LAPSED_SUBSCRIBER",
        "HIGH_VALUE_SUBSCRIBER",
        None,  # fallback test
    ]

    print("\n===== SUBSCRIBER SEND RULES TEST =====\n")

    for profile in test_profiles:
        user_memory = {
            "subscriber_profile": profile
        }

        rules = service.get_subscriber_send_rules(user_memory)

        print(f"PROFILE: {profile}")
        print("RULES:")
        for key, value in rules.items():
            print(f"  {key}: {value}")
        print("-" * 40)


def run_eligibility_tests(service):
    now = datetime.utcnow()

    test_cases = [
        {
            "name": "Eligible new subscriber",
            "user_memory": {
                "subscriber_profile": "NEW_SUBSCRIBER",
                "last_subscriber_send_at": None,
                "subscriber_send_count_24h": 0,
                "last_subscriber_content_tag": None,
            },
            "content_tag": "vip_tease_001",
        },
        {
            "name": "Blocked by cooldown",
            "user_memory": {
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "last_subscriber_send_at": (now - timedelta(hours=2)).isoformat(),
                "subscriber_send_count_24h": 0,
                "last_subscriber_content_tag": None,
            },
            "content_tag": "vip_tease_002",
        },
        {
            "name": "Blocked by max sends",
            "user_memory": {
                "subscriber_profile": "NEW_SUBSCRIBER",
                "last_subscriber_send_at": (now - timedelta(hours=30)).isoformat(),
                "subscriber_send_count_24h": 1,
                "last_subscriber_content_tag": None,
            },
            "content_tag": "vip_tease_003",
        },
        {
            "name": "Blocked by repeat content",
            "user_memory": {
                "subscriber_profile": "LAPSED_SUBSCRIBER",
                "last_subscriber_send_at": (now - timedelta(hours=72)).isoformat(),
                "subscriber_send_count_24h": 0,
                "last_subscriber_content_tag": "vip_tease_004",
            },
            "content_tag": "vip_tease_004",
        },
        {
            "name": "Eligible active subscriber",
            "user_memory": {
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "last_subscriber_send_at": (now - timedelta(hours=24)).isoformat(),
                "subscriber_send_count_24h": 1,
                "last_subscriber_content_tag": "vip_tease_old",
            },
            "content_tag": "vip_tease_new",
        },
    ]

    print("\n===== SUBSCRIBER ELIGIBILITY TEST =====\n")

    for case in test_cases:
        result = service.can_send_to_subscriber(
            user_memory=case["user_memory"],
            content_tag=case["content_tag"],
            now=now,
        )

        print(f"TEST: {case['name']}")
        print(f"RESULT: {result}")
        print("-" * 40)


def run_tests():
    service = SubscriberSendRulesService()
    run_rule_tests(service)
    run_eligibility_tests(service)
    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_tests()