from app.services.ppv_targeting_service import PPVTargetingService


def run_test():
    print("\n=== TEST: Follower Monetization Targets ===\n")

    service = PPVTargetingService()

    results = service.get_follower_monetization_targets(
        fanvue_account_id=1  # 👈 change if needed
    )

    print(f"\nTotal Results: {len(results)}\n")

    for r in results:
        print(
            f"USER: {r['username']} | "
            f"tier: {r['user_value_tier']} | "
            f"attention: {r['attention_tier']} | "
            f"route: {r['current_route']} | "
            f"outreach: {r['outreach_status']}"
        )


if __name__ == "__main__":
    run_test()