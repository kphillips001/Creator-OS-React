from app.services.mass_ppv_scheduler_service import (
    MassPPVSchedulerService,
)

from app.repositories.mass_ppv_campaign_repository import (
    create_mass_ppv_campaign,
    fetch_campaign,
    get_campaign_status,
)


def main():
    print("\n=== MASS PPV SCHEDULER SERVICE TEST ===\n")

    campaign_id = create_mass_ppv_campaign(
        campaign_name="Scheduler Test Campaign",
        fanvue_account_id=1,
        content_id=1,
        caption="Scheduler Test Caption",
        price=19.99,
    )

    print(f"[CAMPAIGN CREATED] campaign_id={campaign_id}")

    campaign = fetch_campaign(
        campaign_id=campaign_id,
    )

    service = MassPPVSchedulerService()

    result = service.schedule_campaign(
        campaign=campaign,
        target_limit=25,
    )

    print("\n=== SCHEDULER RESULT ===\n")
    print(result)

    status = get_campaign_status(
        campaign_id=campaign_id,
    )

    print("\n=== CAMPAIGN QUEUE STATUS ===\n")
    print(status)

    print("\n=== MASS PPV SCHEDULER SERVICE TEST COMPLETE ===\n")


if __name__ == "__main__":
    main()