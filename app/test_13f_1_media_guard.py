from app.services.content_media_delivery_service import ContentMediaDeliveryService


def run_test():
    print("\n======================================")
    print("13F-1 TEST — MEDIA FETCH + DELIVERY GUARD")
    print("======================================\n")

    service = ContentMediaDeliveryService()

    fanvue_account_id = 1

    test_cases = [
        {
            "destination": "wall",
            "requested_delivery": "wall_post",
            "expected": "allowed",
        },
        {
            "destination": "wall",
            "requested_delivery": "chat_ppv",
            "expected": "blocked",
        },
        {
            "destination": "teaser",
            "requested_delivery": "chat_teaser",
            "expected": "allowed",
        },
        {
            "destination": "teaser",
            "requested_delivery": "chat_ppv",
            "expected": "blocked",
        },
        {
            "destination": "vip",
            "requested_delivery": "chat_ppv",
            "expected": "allowed",
        },
        {
            "destination": "premium",
            "requested_delivery": "chat_ppv",
            "expected": "allowed",
        },
        {
            "destination": "premium",
            "requested_delivery": "wall_post",
            "expected": "blocked",
        },
    ]

    for case in test_cases:
        print("\n--------------------------------------")
        print(f"CASE: {case}")
        print("--------------------------------------")

        result = service.get_media_for_delivery(
            fanvue_account_id=fanvue_account_id,
            destination=case["destination"],
            requested_delivery=case["requested_delivery"],
            limit=5,
        )

        print("success:", result.get("success"))
        print("safe media count:", result.get("count"))
        print("blocked count:", len(result.get("blocked", [])))

        for media in result.get("media", []):
            print("\nSAFE MEDIA:")
            print("content_item_id:", media.get("content_item_id"))
            print("destination:", media.get("destination"))
            print("vault_folder_id:", media.get("vault_folder_id"))
            print("preview_uuid:", media.get("fanvue_preview_media_uuid"))
            print("full_uuid:", media.get("fanvue_full_media_uuid"))

        for blocked in result.get("blocked", []):
            print("\nBLOCKED MEDIA:")
            print(blocked)

    print("\n======================================")
    print("13F-1 TEST COMPLETE")
    print("======================================\n")


if __name__ == "__main__":
    run_test()