from app.services.one_on_one_ppv_send_service import (
    OneOnOnePPVSendService,
)


def build_test_content():
    return {
        "id": 999999,
        "tag": "TEST_3E_6_PPV_GUARD",
        "classification": "VIP",
        "content_tier": "VIP",
        "destination": "VIP",
        "upload_status": "uploaded",
        "fanvue_media_uuid": "test-media-uuid",
        "fanvue_preview_media_uuid": "test-preview-uuid",
        "fanvue_full_media_uuid": "test-full-uuid",
        "title": "3E.6 Test PPV",
        "safe_summary": "Test PPV guard content",
        "tags": ["test", "ppv_guard"],
    }


def run_off_switch_test():
    print("\n=== 3E.6 PPV OFF-SWITCH TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- PPV Offers Enabled = OFF\n"
    )

    service = OneOnOnePPVSendService()

    result = service.send_ppv_to_user(
        fanvue_account_id=2,
        fanvue_user_uuid=1,
        thread_id="test-thread",
        content_item=build_test_content(),
        price=19.99,
        dry_run=True,
    )

    print("\nOFF-SWITCH RESULT:")
    print(result)

    assert result["success"] is False
    assert result["blocked"] is True
    assert result["status"] == "blocked"
    assert result["reason"] == "ppv_offers_disabled"

    assert (
        result["execution_guard_result"]["reason"]
        == "ppv_offers_disabled"
    )
    assert (
        result["execution_guard_result"]["blocked"]
        is True
    )
    assert (
        result["execution_guard_result"]["allowed"]
        is False
    )

    print("\n✅ OFF switch correctly blocked PPV execution.\n")


def run_on_dry_run_test():
    print("\n=== 3E.6 PPV ON DRY-RUN TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- PPV Offers Enabled = ON\n"
    )

    service = OneOnOnePPVSendService()

    result = service.send_ppv_to_user(
        fanvue_account_id=2,
        fanvue_user_uuid=1,
        thread_id="test-thread",
        content_item=build_test_content(),
        price=19.99,
        dry_run=True,
    )

    print("\nON DRY-RUN RESULT:")
    print(result)

    # 3E.6 validates that the dashboard switch allows
    # PPV execution to reach dry-run mode safely.
    #
    # The service may still stop later for normal runtime reasons
    # such as no_memory, duplicate content, or content guard blocks.
    # Those are NOT switch failures.
    assert (
        result["execution_guard_result"]["reason"]
        == "dry_run_allowed"
    )
    assert (
        result["execution_guard_result"]["blocked"]
        is False
    )
    assert (
        result["execution_guard_result"]["allowed"]
        is True
    )

    print("\n✅ ON dry-run allowed PPV orchestration safely.\n")


def main():
    print("\n=== 3E.6 PPV EXECUTION GUARD TEST ===\n")

    print(
        "Run this test twice:\n\n"
        "1) First with PPV Offers Enabled OFF\n"
        "   Expected: ppv_offers_disabled\n\n"
        "2) Then with PPV Offers Enabled ON\n"
        "   Expected: dry_run_allowed\n"
    )

    choice = input(
        "Type OFF to run the OFF-switch test, "
        "or ON to run the dry-run test: "
    ).strip().upper()

    if choice == "OFF":
        run_off_switch_test()
    elif choice == "ON":
        run_on_dry_run_test()
    else:
        raise ValueError("Invalid choice. Type OFF or ON.")

    print("\n=== 3E.6 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()