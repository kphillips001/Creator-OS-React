from app.services.mass_ppv_worker_service import (
    MassPPVWorkerService,
)

from app.repositories.mass_ppv_campaign_repository import (
    create_mass_ppv_campaign,
    create_mass_ppv_queue_entry,
    get_campaign_status,
)


def main():
    print("\n=== MASS PPV WORKER SERVICE TEST ===\n")

    campaign_id = create_mass_ppv_campaign(
        campaign_name="Worker Test Campaign",
        fanvue_account_id=1,
        content_id=1,
        caption="Test Caption",
        price=19.99,
    )

    print(f"[CAMPAIGN CREATED] campaign_id={campaign_id}")

    queue_id_1 = create_mass_ppv_queue_entry(
        campaign_id=campaign_id,
        fanvue_user_id="worker_test_1",
    )

    queue_id_2 = create_mass_ppv_queue_entry(
        campaign_id=campaign_id,
        fanvue_user_id="worker_test_2",
    )

    print(f"[QUEUE CREATED] ids={queue_id_1}, {queue_id_2}")

    service = MassPPVWorkerService()

    results = service.process_pending_queue(
        limit=10,
    )

    print("\n=== WORKER RESULTS ===\n")

    for result in results:
        print(result)

    status = get_campaign_status(
        campaign_id=campaign_id,
    )

    print("\n=== CAMPAIGN STATUS ===\n")
    print(status)

    print("\n=== MASS PPV WORKER SERVICE TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()