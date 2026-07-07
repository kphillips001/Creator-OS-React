from app.repositories.buyer_memory_sync_repository import (
    get_content_ownership_memory,
)


def run_test():
    print("\n==============================")
    print(" 3D.16.7 OWNERSHIP INTELLIGENCE")
    print("==============================\n")

    fanvue_user_id = "1"

    result = get_content_ownership_memory(
        fanvue_user_id
    )

    print("[OWNERSHIP MEMORY]")
    print(result)

    required_keys = [
        "owned_content_count",
        "owned_vip_count",
        "owned_premium_count",
        "last_owned_at",
        "recent_owned_content_tags",
        "collector_score",
        "repeat_purchase_score",
    ]

    for key in required_keys:
        assert key in result, f"Missing key: {key}"
        print(f"{key}: ✅")

    print("\n✅ 3D.16.7 TEST COMPLETE")
    print("Ownership intelligence memory signals are available.")


if __name__ == "__main__":
    run_test()