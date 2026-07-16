from pathlib import Path
from app.dashboard.navigation import DASHBOARD_NAVIGATION_GROUPS


MAIN_SOURCE = (
    Path(__file__).parent / "dashboard" / "main.py"
).read_text(encoding="utf-8")


def test_sidebar_has_read_only_creator_display():
    assert "st.sidebar.selectbox" not in MAIN_SOURCE
    assert "👤 {st.session_state.get('active_persona_name')}" in MAIN_SOURCE
    assert "Active Creator Account" not in MAIN_SOURCE
    assert "Provider Account ID" not in MAIN_SOURCE
    assert "Selected:" not in MAIN_SOURCE


def test_fanvue_connection_renders_after_navigation():
    navigation_position = MAIN_SOURCE.rindex("_render_sidebar_navigation()")
    connections_position = MAIN_SOURCE.index('st.sidebar.markdown("#### Connections")')

    assert connections_position > navigation_position
    assert "🟢 Fanvue Connected" in MAIN_SOURCE
    assert "OAuth Connected" not in MAIN_SOURCE


def test_legacy_creator_is_not_rendered():
    assert "Amanda Cayne" not in MAIN_SOURCE


def test_utilities_navigation_exposes_strip_metadata():
    utilities = next(
        group for group in DASHBOARD_NAVIGATION_GROUPS
        if group.label == "Utilities"
    )
    assert tuple((item.label, item.page) for item in utilities.items) == (
        ("Strip Metadata", "Strip Metadata"),
    )
