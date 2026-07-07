from app.repositories.mass_ppv_campaign_repository import (
    fetch_mass_ppv_campaign_dashboard_rows,
    fetch_mass_ppv_queue_dashboard_rows,
    fetch_mass_ppv_campaign_analytics_rows,
)


def main():
    print("\n=== MASS PPV DASHBOARD REPOSITORY TEST ===\n")

    campaigns = fetch_mass_ppv_campaign_dashboard_rows(
        limit=10,
    )

    print("\n--- CAMPAIGNS ---")
    print(campaigns)

    queue_rows = fetch_mass_ppv_queue_dashboard_rows(
        status="all",
        limit=10,
    )

    print("\n--- QUEUE ROWS ---")
    print(queue_rows)

    analytics = fetch_mass_ppv_campaign_analytics_rows(
        limit=10,
    )

    print("\n--- ANALYTICS ---")
    print(analytics)

    print(
        "\n=== MASS PPV DASHBOARD REPOSITORY TEST COMPLETE ===\n"
    )


if __name__ == "__main__":
    main()