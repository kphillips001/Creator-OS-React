from app.services.mass_ppv_send_service import MassPPVSendService


def run_test():
    service = MassPPVSendService()

    content_item = {
        "id": 1,
        "content_item_id": 1,
        "destination": "vip",
        "requested_delivery": "chat_ppv",
        "upload_status": "uploaded",
        "vault_folder_id": "VIP",
        "fanvue_media_uuid": "TEST-MEDIA-UUID",
        "fanvue_preview_media_uuid": "TEST-PREVIEW-UUID",
        "fanvue_full_media_uuid": "TEST-FULL-UUID",
        "classification": "VIP",
        "tier": "vip",
        "tag": "vip_test",
        "suggested_tags": ["lingerie", "bedroom", "tease"],
        "safe_summary": "A flirty VIP-style photo with a teasing bedroom vibe.",
        "price": 9.99,
    }
    targets = [
        {
            "fanvue_user": {
                "id": 1,
                "username": "follower_user",
                "fanvue_user_uuid": "TEST-FOLLOWER-UUID",
            },
            "memory": {
                "is_subscriber": False,
                "user_value_tier": "cold",
            },
        },
        {
            "fanvue_user": {
                "id": 2,
                "username": "low_value_sub",
                "fanvue_user_uuid": "TEST-LOW-SUB-UUID",
            },
            "memory": {
                "is_subscriber": True,
                "subscriber_profile": "ACTIVE_SUBSCRIBER",
                "intent_score": 10,
                "user_value_tier": "low",
            },
        },
        {
            "fanvue_user": {
                "id": 3,
                "username": "high_value_sub",
                "fanvue_user_uuid": "TEST-HIGH-SUB-UUID",
            },
            "memory": {
                "is_subscriber": True,
                "subscriber_profile": "HIGH_VALUE_SUBSCRIBER",
                "intent_score": 90,
                "user_value_tier": "high",
            },
        },
    ]

    result = service.send_mass_ppv_campaign(
        fanvue_account_id=1,
        targets=targets,
        content_item=content_item,
        caption="I saved this one for the ones who pay attention 😏",
        price=9.99,
        dry_run=True,
    )

    print("\n=== 15H-2 MASS PPV SEND TEST RESULT ===")
    print(result)


if __name__ == "__main__":
    run_test()