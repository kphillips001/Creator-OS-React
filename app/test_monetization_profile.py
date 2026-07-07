from datetime import datetime, timezone, timedelta

from app.services.monetization_profile_service import MonetizationProfileService


service = MonetizationProfileService()

test_users = [
    {
        "name": "low probability user",
        "data": {
            "purchase_count": 0,
            "total_spent_cents": 0,
            "content_send_count": 6,
            "outreach_response_count": 0,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=10),
            "is_whale": False,
        },
    },
    {
        "name": "potential buyer user",
        "data": {
            "purchase_count": 0,
            "total_spent_cents": 0,
            "content_send_count": 1,
            "outreach_response_count": 1,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=1),
            "is_whale": False,
        },
    },
    {
        "name": "active buyer user",
        "data": {
            "purchase_count": 2,
            "total_spent_cents": 5000,
            "content_send_count": 2,
            "outreach_response_count": 0,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=1),
            "is_whale": False,
        },
    },
    {
        "name": "high value user",
        "data": {
            "purchase_count": 5,
            "total_spent_cents": 15000,
            "content_send_count": 2,
            "outreach_response_count": 0,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=1),
            "is_whale": False,
        },
    },
    {
        "name": "whale excluded user",
        "data": {
            "purchase_count": 10,
            "total_spent_cents": 50000,
            "content_send_count": 1,
            "outreach_response_count": 0,
            "last_active_at": datetime.now(timezone.utc) - timedelta(days=1),
            "is_whale": True,
        },
    },
]

for user in test_users:
    profile = service.get_profile(user["data"])
    print(f'{user["name"]}: {profile}')