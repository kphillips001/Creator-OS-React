import streamlit as st

from app.main import (
    decision_engine,
    memory_service,
)

from app.repositories.fanvue_account_repository import (
    get_or_create_account,
)

from app.repositories.user_repository import (
    get_or_create_user_with_memory,
)

from app.repositories.chat_message_repository import (
    get_or_create_chat_thread,
    save_chat_message,
    get_recent_messages_for_gpt,
)


def _get_simulator_context():

    active_account = (
        st.session_state.get(
            "active_fanvue_account",
            {}
        )
    )

    if not active_account:
        raise Exception(
            "No active provider account selected."
        )

    simulated_fanvue_user_uuid = (
        "11111111-1111-1111-1111-111111111111"
    )

    context = get_or_create_user_with_memory(
        fanvue_account_id=active_account["id"],
        fanvue_user_uuid=simulated_fanvue_user_uuid,
        username="test_user",
        display_name="Test User",
        relationship_status="follower",
        is_subscriber=False,
        is_follower=True,
        source="chat_console_test",
    )

    db_user = context["user"]

    engine_user_id = (
        f"{active_account['id']}:{db_user['id']}"
    )

    thread = get_or_create_chat_thread(
        fanvue_account_id=active_account["id"],
        fanvue_user_id=db_user["id"],
    )

    return {
        "account": active_account,
        "db_user": db_user,
        "engine_user_id": engine_user_id,
        "thread": thread,
    }


def _deep_get(data, path, default="—"):
    current = data

    for key in path:
        if not isinstance(current, dict):
            return default

        current = current.get(key)

        if current is None:
            return default

    return current


def render_chat_console():
    st.subheader("Chat Console")

    if st.session_state.get("reset_toast"):
        st.toast("Conversation reset successfully ✅")
        st.session_state.reset_toast = False

    current_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    chat_history_key = (
        f"chat_history_{current_account_id}"
    )

    debug_key = (
        f"last_debug_{current_account_id}"
    )

    simulator_key = (
        f"simulator_context_{current_account_id}"
    )

    if chat_history_key not in st.session_state:
        st.session_state[chat_history_key] = []

    if debug_key not in st.session_state:
        st.session_state[debug_key] = {}

    current_account_id = (
        st.session_state.get(
            "fanvue_account_id"
        )
    )

    existing_context = (
        st.session_state.get(
            simulator_key
        )
    )

    if (
        existing_context
        and existing_context["account"]["id"]
        != current_account_id
    ):
        st.session_state[simulator_key] = None

    if (
        simulator_key not in st.session_state
        or st.session_state[simulator_key] is None
    ):
        st.session_state[simulator_key] = (
            _get_simulator_context()
        )

    context = st.session_state[simulator_key]
    engine_user_id = context["engine_user_id"]
    account = context["account"]
    db_user = context["db_user"]
    thread = context["thread"]

    col_chat, col_debug = st.columns([2, 1])

    with col_chat:
        st.markdown("### Conversation")

        st.caption(
            f"Connected account: {account['username']} | "
            f"Engine user: {engine_user_id}"
        )

        for msg in st.session_state[chat_history_key]:
            if msg["role"] == "user":
                st.markdown(f"**You:** {msg['content']}")
            else:
                st.markdown(f"**Bot:** {msg['content']}")

        st.divider()

        with st.form(
            key="chat_console_form",
            clear_on_submit=True,
        ):
            user_input = st.text_input(
                "Type your message...",
                key="chat_input",
                placeholder="Type your message...",
                label_visibility="visible",
            )

            submitted = st.form_submit_button(
                "Send Message",
                type="primary",
                use_container_width=True,
            )

        if submitted and user_input:
            st.session_state[chat_history_key].append(
                {
                    "role": "user",
                    "content": user_input,
                }
            )

            save_chat_message(
                fanvue_account_id=account["id"],
                thread_id=thread["id"],
                fanvue_user_id=db_user["id"],
                direction="inbound",
                sender_type="user",
                text=user_input,
            )

            chat_history = get_recent_messages_for_gpt(
                fanvue_account_id=account["id"],
                thread_id=thread["id"],
                limit=10,
            )
            result = decision_engine.process_message(
                engine_user_id,
                user_input,
                chat_history=chat_history,
            )

            if result is None:
                result = {
                    "response": "Error: DecisionEngine returned None.",
                    "error": "decision_engine_returned_none",
                }

            bot_response = result.get("response", "")

            save_chat_message(
                fanvue_account_id=account["id"],
                thread_id=thread["id"],
                fanvue_user_id=db_user["id"],
                direction="outbound",
                sender_type="bot",
                text=bot_response,
            )

            st.session_state[chat_history_key].append(
                {
                    "role": "assistant",
                    "content": bot_response,
                }
            )

            st.session_state[debug_key] = result

            st.rerun()

        if st.button("Reset Conversation"):
            st.session_state[chat_history_key] = []
            st.session_state[debug_key] = {}
            memory_service.clear_user_memory(engine_user_id)

            st.session_state.reset_toast = True

            st.rerun()

    with col_debug:
        st.markdown("## System")

        debug = st.session_state[debug_key] or {}

        route = debug.get("route", {})

        if isinstance(route, dict):
            route_name = route.get("route", "—")
            route_reason = route.get("reason", "—")
            route_confidence = route.get("confidence", "—")
        else:
            route_name = route
            route_reason = "—"
            route_confidence = "—"

        intimacy = (
            debug.get("intimacy_overrides")
            or debug.get("intimacy_result")
            or debug.get("runtime_intimacy")
            or {}
        )

        provider_preview = (
            debug.get("provider_preview")
            or debug.get("generation_preview")
            or debug.get("llm_preview")
            or {}
        )

        generation = (
            debug.get("generation")
            or debug.get("gpt_generation")
            or debug.get("response_generation")
            or {}
        )

        provider = (
            debug.get("provider")
            or provider_preview.get("provider")
            or generation.get("provider")
            or "OPENAI"
        )

        runtime_mode = (
            debug.get("runtime_mode")
            or intimacy.get("runtime_mode")
            or provider_preview.get("runtime_mode")
            or "safe_chat"
        )

        adult_allowed = (
            debug.get("adult_generation_allowed")
            if debug.get("adult_generation_allowed") is not None
            else intimacy.get("adult_generation_allowed", False)
        )

        buyer_tier = (
            debug.get("buyer_tier")
            or intimacy.get("buyer_tier")
            or _deep_get(debug, ["memory", "buyer_tier"])
            or _deep_get(debug, ["working_memory", "buyer_tier"])
            or "NON_BUYER"
        )

        premium_allowed = (
            intimacy.get("premium_sexting_allowed")
            or False
        )

        explicit_allowed = (
            intimacy.get("explicit_allowed")
            or False
        )

        grok_eligible = (
            provider_preview.get("grok_eligible")
        )

        premium_qualified = (
            provider_preview.get("premium_qualified")
        )

        st.success(
            f"ACTIVE PROVIDER: {provider}"
        )

        st.markdown("---")

        st.markdown("### Routing")

        st.write(f"**Route:** `{route_name}`")
        st.write(f"**Confidence:** `{route_confidence}`")
        st.write(f"**Reason:** `{route_reason}`")

        st.markdown("### Runtime")

        st.write(f"**Mode:** `{debug.get('mode', '—')}`")
        st.write(f"**Runtime Mode:** `{runtime_mode}`")
        st.write(f"**Buyer Tier:** `{buyer_tier}`")

        st.markdown("### Intimacy")

        st.write(
            f"**Adult Allowed:** "
            f"`{adult_allowed}`"
        )

        st.write(
            f"**Premium Sexting:** "
            f"`{premium_allowed}`"
        )

        st.write(
            f"**Explicit Allowed:** "
            f"`{explicit_allowed}`"
        )

        st.markdown("### Provider Routing")

        st.write(
            f"**Premium Qualified:** "
            f"`{premium_qualified}`"
        )

        st.write(
            f"**Grok Eligible:** "
            f"`{grok_eligible}`"
        )

        st.write(
            f"**Selected Provider:** "
            f"`{provider}`"
        )

        st.markdown("---")

        st.markdown("### Whale Retention")

        st.write(
            f"**Retention Mode:** "
            f"`{debug.get('whale_retention_mode', '—')}`"
        )

        st.write(
            f"**Premium Attention:** "
            f"`{debug.get('premium_attention_priority', '—')}`"
        )

        st.write(
            f"**Reduce Sales Pressure:** "
            f"`{debug.get('reduce_sales_pressure', '—')}`"
        )

        st.write(
            f"**Emotional Priority:** "
            f"`{debug.get('emotional_priority_level', '—')}`"
        )

        st.write(
            f"**Relationship First:** "
            f"`{debug.get('relationship_first_response', '—')}`"
        )

        st.write(
            f"**Premium Pacing:** "
            f"`{debug.get('premium_pacing_preference', '—')}`"
        )

        with st.expander(
            "Whale Retention Profile"
        ):
            st.json(
                debug.get(
                    "whale_retention_profile",
                    {},
                )
            )

                # ==================================================
        # 3D.20.5 — Whale Burnout Prevention
        # ==================================================

        st.markdown("## 3D.20.5 Whale Burnout Prevention")

        st.markdown(
            f"**Burnout Prevention Active:** "
            f"`{debug.get('whale_burnout_prevention_active', '—')}`"
        )

        st.markdown(
            f"**Burnout Risk:** "
            f"`{debug.get('burnout_risk', '—')}`"
        )

        st.markdown(
            f"**Monetization Fatigue:** "
            f"`{debug.get('monetization_fatigue_level', '—')}`"
        )

        st.markdown(
            f"**Emotional Fatigue:** "
            f"`{debug.get('emotional_fatigue_level', '—')}`"
        )

        st.markdown(
            f"**CTA Fatigue:** "
            f"`{debug.get('cta_fatigue_level', '—')}`"
        )

        st.markdown(
            f"**Pacing Slowdown Required:** "
            f"`{debug.get('pacing_slowdown_required', '—')}`"
        )

        st.markdown(
            f"**Soft Presence Mode:** "
            f"`{debug.get('soft_presence_mode', '—')}`"
        )

        st.markdown(
            f"**Emotional Recovery Mode:** "
            f"`{debug.get('emotional_recovery_mode', '—')}`"
        )

        st.markdown(
            f"**Offer Pressure Reduction:** "
            f"`{debug.get('offer_pressure_reduction', '—')}`"
        )

        st.markdown(
            f"**Immersion Recovery Priority:** "
            f"`{debug.get('immersion_recovery_priority', '—')}`"
        )

        st.markdown(
            f"**Recommended Next Energy:** "
            f"`{debug.get('recommended_next_energy', '—')}`"
        )

        with st.expander("Whale Burnout Profile"):
            st.json(
                debug.get(
                    "whale_burnout_profile",
                    {},
                )
            )

        # ==================================================
        # 3D.20.6.4 — Emotional Dependency Safeguards
        # ==================================================

        st.markdown(
            "## 3D.20.6 Emotional Dependency Safeguards"
        )

        st.markdown(
            f"**Dependency Risk Level:** "
            f"`{debug.get('dependency_risk_level', '—')}`"
        )

        st.markdown(
            f"**Dependency Risk Score:** "
            f"`{debug.get('dependency_risk_score', '—')}`"
        )

        st.markdown(
            f"**Attachment Stabilization Mode:** "
            f"`{debug.get('attachment_stabilization_mode', '—')}`"
        )

        st.markdown(
            f"**Dependency Safe Response Bias:** "
            f"`{debug.get('dependency_safe_response_bias', '—')}`"
        )

        with st.expander(
            "Dependency Safeguard Profile"
        ):
            st.json(
                {
                    "dependency_risk_level": debug.get(
                        "dependency_risk_level"
                    ),
                    "dependency_risk_score": debug.get(
                        "dependency_risk_score"
                    ),
                    "attachment_stabilization_mode": debug.get(
                        "attachment_stabilization_mode"
                    ),
                    "dependency_safe_response_bias": debug.get(
                        "dependency_safe_response_bias"
                    ),
                }
            )
        
        # ==================================================
        # 3D.20.7.4 — Long-Term Emotional Stability
        # ==================================================

        st.markdown(
            "## 3D.20.7 Long-Term Emotional Stability"
        )

        st.markdown(
            f"**Stability Active:** "
            f"`{debug.get('long_term_emotional_stability_active', '—')}`"
        )

        st.markdown(
            f"**Stability Level:** "
            f"`{debug.get('stability_level', '—')}`"
        )

        st.markdown(
            f"**Relationship Rhythm:** "
            f"`{debug.get('relationship_rhythm_state', '—')}`"
        )

        st.markdown(
            f"**Long-Term Response Bias:** "
            f"`{debug.get('long_term_response_bias', '—')}`"
        )

        with st.expander(
            "Long-Term Stability Profile"
        ):
            st.json(
                {
                    "long_term_emotional_stability_active": debug.get(
                        "long_term_emotional_stability_active"
                    ),
                    "stability_level": debug.get(
                        "stability_level"
                    ),
                    "relationship_rhythm_state": debug.get(
                        "relationship_rhythm_state"
                    ),
                    "long_term_response_bias": debug.get(
                        "long_term_response_bias"
                    ),
                }
            )
        
        # ==================================================
        # 3D.20.8 — Relationship Recovery
        # ==================================================

        st.markdown(
            "## 3D.20.8 Relationship Recovery"
        )

        st.markdown(
            f"**Recovery Active:** "
            f"`{debug.get('relationship_recovery_active', '—')}`"
        )

        st.markdown(
            f"**Recovery Risk:** "
            f"`{debug.get('recovery_risk', '—')}`"
        )

        st.markdown(
            f"**Recovery Mode:** "
            f"`{debug.get('recovery_mode', '—')}`"
        )

        st.markdown(
            f"**Reduce Pressure:** "
            f"`{debug.get('reduce_pressure', '—')}`"
        )

        st.markdown(
            f"**Increase Presence:** "
            f"`{debug.get('increase_presence', '—')}`"
        )

        st.markdown(
            f"**CTA Suppression:** "
            f"`{debug.get('recovery_cta_suppression', '—')}`"
        )

        with st.expander(
            "Relationship Recovery Profile"
        ):
            st.json(
                {
                    "relationship_recovery_active": debug.get(
                        "relationship_recovery_active"
                    ),
                    "recovery_risk": debug.get(
                        "recovery_risk"
                    ),
                    "recovery_mode": debug.get(
                        "recovery_mode"
                    ),
                    "reduce_pressure": debug.get(
                        "reduce_pressure"
                    ),
                    "increase_presence": debug.get(
                        "increase_presence"
                    ),
                    "recovery_cta_suppression": debug.get(
                        "recovery_cta_suppression"
                    ),
                    "relationship_recovery_result": debug.get(
                        "relationship_recovery_result"
                    ),
                }
            )
        
                # ==================================================
        # 3D.20.9 — Advanced Intimacy Governance
        # ==================================================

        st.markdown(
            "## 3D.20.9 Advanced Intimacy Governance"
        )

        st.markdown(
            f"**Governance Active:** "
            f"`{debug.get('advanced_intimacy_governance_active', '—')}`"
        )

        st.markdown(
            f"**Premium Intimacy Allowed:** "
            f"`{debug.get('premium_intimacy_allowed', '—')}`"
        )

        st.markdown(
            f"**Escalation Allowed:** "
            f"`{debug.get('intimacy_escalation_allowed', '—')}`"
        )

        st.markdown(
            f"**Governance Mode:** "
            f"`{debug.get('intimacy_governance_mode', '—')}`"
        )

        st.markdown(
            f"**Escalation Ceiling:** "
            f"`{debug.get('intimacy_escalation_ceiling', '—')}`"
        )

        st.markdown(
            f"**Governance Reason:** "
            f"`{debug.get('governance_reason', '—')}`"
        )

        with st.expander(
            "Advanced Intimacy Governance Profile"
        ):
            st.json(
                {
                    "advanced_intimacy_governance_active": debug.get(
                        "advanced_intimacy_governance_active"
                    ),
                    "premium_intimacy_allowed": debug.get(
                        "premium_intimacy_allowed"
                    ),
                    "intimacy_escalation_allowed": debug.get(
                        "intimacy_escalation_allowed"
                    ),
                    "intimacy_governance_mode": debug.get(
                        "intimacy_governance_mode"
                    ),
                    "intimacy_escalation_ceiling": debug.get(
                        "intimacy_escalation_ceiling"
                    ),
                    "governance_reason": debug.get(
                        "governance_reason"
                    ),
                    "advanced_intimacy_governance_result": debug.get(
                        "advanced_intimacy_governance_result"
                    ),
                }
            )
        
                # ==================================================
        # 3D.20.10 — Final Relationship Intelligence
        # ==================================================

        st.markdown(
            "## 3D.20.10 Final Relationship Intelligence"
        )

        st.markdown(
            f"**Relationship Intelligence Active:** "
            f"`{debug.get('final_relationship_intelligence_active', '—')}`"
        )

        st.markdown(
            f"**Relationship Protection Active:** "
            f"`{debug.get('relationship_protection_active', '—')}`"
        )

        st.markdown(
            f"**Master Relationship Mode:** "
            f"`{debug.get('master_relationship_mode', '—')}`"
        )

        st.markdown(
            f"**Relationship Override Active:** "
            f"`{debug.get('relationship_override_active', '—')}`"
        )

        st.markdown(
            f"**Runtime Summary:** "
            f"`{debug.get('relationship_runtime_summary', '—')}`"
        )

        st.markdown(
            f"**Behavior Directive:** "
            f"`{debug.get('relationship_behavior_directive', '—')}`"
        )

        with st.expander(
            "Final Relationship Intelligence Profile"
        ):
            st.json(
                {
                    "final_relationship_intelligence_active": debug.get(
                        "final_relationship_intelligence_active"
                    ),
                    "relationship_protection_active": debug.get(
                        "relationship_protection_active"
                    ),
                    "master_relationship_mode": debug.get(
                        "master_relationship_mode"
                    ),
                    "relationship_override_active": debug.get(
                        "relationship_override_active"
                    ),
                    "relationship_runtime_summary": debug.get(
                        "relationship_runtime_summary"
                    ),
                    "relationship_behavior_directive": debug.get(
                        "relationship_behavior_directive"
                    ),
                    "final_relationship_intelligence_result": debug.get(
                        "final_relationship_intelligence_result"
                    ),
                }
            )

        st.markdown("### Monetization")

        st.write(
            f"**Send Offer:** "
            f"`{debug.get('send_offer', False)}`"
        )

        st.write(
            f"**Close Ready:** "
            f"`{_deep_get(debug, ['route', 'classifier_result', 'close_ready'], False)}`"
        )

        st.write(
            f"**Buying Intent:** "
            f"`{_deep_get(debug, ['route', 'classifier_result', 'buying_intent'], False)}`"
        )

        st.markdown("---")

        with st.expander("Full Debug Data"):
            st.json(debug)
