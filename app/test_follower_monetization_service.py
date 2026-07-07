from app.services.follower_monetization_service import FollowerMonetizationService


def run_test():
    print("\n=== TEST: Follower Monetization Service ===\n")

    service = FollowerMonetizationService()

    results = service.run(
        fanvue_account_id=1,   # change if needed
        dry_run=False,
        limit=5,
    )

    print(f"Total Targets: {results['target_count']}")
    print(f"Sent Count: {results['sent_count']}")
    print(f"Skipped Count: {results['skipped_count']}\n")

    for target in results["targets"]:
        print(
            f"USER: {target.get('username')} | "
            f"outreach: {target.get('outreach_status')} | "
            f"tier: {target.get('user_value_tier')} | "
            f"offer_type: {target.get('offer_type')} | "
            f"content_tag: {target.get('content_tag')} | "
            f"status: {target.get('status')}"
        )


if __name__ == "__main__":
    run_test()
    