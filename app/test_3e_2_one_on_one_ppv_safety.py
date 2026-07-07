from app.services.one_on_one_ppv_send_service import (
    OneOnOnePPVSendService,
)

import app.services.one_on_one_ppv_send_service as ppv_module


def fake_get_user_memory_row(
    fanvue_account_id,
    fanvue_user_id,
):
    return {
        "user_value_tier": "medium",
        "is_whale": False,
        "avg_ppv_spend": 19.99,
        "ppv_purchase_count": 2,
        "buyer_session_active": False,
        "buyer_session_step": 1,
        "buyer_session_ppv_count": 0,
    }


def fake_update_memory_fields(
    fanvue_account_id,
    fanvue_user_id,
    data,
):
    print("[FAKE MEMORY UPDATE]", data)
    return True


def main():
    print("\n==============================")
    print("3E.2 ONE-ON-ONE PPV SAFETY TEST")
    print("==============================\n")

    # Patch DB functions so this test is safe and isolated.
    ppv_module.get_user_memory_row = fake_get_user_memory_row
    ppv_module.update_memory_fields = fake_update_memory_fields

    service = OneOnOnePPVSendService()

    # Patch expensive/external dependencies.
    service.context_builder.build_context = lambda thread_id, limit=20: [
        {"role": "user", "content": "what do you have for me?"},
        {"role": "assistant", "content": "maybe something special 😏"},
    ]

    service.hot_buyer_service.is_hot_buyer = lambda **kwargs: {
        "is_hot": False,
        "reason": "test_safe_default",
    }

    service.buyer_session_service.get_session_offer_tier = lambda memory: {
        "classification": "VIP",
        "price_multiplier": 1.0,
        "caption_tone": "flirty",
    }

    service.caption_service.generate_context_aware_caption = (
        lambda chat_history, content_metadata: "A little something just for you 😏"
    )

    service.content_guard.can_deliver_content = lambda **kwargs: {
        "allowed": True,
        "reason": "test_content_guard_allowed",
    }

    service.payload_builder.build_paid_ppv_payload = lambda *args, **kwargs: {
        "recipientUserId": "TEST-USER-UUID",
        "message": "A little something just for you 😏",
        "price": 19.99,
        "media": ["TEST-MEDIA-UUID"],
    }

    def fake_send_chat_message(
        user_uuid,
        payload,
    ):
        print("[ERROR] LIVE SEND SHOULD NOT BE CALLED IN THIS TEST")
        return {
            "success": False,
            "reason": "live_send_called_unexpectedly",
        }

    service.fanvue_api.send_chat_message = fake_send_chat_message

    safety_result = service.global_safety.can_send_monetization()

    print("[CURRENT MONETIZATION SAFETY STATE]")
    print(safety_result)

    content_item = {
        "id": 999,
        "classification": "VIP",
        "content_tier": "VIP",
        "distribution_type": "one_on_one",
        "destination": "VIP",
        "upload_status": "uploaded",
        "fanvue_media_uuid": "TEST-MEDIA-UUID",
        "fanvue_preview_media_uuid": "TEST-PREVIEW-UUID",
        "fanvue_full_media_uuid": "TEST-FULL-UUID",
        "tag": "TEST_VIP_TAG",
        "summary": "Test VIP content",
    }

    # If PPV/module/global safety is OFF, verify dry_run=False is blocked
    # BEFORE any live send can happen.
    if not safety_result.get("allowed"):
        print("\n[TEST MODE]")
        print("Safety is currently BLOCKED.")
        print("Testing dry_run=False hard block...\n")

        result = service.send_ppv_to_user(
            fanvue_account_id=1,
            fanvue_user_uuid="TEST-USER-UUID",
            thread_id="TEST-THREAD-ID",
            content_item=content_item,
            price=19.99,
            dry_run=False,
        )

        print("\n[RESULT]")
        print(result)

        assert result.get("blocked") is True
        assert result.get("success") is False
        assert result.get("reason") is not None

        print("\n✅ PASS")
        print("One-on-one PPV was blocked by safety/module controls.")
        print("No live send occurred.")

        return

    # If PPV/module/global safety is ON, verify it can proceed safely
    # only to dry_run payload creation.
    print("\n[TEST MODE]")
    print("Safety is currently ALLOWED.")
    print("Testing dry_run=True safe payload path...\n")

    result = service.send_ppv_to_user(
        fanvue_account_id=1,
        fanvue_user_uuid="TEST-USER-UUID",
        thread_id="TEST-THREAD-ID",
        content_item=content_item,
        price=19.99,
        dry_run=True,
    )

    print("\n[RESULT]")
    print(result)

    assert result.get("success") is True
    assert result.get("status") == "dry_run"
    assert result.get("payload") is not None
    assert result.get("safety_result", {}).get("allowed") is True
    assert result.get("content_guard_result", {}).get("allowed") is True

    print("\n✅ PASS")
    print("One-on-one PPV passed safety checks and stopped at dry_run.")
    print("No live send occurred.")


if __name__ == "__main__":
    main()