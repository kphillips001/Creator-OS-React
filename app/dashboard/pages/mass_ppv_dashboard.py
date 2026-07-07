import pandas as pd
import streamlit as st

from app.services.mass_ppv_dashboard_service import MassPPVDashboardService


def render(
    dashboard_service: MassPPVDashboardService | None = None,
):

    active_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    st.title("Campaign Publishing")

    st.divider()

    # =====================================================
    # CAMPAIGN MONITOR
    # =====================================================
    st.header("Campaign Monitor")

    service = dashboard_service or MassPPVDashboardService()
    campaign_rows = service.get_campaign_rows(
        fanvue_account_id=active_account_id,
        limit=100,
    )

    if campaign_rows:
        df_campaigns = pd.DataFrame(
            campaign_rows
        )

        st.dataframe(
            df_campaigns,
            use_container_width=True,
        )
    else:
        st.info(
            "No Mass PPV campaigns found."
        )

    st.divider()

    # =====================================================
    # QUEUE VIEWER
    # =====================================================
    st.header("Queue Viewer")

    queue_status = st.selectbox(
        "Queue Status Filter",
        options=[
            "all",
            "pending",
            "processing",
            "completed",
            "failed",
        ],
    )

    queue_rows = service.get_queue_rows(
        fanvue_account_id=active_account_id,
        status=queue_status,
        limit=250,
    )

    if queue_rows:
        df_queue = pd.DataFrame(
            queue_rows
        )

        st.dataframe(
            df_queue,
            use_container_width=True,
        )
    else:
        st.info(
            "No queue rows found."
        )

    st.divider()

    # =====================================================
    # ANALYTICS
    # =====================================================
    st.header("Campaign Analytics")

    analytics_rows = service.get_analytics_rows(
        fanvue_account_id=active_account_id,
        limit=100,
    )

    if analytics_rows:
        df_analytics = pd.DataFrame(
            analytics_rows
        )

        st.dataframe(
            df_analytics,
            use_container_width=True,
        )
    else:
        st.info(
            "No analytics found."
        )
