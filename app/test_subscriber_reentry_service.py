from datetime import datetime, timedelta, timezone

from app.services.subscriber_reentry_service import SubscriberReentryService


def run_test():
    service = SubscriberReentryService()

    print("\n===== SUBSCRIBER REENTRY SERVICE TEST =====\n")

    now = datetime.now(timezone.utc)

    test_cases = [
        {
            "label": "Recently active subscriber",
            "memory": {
                "last_active_at": now - timedelta(days=2),
                "last_subscriber_send_at": now - timedelta(days=3),
            },
        },
        {
            "label": "Re-entry subscriber",
            "memory": {
                "last_active_at": now - timedelta(days=8),
                "last_subscriber_send_at": now - timedelta(days=5),
            },
        },
        {
            "label": "Fatigue reset subscriber",
            "memory": {
                "last_active_at": now - timedelta(days=10),
                "last_subscriber_send_at": now - timedelta(days=15),
            },
        },
        {
            "label": "No dates available",
            "memory": {},
        },
    ]

    for test in test_cases:
        print(f"--- {test['label']} ---")
        result = service.process_reentry(
            fanvue_account_id=1,
            fanvue_user_id=1,
            user_memory=test["memory"],
        )       
        print(result)
        print("-" * 40)

    print("\n===== TEST COMPLETE =====\n")


if __name__ == "__main__":
    run_test()