import streamlit as st
import pandas as pd

from app.services.delayed_messages_dashboard_service import (
    DelayedMessagesDashboardService,
)


def render_delayed_messages_dashboard(
    dashboard_service: DelayedMessagesDashboardService | None = None,
):

    active_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    st.title(
        "⏰ Delayed Messages Dashboard"
    )

    st.caption(
        "Monitor delayed followup queue activity, "
        "status counts, retries, cancellations, "
        "and completed delayed sends."
    )

    st.divider()

    service = dashboard_service or DelayedMessagesDashboardService()
    dashboard = (
        service.build_dashboard(
            fanvue_account_id=active_account_id,
            recent_limit=100,
        )
    )
    summary = dashboard.summary

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Pending",
            summary["pending"],
        )

        st.metric(
            "Completed",
            summary["completed"],
        )

    with col2:
        st.metric(
            "Processing",
            summary["processing"],
        )

        st.metric(
            "Failed",
            summary["failed"],
        )

    with col3:
        st.metric(
            "Cancelled",
            summary["cancelled"],
        )

        st.metric(
            "Expired",
            summary["expired"],
        )

    st.divider()

    st.subheader(
        "Recent Delayed Messages"
    )

    recent_rows = dashboard.recent_rows

    if not recent_rows:
        st.info(
            "No delayed messages found."
        )
        return

    df = pd.DataFrame(recent_rows)

    preferred_columns = [
        "id",
        "fanvue_account_id",
        "fanvue_user_id",
        "message_body",
        "status",
        "retry_count",
        "scheduled_for",
        "created_at",
        "completed_at",
        "cancelled_at",
        "expired_at",
    ]

    available_columns = [
        col for col in preferred_columns
        if col in df.columns
    ]

    st.dataframe(
        df[available_columns],
        use_container_width=True,
        height=600,
    )
