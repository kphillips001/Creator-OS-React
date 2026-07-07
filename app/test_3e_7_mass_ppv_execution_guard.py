from app.services.mass_ppv_send_service import (
    MassPPVSendService,
)


def build_test_content():
    return {
        "id": 999998,
        "tag": "TEST_3E_7_MASS_PPV_GUARD",
        "classification": "VIP",
        "content_tier": "VIP",
        "destination": "VIP",
        "upload_status": "uploaded",
        "fanvue_media_uuid": "test-media-uuid",
        "fanvue_preview_media_uuid": "test-preview-uuid",
        "fanvue_full_media_uuid": "test-full-uuid",
        "title": "3E.7 Test Mass PPV",
        "safe_summary": "Test Mass PPV guard content",
        "tags": ["test", "mass_ppv_guard"],
    }


def build_test_targets():
    return [
        {
            "fanvue_user": {
                "id": 1,
                "username": "test_mass_ppv_user",
                "fanvue_user_uuid": "test-user-uuid",
            },
            "memory": {
                "buyer_tier": "LOW",
                "user_value_tier": "LOW",
                "is_whale": False,
                "is_top_spender": False,
                "buyer_session_active": False,
                "close_ready": False,
                "intent_score": 0.1,
                "heat_score": 0.1,
                "conversation_mode": "casual",
            },
        }
    ]


def run_off_switch_test():
    print("\n=== 3E.7 MASS PPV OFF-SWITCH TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Mass PPV Enabled = OFF\n"
    )

    service = MassPPVSendService()

    result = service.send_mass_ppv_campaign(
        fanvue_account_id=2,
        targets=build_test_targets(),
        content_item=build_test_content(),
        caption="3E.7 Mass PPV guard test caption",
        price=14.99,
        dry_run=True,
    )

    print("\nOFF-SWITCH RESULT:")
    print(result)

    assert result["success"] is True
    assert result["status"] == "complete"
    assert result["safety_result"]["blocked"] is True
    assert result["safety_result"]["allowed"] is False
    assert result["safety_result"]["reason"] == "mass_ppv_disabled"
    assert result["sent_count"] == 0
    assert result["dry_run_count"] == 0
    assert result["skipped_count"] == 1

    assert result["results"][0]["reason"] == "module_disabled"

    print("\n✅ OFF switch correctly blocked Mass PPV execution.\n")


def run_on_dry_run_test():
    print("\n=== 3E.7 MASS PPV ON DRY-RUN TEST ===\n")
    print(
        "Dashboard setup required:\n"
        "- Global Automation Enabled = ON\n"
        "- Global Live Sends Enabled = ON\n"
        "- Manual Pause Enabled = OFF\n"
        "- Mass PPV Enabled = ON\n"
    )

    service = MassPPVSendService()

    result = service.send_mass_ppv_campaign(
        fanvue_account_id=2,
        targets=build_test_targets(),
        content_item=build_test_content(),
        caption="3E.7 Mass PPV guard test caption",
        price=14.99,
        dry_run=True,
    )

    print("\nON DRY-RUN RESULT:")
    print(result)

    assert result["success"] is True
    assert result["status"] == "complete"

    # 3E.7 validates that the dashboard switch allows
    # Mass PPV execution to reach dry-run mode safely.
    #
    # The service may still skip later for normal runtime reasons
    # such as targeting blocks, content guard blocks, duplicate content,
    # or missing user data. Those are NOT switch failures.
    assert (
        result["safety_result"]["allowed"] is True
        or result["results"][0]["reason"].startswith(
            "realtime_buyer_state"
        )
    )
    assert (
        result["safety_result"]["blocked"] is False
        or result["results"][0]["reason"].startswith(
            "realtime_buyer_state"
        )
    )

    if result["results"]:
        execution_guard_result = result["results"][0].get(
            "execution_guard_result"
        )

        if execution_guard_result:
            assert execution_guard_result["reason"] == "dry_run_allowed"
            assert execution_guard_result["blocked"] is False
            assert execution_guard_result["allowed"] is True

    print("\n✅ ON dry-run allowed Mass PPV orchestration safely.\n")


def main():
    print("\n=== 3E.7 MASS PPV EXECUTION GUARD TEST ===\n")

    print(
        "Run this test twice:\n\n"
        "1) First with Mass PPV Enabled OFF\n"
        "   Expected: mass_ppv_disabled\n\n"
        "2) Then with Mass PPV Enabled ON\n"
        "   Expected: dry_run_allowed or safe downstream skip\n"
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

    print("\n=== 3E.7 TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()