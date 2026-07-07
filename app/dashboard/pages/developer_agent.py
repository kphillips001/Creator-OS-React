"""Developer Agent workspace page.

This page is presentation only. Developer Agent answers flow through
DeveloperAgentService and read-only architecture metadata.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import streamlit as st

from app.models.developer_agent import (
    DeveloperAgentEvidence,
    DeveloperAgentRecommendation,
    DeveloperAgentRequest,
    DeveloperAgentResponse,
    DeveloperAgentSource,
)
from app.services.developer_agent_service import DeveloperAgentService


SUGGESTED_QUESTIONS = (
    "What should we build next?",
    "Generate the next Codex command.",
    "Review the architecture.",
    "What technical debt remains?",
    "Explain Creator Agent architecture.",
    "What tests should I run?",
    "Is this implementation ready?",
    "What are the risks?",
)

DEVELOPER_AGENT_HISTORY_PREFIX = "developer_agent_history"


def _history_key(active_account: dict | None) -> str:
    account_id = (active_account or {}).get("id") or "default"
    return f"{DEVELOPER_AGENT_HISTORY_PREFIX}_{account_id}"


def _ensure_history(key: str) -> list[dict[str, Any]]:
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def _request_from_question(
    question: str,
    *,
    history: list[dict[str, Any]] | None = None,
) -> DeveloperAgentRequest:
    conversation_history = tuple(
        {
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in (history or [])[-12:]
        if message.get("role") in {"user", "assistant"} and message.get("content")
    )
    return DeveloperAgentRequest(
        question=question,
        metadata={
            "surface": "creator_hq",
            "page": "developer_agent",
            "conversation_history": conversation_history,
        },
    )


def _submit_question(
    question: str,
    *,
    history: list[dict[str, Any]],
    developer_agent_service: DeveloperAgentService,
) -> DeveloperAgentResponse:
    request = _request_from_question(question, history=history)
    history.append({"role": "user", "content": question})
    response = developer_agent_service.answer(request)
    history.append(
        {
            "role": "assistant",
            "content": response.answer_text,
            "response": response,
        }
    )
    return response


def _render_sources(sources: Iterable[DeveloperAgentSource]) -> None:
    sources = tuple(sources)
    if not sources:
        st.caption("No architecture sources were available.")
        return
    for source in sources:
        st.write(f"**{source.name}**")
        st.caption(source.summary)
        st.progress(min(max(source.confidence, 0.0), 1.0))


def _render_evidence(evidence: Iterable[DeveloperAgentEvidence]) -> None:
    evidence = tuple(evidence)
    if not evidence:
        st.caption("No supporting evidence was returned.")
        return
    for item in evidence:
        st.write(f"**{item.source}**")
        st.caption(
            " | ".join(
                (
                    item.evidence_type,
                    f"Confidence: {item.confidence:.0%}",
                    item.summary,
                )
            )
        )


def _render_recommendations(
    recommendations: Iterable[DeveloperAgentRecommendation],
) -> None:
    recommendations = tuple(recommendations)
    if not recommendations:
        st.caption("No recommendations were returned.")
        return
    for recommendation in recommendations:
        st.write(recommendation.title)
        st.caption(
            " | ".join(
                (
                    f"Priority: {recommendation.priority}",
                    f"Source: {recommendation.source}",
                    recommendation.detail,
                )
            )
        )


def _render_response_details(response: DeveloperAgentResponse) -> None:
    with st.expander("Structured response", expanded=True):
        st.metric("Confidence", f"{response.confidence:.0%}")
        st.caption(f"Intent: {response.intent.value}")

        st.markdown("#### Architecture Sources")
        _render_sources(response.sources)

        st.markdown("#### Evidence")
        _render_evidence(response.evidence)

        st.markdown("#### Recommendations")
        _render_recommendations(response.recommendations)

        if response.suggested_follow_up_questions:
            st.markdown("#### Suggested Follow-up Questions")
            for question in response.suggested_follow_up_questions:
                st.caption(question)

        if response.warnings:
            st.markdown("#### Warnings")
            for warning in response.warnings:
                st.warning(warning)

        if response.limitations:
            st.markdown("#### Limitations")
            for limitation in response.limitations:
                st.info(limitation)


def _render_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        with st.chat_message(role):
            st.markdown(content)
            response = message.get("response")
            if isinstance(response, DeveloperAgentResponse):
                _render_response_details(response)


def _render_suggestions(
    *,
    history: list[dict[str, Any]],
    developer_agent_service: DeveloperAgentService,
) -> None:
    st.markdown("### Suggested Questions")
    columns = st.columns(2)
    for index, question in enumerate(SUGGESTED_QUESTIONS):
        column = columns[index % 2]
        if column.button(
            question,
            key=f"developer_agent_suggestion_{index}",
            use_container_width=True,
        ):
            with st.spinner("Developer Agent is reviewing read-only architecture context..."):
                _submit_question(
                    question,
                    history=history,
                    developer_agent_service=developer_agent_service,
                )
            st.rerun()


def render_developer_agent(
    *,
    active_account: dict | None = None,
    developer_agent_service: DeveloperAgentService | None = None,
) -> None:
    service = developer_agent_service or DeveloperAgentService()
    history_key = _history_key(active_account)
    history = _ensure_history(history_key)

    st.title("Developer Agent")
    st.caption(
        "Read-only software architect for Creator OS architecture, roadmap, "
        "compatibility, validation, and implementation guidance."
    )

    header_columns = st.columns([3, 1])
    with header_columns[0]:
        st.caption("Advisory only. It does not execute commands or modify files.")
    with header_columns[1]:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state[history_key] = []
            st.rerun()

    _render_suggestions(
        history=history,
        developer_agent_service=service,
    )

    st.divider()
    st.markdown("### Conversation")
    _render_messages(history)

    with st.form("developer_agent_chat_form", clear_on_submit=True):
        user_question = st.text_input(
            "Ask Developer Agent",
            placeholder="Ask about architecture, roadmap, tests, risks, or compatibility.",
        )
        submitted = st.form_submit_button(
            "Send",
            type="primary",
            use_container_width=True,
        )

    if submitted and user_question:
        with st.spinner("Developer Agent is reviewing read-only architecture context..."):
            _submit_question(
                user_question,
                history=history,
                developer_agent_service=service,
            )
        st.rerun()
