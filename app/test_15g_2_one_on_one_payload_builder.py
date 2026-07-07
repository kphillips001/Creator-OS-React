from app.services.one_on_one_ppv_send_service import OneOnOnePPVSendService


def run_test():
    service = OneOnOnePPVSendService()

    test_content_item = {
        "id": 1,
        "classification": "VIP",
        "tier": "vip",
        "suggested_tags": ["lingerie", "bedroom", "tease"],
        "safe_summary": "A flirty VIP-style photo with a teasing bedroom vibe.",
        "fanvue_media_preview_uuid": "TEST-PREVIEW-UUID",
        "fanvue_media_full_uuid": "TEST-FULL-UUID",
    }

    result = service.send_ppv_to_user(
        fanvue_account_id=1,
        fanvue_user_uuid="TEST-FANVUE-USER-UUID",
        thread_id="1",
        content_item=test_content_item,
        price=9.99,
        dry_run=True,  # 🔥 keep TRUE for now
    )

    print("\n=== 15G-2 ONE-ON-ONE PPV RESULT ===")
    print(result)


if __name__ == "__main__":
    run_test()