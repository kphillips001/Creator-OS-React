from app.services.fan_insights_sync_service import FanInsightsSyncService


def run_test():
    service = FanInsightsSyncService()

    test_users = [
        {
            "label": "Non Buyer",
            "user_id": 1001,
            "data": {
                "total_spend": 0,
                "purchase_count": 0,
                "is_top_spender": False,
            },
        },
        {
            "label": "Low Spender",
            "user_id": 1002,
            "data": {
                "total_spend": 9.99,
                "purchase_count": 1,
                "is_top_spender": False,
            },
        },
        {
            "label": "Active Buyer",
            "user_id": 1003,
            "data": {
                "total_spend": 40,
                "purchase_count": 2,
                "is_top_spender": False,
            },
        },
        {
            "label": "Whale",
            "user_id": 1004,
            "data": {
                "total_spend": 600,
                "purchase_count": 10,
                "is_top_spender": False,
            },
        },
    ]

    for user in test_users:
        print(f"\n=== TEST: {user['label']} ===")

        result = service.sync_user_insights(
            fanvue_account_id=1,
            fanvue_user_uuid=user["user_id"],  # ← matches DB BIGINT
            mock_data=user["data"],
        )

        print(result)


if __name__ == "__main__":
    run_test()