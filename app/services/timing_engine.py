from datetime import datetime, timezone


class TimingEngine:
    """
    Timing Engine v1

    Purpose:
    - Decide WHEN to send an offer
    - Decide WHEN to wait
    - Decide WHEN to warm up
    - Decide WHEN a post-offer nudge is allowed

    IMPORTANT:
    - This version is intentionally simple and safe
    - It does NOT replace OfferService
    - It does NOT replace PostOfferService
    - It only centralizes timing decisions
    """

    def evaluate_timing(self, user_memory: dict | None, intent_result: dict | None) -> dict:
        user_memory = user_memory or {}
        intent_result = intent_result or {}

        buyer_tier = intent_result.get("tier", "low")
        intent_score = intent_result.get("score", 0) or 0
        signals = intent_result.get("signals", []) or []

        is_whale = user_memory.get("is_whale", False)
        is_subscriber = user_memory.get("is_subscriber", False)
        offers_shown_count = user_memory.get("offers_shown_count", 0) or 0
        messages_since_last_offer = user_memory.get("messages_since_last_offer", 0) or 0
        offer_state = user_memory.get("offer_state")
        last_offer_timestamp = user_memory.get("last_offer_timestamp")
        last_nudge_timestamp = user_memory.get("last_nudge_timestamp")
        nudge_count = user_memory.get("nudge_count", 0) or 0

        # ✅ subscriber-aware timing context
        subscriber_profile = (user_memory.get("subscriber_profile", "none") or "none").strip()
        behavior_config = user_memory.get("behavior_config", {}) or {}
        pacing_level = behavior_config.get("pacing_level", "normal")
        monetization_pressure = behavior_config.get("monetization_pressure", "medium")

        reason = []
        timing_signals = []

        # =====================================
        # 1. WHALE PROTECTION
        # =====================================
        if is_whale:
            reason.append("User is whale; avoid aggressive offer timing.")
            timing_signals.append("whale_protection")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # =====================================
        # 2. ACTIVE POST-OFFER STATE
        # =====================================
        if offer_state in ["offered", "nudged"]:
            timing_signals.append("active_post_offer_state")

            if nudge_count >= 3:
                reason.append("Max nudges reached.")
                timing_signals.append("max_nudges_reached")
                return {
                    "action": "wait",
                    "send_offer": False,
                    "send_nudge": False,
                    "wait_hours": 24,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            if messages_since_last_offer >= 2:
                reason.append("User re-engaged after offer; nudge allowed.")
                timing_signals.append("nudge_window_open")
                return {
                    "action": "send_nudge",
                    "send_offer": False,
                    "send_nudge": True,
                    "wait_hours": 0,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            reason.append("Post-offer state active, but not enough re-engagement yet.")
            timing_signals.append("nudge_not_ready")
            return {
                "action": "wait",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 12,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # =====================================
        # 3. GPT HIGH-INTENT / CLOSING SIGNALS
        # =====================================
        gpt_result = user_memory.get("gpt_classifier_result", {}) or {}

        gpt_intent_level = gpt_result.get("intent_level")
        gpt_buyer_likelihood = gpt_result.get("buyer_likelihood")
        gpt_close_ready = bool(gpt_result.get("close_ready", False))
        gpt_escalation_ready = bool(gpt_result.get("escalation_ready", False))
        gpt_recommended_action = gpt_result.get("recommended_action")
        gpt_confidence = float(gpt_result.get("confidence", 0.0) or 0.0)

        gpt_hot_timing = (
            gpt_confidence >= 0.6
            and (
                gpt_close_ready
                or gpt_recommended_action in ["offer", "close"]
                or (
                    gpt_intent_level == "high"
                    and gpt_buyer_likelihood == "high"
                )
            )
        )

        if gpt_hot_timing:
            reason.append("GPT high-intent timing signal detected.")
            timing_signals.append("gpt_hot_timing")
            return {
                "action": "send_offer",
                "send_offer": True,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }
        
        # =====================================
        # 4. MEDIUM INTENT
        # =====================================
        if buyer_tier == "medium" or intent_score >= 45:
            if messages_since_last_offer >= 4 or offers_shown_count == 0:
                reason.append("Warm user is ready for offer timing.")
                timing_signals.append("warm_offer_ready")
                return {
                    "action": "send_offer",
                    "send_offer": True,
                    "send_nudge": False,
                    "wait_hours": 0,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            reason.append("Warm user needs a bit more conversation first.")
            timing_signals.append("warm_up_required")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # =====================================
        # 5. LOW / COLD INTENT
        # =====================================

        # NEW + LAPSED subscribers should still be softened here.
        if is_subscriber and subscriber_profile == "NEW_SUBSCRIBER":
            reason.append("New subscriber detected; use softer pacing.")
            timing_signals.append("subscriber_soft_pacing")
            timing_signals.append("subscriber_new_warmup_delay")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 12,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        if is_subscriber and subscriber_profile == "LAPSED_SUBSCRIBER":
            reason.append("Lapsed subscriber detected; re-engage before monetization.")
            timing_signals.append("subscriber_soft_pacing")
            timing_signals.append("subscriber_lapsed_reengagement_first")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 12,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # HIGH_VALUE subscribers should be slower, but not fully blocked forever.
        if (
            is_subscriber
            and subscriber_profile == "HIGH_VALUE_SUBSCRIBER"
            and pacing_level == "slow"
            and monetization_pressure == "low"
        ):
            if messages_since_last_offer >= 3 and intent_score >= 25:
                reason.append("High-value subscriber is warm enough for selective offer timing.")
                timing_signals.append("subscriber_soft_pacing")
                timing_signals.append("high_value_offer_window")
                return {
                    "action": "send_offer",
                    "send_offer": True,
                    "send_nudge": False,
                    "wait_hours": 0,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            reason.append("High-value subscriber detected; use slower selective pacing.")
            timing_signals.append("subscriber_soft_pacing")
            timing_signals.append("high_value_soft_delay")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 12,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # ACTIVE subscribers should NOT be blocked by default.
        # Let them flow into standard follower-like timing when warm enough.
        if is_subscriber and subscriber_profile == "ACTIVE_SUBSCRIBER":
            if offers_shown_count == 0 and intent_score >= 25:
                reason.append("Active subscriber can receive a first offer.")
                timing_signals.append("active_subscriber_first_offer_window")
                return {
                    "action": "send_offer",
                    "send_offer": True,
                    "send_nudge": False,
                    "wait_hours": 0,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            if messages_since_last_offer >= 2 and intent_score >= 20:
                reason.append("Active subscriber is warm enough for standard offer timing.")
                timing_signals.append("active_subscriber_standard_offer_window")
                return {
                    "action": "send_offer",
                    "send_offer": True,
                    "send_nudge": False,
                    "wait_hours": 0,
                    "reason": " | ".join(reason),
                    "signals": timing_signals,
                }

            reason.append("Active subscriber needs a little more conversation first.")
            timing_signals.append("active_subscriber_soft_pacing")
            return {
                "action": "warm_up",
                "send_offer": False,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        # Follower / general non-subscriber cold-to-warm path
        if offers_shown_count == 0 and intent_score >= 25:
            reason.append("Cold-to-warm follower can receive first offer.")
            timing_signals.append("follower_first_offer_window")
            return {
                "action": "send_offer",
                "send_offer": True,
                "send_nudge": False,
                "wait_hours": 0,
                "reason": " | ".join(reason),
                "signals": timing_signals,
            }

        reason.append("User is too cold; continue warming up.")
        timing_signals.append("too_cold_wait")
        return {
            "action": "warm_up",
            "send_offer": False,
            "send_nudge": False,
            "wait_hours": 0,
            "reason": " | ".join(reason),
            "signals": timing_signals,
        }