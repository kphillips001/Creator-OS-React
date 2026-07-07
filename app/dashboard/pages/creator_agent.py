"""Creator Agent workspace page.

This page is presentation only. All business question handling flows through
CreatorAgentService and its read-only tool orchestration.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

import streamlit as st

from app.models.creator_agent import (
    CreatorAgentActionProposal,
    CreatorAgentRecommendedAction,
    CreatorAgentRequest,
    CreatorAgentResponse,
    CreatorAgentSource,
)
from app.services.creator_agent_service import CreatorAgentService


SUGGESTED_QUESTIONS = (
    "What should I work on today?",
    "Show today's business summary.",
    "Which Products need Media Links?",
    "Which customers need attention?",
    "Which Products are underperforming?",
    "What should I publish next?",
    "Show Business Health.",
    "Why was this Product recommended?",
)

CREATOR_AGENT_HISTORY_PREFIX = "creator_agent_history"


def _history_key(active_account: dict | None) -> str:
    account_id = (active_account or {}).get("id") or "default"
    return f"{CREATOR_AGENT_HISTORY_PREFIX}_{account_id}"


def _ensure_history(key: str) -> list[dict[str, Any]]:
    if key not in st.session_state:
        st.session_state[key] = []
    return st.session_state[key]


def _request_from_question(
    question: str,
    *,
    creator_profile: dict | None,
    active_account: dict | None,
    history: list[dict[str, Any]] | None = None,
) -> CreatorAgentRequest:
    conversation_history = tuple(
        {
            "role": message.get("role"),
            "content": message.get("content"),
        }
        for message in (history or [])[-12:]
        if message.get("role") in {"user", "assistant"} and message.get("content")
    )
    return CreatorAgentRequest(
        question=question,
        creator_profile_id=(creator_profile or {}).get("id"),
        account_id=(active_account or {}).get("id"),
        provider=(active_account or {}).get("provider") or "fanvue",
        metadata={
            "surface": "creator_workspace",
            "page": "creator_agent",
            "conversation_history": conversation_history,
        },
    )


def _submit_question(
    question: str,
    *,
    history: list[dict[str, Any]],
    creator_profile: dict | None,
    active_account: dict | None,
    creator_agent_service: CreatorAgentService,
) -> CreatorAgentResponse:
    request = _request_from_question(
        question,
        creator_profile=creator_profile,
        active_account=active_account,
        history=history,
    )
    history.append({"role": "user", "content": question})
    response = creator_agent_service.answer(request)
    history.append(
        {
            "role": "assistant",
            "content": response.answer_text,
            "response": response,
        }
    )
    return response


def _render_sources(sources: Iterable[CreatorAgentSource]) -> None:
    sources = tuple(sources)
    if not sources:
        st.caption("No supporting sources were available.")
        return

    for source in sources:
        st.write(f"**{source.name}**")
        st.caption(source.summary)
        st.progress(min(max(source.confidence, 0.0), 1.0))


def _render_actions(actions: Iterable[CreatorAgentRecommendedAction]) -> None:
    actions = tuple(actions)
    if not actions:
        st.caption("No recommended actions were returned.")
        return

    for action in actions:
        st.write(action.title)
        if action.detail:
            st.caption(action.detail)
        st.caption(f"Priority: {action.priority} | Source: {action.source}")


def _render_action_proposals(proposals: Iterable[CreatorAgentActionProposal]) -> None:
    proposals = tuple(proposals)
    if not proposals:
        st.caption("No action proposals were returned.")
        return

    for proposal in proposals:
        st.write(proposal.title)
        st.caption(proposal.detail or "Review only.")
        st.caption(
            "Confirmation required"
            if proposal.requires_confirmation
            else "No confirmation required"
        )


def _render_messages(messages: list[dict[str, Any]]) -> None:
    for message in messages:
        role = message.get("role", "assistant")
        content = message.get("content", "")
        with st.chat_message(role):
            st.markdown(content)
            response = message.get("response")
            if isinstance(response, CreatorAgentResponse):
                _render_response_details(response)


def _render_response_details(response: CreatorAgentResponse) -> None:
    with st.expander("Structured response", expanded=True):
        st.metric("Confidence", f"{response.confidence:.0%}")
        st.caption(f"Intent: {response.intent.value}")

        st.markdown("#### Supporting Sources")
        _render_sources(response.sources)

        if response.business_reasoning:
            st.markdown("#### Business Reasoning")
            for reason in response.business_reasoning:
                st.write(reason)

        if response.supporting_evidence:
            st.markdown("#### Supporting Evidence")
            for item in response.supporting_evidence:
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

        if response.confidence_explanation:
            st.markdown("#### Confidence Explanation")
            st.caption(response.confidence_explanation)

        if response.recommendation_rationale:
            st.markdown("#### Recommendation Rationale")
            for rationale in response.recommendation_rationale:
                st.caption(rationale)

        st.markdown("#### Recommended Actions")
        _render_actions(response.recommended_actions)

        st.markdown("#### Action Proposals")
        _render_action_proposals(response.action_proposals)

        if response.suggested_follow_up_questions:
            st.markdown("#### Suggested Follow-up Questions")
            for question in response.suggested_follow_up_questions:
                st.caption(question)

        if response.related_business_areas:
            st.markdown("#### Related Business Areas")
            st.caption(", ".join(response.related_business_areas))

        if response.warnings:
            st.markdown("#### Warnings")
            for warning in response.warnings:
                st.warning(warning)

        if response.limitations:
            st.markdown("#### Limitations")
            for limitation in response.limitations:
                st.info(limitation)


def _render_suggestions(
    *,
    history: list[dict[str, Any]],
    creator_profile: dict | None,
    active_account: dict | None,
    creator_agent_service: CreatorAgentService,
) -> None:
    st.markdown("### Suggested Questions")
    columns = st.columns(2)
    for index, question in enumerate(SUGGESTED_QUESTIONS):
        column = columns[index % 2]
        if column.button(
            question,
            key=f"creator_agent_suggestion_{index}",
            use_container_width=True,
        ):
            with st.spinner("Creator Agent is reviewing Creator OS read models..."):
                _submit_question(
                    question,
                    history=history,
                    creator_profile=creator_profile,
                    active_account=active_account,
                    creator_agent_service=creator_agent_service,
                )
            st.rerun()


def _render_future_placeholders() -> None:
    st.markdown("### Future Capabilities")
    columns = st.columns(4)
    placeholders = (
        "Attach business context",
        "Voice input",
        "Export conversation",
        "Suggested follow-up questions",
    )
    for column, label in zip(columns, placeholders):
        column.button(label, disabled=True, use_container_width=True)


def _render_auto_scroll_anchor() -> None:
    st.markdown(
        """
        <div id="creator-agent-bottom"></div>
        <script>
        const anchor = window.parent.document.getElementById("creator-agent-bottom");
        if (anchor) { anchor.scrollIntoView({ behavior: "smooth", block: "end" }); }
        </script>
        """,
        unsafe_allow_html=True,
    )


def render_creator_agent(
    *,
    creator_profile: dict | None = None,
    active_account: dict | None = None,
    creator_agent_service: CreatorAgentService | None = None,
) -> None:
    service = creator_agent_service or CreatorAgentService()
    history_key = _history_key(active_account)
    history = _ensure_history(history_key)

    st.title("Creator Agent")
    st.caption(
        "Natural-language business assistant powered by Creator OS read models."
    )

    header_columns = st.columns([3, 1])
    with header_columns[0]:
        st.caption("Presentation only. Business domains remain the source of truth.")
    with header_columns[1]:
        if st.button("Clear conversation", use_container_width=True):
            st.session_state[history_key] = []
            st.rerun()

    _render_suggestions(
        history=history,
        creator_profile=creator_profile,
        active_account=active_account,
        creator_agent_service=service,
    )

    st.divider()
    st.markdown("### Conversation")
    _render_messages(history)

    with st.form("creator_agent_chat_form", clear_on_submit=True):
        user_question = st.text_input(
            "Ask Creator Agent",
            placeholder="Ask about priorities, Products, customers, publishing, or Telegram.",
        )
        submitted = st.form_submit_button(
            "Send",
            type="primary",
            use_container_width=True,
        )

    if submitted and user_question:
        with st.spinner("Creator Agent is reviewing Creator OS read models..."):
            _submit_question(
                user_question,
                history=history,
                creator_profile=creator_profile,
                active_account=active_account,
                creator_agent_service=service,
            )
        st.rerun()

    _render_future_placeholders()
    _render_auto_scroll_anchor()
