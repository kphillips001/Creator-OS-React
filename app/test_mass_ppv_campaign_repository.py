from app.repositories.mass_ppv_campaign_repository import (
    create_mass_ppv_campaign,
    create_mass_ppv_queue_entry,
    fetch_pending_mass_ppv_queue,
    mark_mass_ppv_processing,
    mark_mass_ppv_completed,
    mark_mass_ppv_failed,
    get_campaign_status,
    get_pending_queue_count,
    get_failed_queue_count,
    get_completed_queue_count,
)


def main():
    print(
        "\n=== MASS PPV CAMPAIGN REPOSITORY TEST ===\n"
    )

    # =====================================================
    # CREATE CAMPAIGN
    # =====================================================

    campaign_id = create_mass_ppv_campaign(
        campaign_name="VIP Weekend Drop",
        fanvue_account_id=1,
        content_id=999,
        caption="Exclusive VIP drop 😈",
        price=24.99,
    )

    print(
        f"[CAMPAIGN CREATED] campaign_id={campaign_id}"
    )

    assert campaign_id

    # =====================================================
    # CREATE QUEUE ITEMS
    # =====================================================

    queue_id_1 = create_mass_ppv_queue_entry(
        campaign_id=campaign_id,
        fanvue_user_id="test_user_1",
    )

    queue_id_2 = create_mass_ppv_queue_entry(
        campaign_id=campaign_id,
        fanvue_user_id="test_user_2",
    )

    print(
        f"[QUEUE CREATED] ids={queue_id_1}, {queue_id_2}"
    )

    # =====================================================
    # FETCH PENDING
    # =====================================================

    pending = fetch_pending_mass_ppv_queue()

    print(
        f"[PENDING ITEMS] count={len(pending)}"
    )

    assert len(pending) >= 2

    # =====================================================
    # PROCESSING
    # =====================================================

    mark_mass_ppv_processing(
        queue_id_1
    )

    print(
        f"[PROCESSING] queue_id={queue_id_1}"
    )

    # =====================================================
    # COMPLETED
    # =====================================================

    mark_mass_ppv_completed(
        queue_id_1,
        fanvue_message_id="msg_123",
    )

    print(
        f"[COMPLETED] queue_id={queue_id_1}"
    )

    # =====================================================
    # FAILED
    # =====================================================

    mark_mass_ppv_failed(
        queue_id_2,
        failure_reason="Simulated failure",
    )

    print(
        f"[FAILED] queue_id={queue_id_2}"
    )

    # =====================================================
    # CAMPAIGN STATUS
    # =====================================================

    status = get_campaign_status(
        campaign_id
    )

    print(
        f"\n[CAMPAIGN STATUS]\n{status}"
    )

    # =====================================================
    # COUNTS
    # =====================================================

    pending_count = get_pending_queue_count()
    failed_count = get_failed_queue_count()
    completed_count = get_completed_queue_count()

    print(
        f"""
[QUEUE COUNTS]

pending={pending_count}
failed={failed_count}
completed={completed_count}
"""
    )

    print(
        "\n=== TEST COMPLETE ===\n"
    )


if __name__ == "__main__":
    main()