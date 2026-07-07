"""Dedicated Creator Activity Feed page."""

from __future__ import annotations

import streamlit as st

from app.models.workspace_dashboard import WorkspaceActivityEvent
from app.services.creator_workspace_service import CreatorWorkspaceService


def _format_event_timestamp(event: WorkspaceActivityEvent) -> str:
    if event.timestamp is None:
        return "Future-ready"
    return event.timestamp.strftime("%Y-%m-%d %H:%M")


def _render_activity_feed(events: tuple[WorkspaceActivityEvent, ...]) -> None:
    if not events:
        st.caption("No activity feed events available.")
        return

    for index, event in enumerate(events):
        with st.container():
            st.caption(
                " | ".join(
                    (
                        _format_event_timestamp(event),
                        event.event_type.replace("_", " ").title(),
                        event.source,
                    )
                )
            )
            st.write(event.title)
            st.caption(event.detail)
            if event.future_ready:
                st.info("Placeholder: event stream not yet exposed.")
        if index < len(events) - 1:
            st.divider()


def render_activity_feed(
    *,
    creator_profile: dict | None = None,
    active_account: dict | None = None,
    workspace_service: CreatorWorkspaceService | None = None,
) -> None:
    dashboard = (workspace_service or CreatorWorkspaceService()).build_dashboard(
        creator_profile=creator_profile,
        active_account=active_account,
    )

    st.title("Activity Feed")
    st.caption("Read-only operational events across Creator OS.")
    _render_activity_feed(dashboard.activity_feed)
