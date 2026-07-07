from app.repositories.wall_post_repository import (
    fetch_wall_queue_dashboard,
    fetch_wall_queue_counts,
)


def main():

    print(
        "\n=== WALL DASHBOARD REPOSITORY TEST ===\n"
    )

    # =====================================================
    # COUNTS
    # =====================================================

    print(
        "[1] Fetching wall queue counts..."
    )

    counts = (
        fetch_wall_queue_counts()
    )

    print(counts)
    print()

    # =====================================================
    # DASHBOARD DATA
    # =====================================================

    print(
        "[2] Fetching dashboard queue items..."
    )

    rows = (
        fetch_wall_queue_dashboard()
    )

    print(
        f"Queue Rows: {len(rows)}"
    )

    for row in rows[:5]:
        print(row)

    print()

    print(
        "🚀 WALL DASHBOARD REPOSITORY TEST COMPLETE\n"
    )


if __name__ == "__main__":
    main()