"""Administration dashboard for Creator OS system health."""

from __future__ import annotations

import os
import sys

import streamlit as st

from app.models.system_health import HealthCheck, HealthSection, HealthStatus
from app.services.system_health_service import SystemHealthService


STATUS_LABELS = {
    HealthStatus.HEALTHY.value: "Healthy",
    HealthStatus.WARNING.value: "Warning",
    HealthStatus.CRITICAL.value: "Critical",
    HealthStatus.UNKNOWN.value: "Unknown",
}


def _status_text(status: str) -> str:
    return STATUS_LABELS.get(status, "Unknown")


def _render_check(check: HealthCheck) -> None:
    with st.container(border=True):
        st.markdown(f"**{check.name}**")
        st.caption(_status_text(check.status))
        if check.value:
            st.write(check.value)
        st.caption(check.summary)
        if check.detail:
            st.caption(check.detail)
        if check.guidance:
            st.code(check.guidance, language="powershell")


def _render_section(section: HealthSection) -> None:
    st.markdown(f"### {section.name}")
    checks = section.checks or ()
    if not checks:
        st.caption("No checks available.")
        return
    columns = st.columns(3)
    for index, check in enumerate(checks):
        with columns[index % 3]:
            _render_check(check)


def _render_quick_tests(service: SystemHealthService) -> None:
    st.markdown("### Quick Tests")
    tests = (
        ("Test X", "x"),
        ("Test Telegram", "telegram"),
        ("Test Grok", "grok"),
        ("Test OpenAI", "openai"),
        ("Test Database", "database"),
        ("Test Storage", "storage"),
    )
    columns = st.columns(3)
    for index, (label, key) in enumerate(tests):
        with columns[index % 3]:
            if st.button(label, key=f"system_health_quick_{key}", use_container_width=True):
                st.session_state[f"system_health_result_{key}"] = service.run_quick_test(key)
            result = st.session_state.get(f"system_health_result_{key}")
            if result:
                _render_check(result)


def render_system_health(service: SystemHealthService | None = None) -> None:
    service = service or SystemHealthService()
    report = service.build_report()

    st.title("System Health")
    st.caption("Operational readiness dashboard for Creator OS.")
    st.code(
        f"""
sys.executable:
{sys.executable}

PID:
{os.getpid()}
""",
        language="text",
    )

    top = st.container(border=True)
    with top:
        col_status, col_score, col_headline = st.columns([1, 1, 2])
        col_status.metric("System Health", _status_text(report.overall_status))
        col_score.metric("Score", f"{report.score}%")
        col_headline.metric("Readiness", report.headline)

    runtime = report.section("Runtime")
    dependencies = report.section("Dependencies")
    configuration = report.section("Configuration")
    providers = report.section("Provider Connectivity")
    ai_models = report.section("AI Models")
    storage = report.section("Storage")
    database = report.section("Database")
    queues = report.section("Queues")

    for section in (
        runtime,
        dependencies,
        configuration,
        providers,
        ai_models,
        storage,
        database,
        queues,
    ):
        if section is not None:
            _render_section(section)

    st.markdown("### Warnings")
    if not report.warnings:
        st.success("No warnings detected.")
    else:
        for warning in report.warnings:
            _render_check(warning)

    _render_quick_tests(service)
