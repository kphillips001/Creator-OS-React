def build_delayed_message_dashboard_summary(
    queue_counts,
):
    return {
        "pending": (
            queue_counts.get("pending", 0)
        ),
        "processing": (
            queue_counts.get("processing", 0)
        ),
        "completed": (
            queue_counts.get("completed", 0)
        ),
        "failed": (
            queue_counts.get("failed", 0)
        ),
        "cancelled": (
            queue_counts.get("cancelled", 0)
        ),
        "expired": (
            queue_counts.get("expired", 0)
        ),
    }