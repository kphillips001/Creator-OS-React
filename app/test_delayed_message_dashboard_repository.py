from app.repositories.delayed_message_queue_repository import (
    get_delayed_message_queue_counts,
    fetch_recent_delayed_messages,
)

from app.repositories.delayed_message_dashboard_repository import (
    build_delayed_message_dashboard_summary,
)


def main():
    print(
        "\n=== DELAYED DASHBOARD TEST ===\n"
    )

    counts = (
        get_delayed_message_queue_counts()
    )

    summary = (
        build_delayed_message_dashboard_summary(
            counts
        )
    )

    print("\nDashboard Summary:\n")
    print(summary)

    recent_rows = (
        fetch_recent_delayed_messages()
    )

    print("\nRecent Delayed Messages:\n")

    for row in recent_rows:
        print(row)

    print(
        "\n✅ DELAYED DASHBOARD TEST PASSED\n"
    )


if __name__ == "__main__":
    main()