import streamlit as st
import pandas as pd

from app.services.wall_scheduler_dashboard_service import (
    WallSchedulerDashboardService,
)


def render_wall_scheduler_dashboard(
    dashboard_service: WallSchedulerDashboardService | None = None,
):

    active_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    st.title(
        "🧱 Wall Publishing Queue"
    )

    st.markdown("---")

    # =====================================================
    # COUNTS
    # =====================================================

    service = dashboard_service or WallSchedulerDashboardService()
    dashboard = (
        service.build_dashboard(
            fanvue_account_id=active_account_id,
        )
    )
    counts = dashboard.counts

    col1, col2, col3, col4, col5 = (
        st.columns(5)
    )

    col1.metric(
        "Total",
        counts.get("total", 0),
    )

    col2.metric(
        "Pending",
        counts.get("pending", 0),
    )

    col3.metric(
        "Processing",
        counts.get("processing", 0),
    )

    col4.metric(
        "Completed",
        counts.get("completed", 0),
    )

    col5.metric(
        "Failed",
        counts.get("failed", 0),
    )

    st.markdown("---")

    # =====================================================
    # QUEUE TABLE
    # =====================================================

    st.subheader(
        "Wall Queue"
    )

    rows = dashboard.queue_rows

    if not rows:

        st.info(
            "No wall queue items found."
        )

        return

    dataframe = pd.DataFrame(rows)

    st.dataframe(
        dataframe,
        use_container_width=True,
        height=600,
    )
