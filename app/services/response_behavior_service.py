class ResponseBehaviorService:
    """
    15.6 Response Behavior Engine

    Converts GPT classifier output into response behavior instructions
    that can be injected into DecisionEngine / GPT prompts.

    GPT = intelligence layer
    Python = control layer
    """

    def determine_behavior(
        self,
        classifier_result: dict,
        memory: dict = None,
    ) -> dict:
        memory = memory or {}
        classifier_result = classifier_result or {}

        intent_level = classifier_result.get("intent_level", "none")
        buying_intent = classifier_result.get("buying_intent", False)
        close_ready = classifier_result.get("close_ready", False)
        objection_type = classifier_result.get("objection_type", "none")
        recommended_action = classifier_result.get("recommended_action", "chat")
        buyer_likelihood = classifier_result.get("buyer_likelihood", "low")
        effort_mode = memory.get("effort_mode", "high")

        # --------------------------------------------------
        # DEFAULT BEHAVIOR
        # --------------------------------------------------

        behavior = {
            "response_strategy": "chat",
            "pressure_level": "low",
            "tone_mode": "casual",
            "should_sell": False,
            "should_send_offer": False,
            "should_handle_objection": False,
            "should_downgrade_effort": False,
            "behavior_notes": [],
        }

        # --------------------------------------------------
        # 1. CLOSE-READY USERS
        # --------------------------------------------------

        if close_ready or recommended_action == "close":
            behavior.update({
                "response_strategy": "close",
                "pressure_level": "high",
                "tone_mode": "confident",
                "should_sell": True,
                "should_send_offer": True,
                "should_handle_objection": False,
            })

            behavior["behavior_notes"].append(
                "User appears close-ready. Keep response short, confident, and conversion-focused."
            )

        # --------------------------------------------------
        # 2. OBJECTION HANDLING
        # --------------------------------------------------

        elif objection_type and objection_type != "none":
            behavior.update({
                "response_strategy": "handle_objection",
                "pressure_level": "medium",
                "tone_mode": "reassuring",
                "should_sell": False,
                "should_send_offer": False,
                "should_handle_objection": True,
            })

            if objection_type == "price":
                behavior["behavior_notes"].append(
                    "Handle price objection by reinforcing value and exclusivity. Do not discount immediately."
                )

            elif objection_type in ["hesitation", "time"]:
                behavior["pressure_level"] = "low"
                behavior["behavior_notes"].append(
                    "User is hesitant or delaying. Reduce pressure and keep the conversation open."
                )

            elif objection_type == "content_specific":
                behavior["behavior_notes"].append(
                    "User is asking about content/value. Build curiosity without giving everything away."
                )

            elif objection_type == "trust":
                behavior["pressure_level"] = "low"
                behavior["behavior_notes"].append(
                    "User has trust concerns. Reassure softly and avoid hard selling."
                )

            elif objection_type == "technical":
                behavior.update({
                    "response_strategy": "support",
                    "pressure_level": "low",
                    "tone_mode": "helpful",
                    "should_sell": False,
                    "should_send_offer": False,
                })

                behavior["behavior_notes"].append(
                    "User has a technical/support issue. Pause sales behavior and help first."
                )

        # --------------------------------------------------
        # 3. BUILD TENSION / WARM BUYER
        # --------------------------------------------------

        elif recommended_action == "build_tension" or intent_level == "medium":
            behavior.update({
                "response_strategy": "build_tension",
                "pressure_level": "medium",
                "tone_mode": "flirty",
                "should_sell": False,
                "should_send_offer": False,
            })

            behavior["behavior_notes"].append(
                "User shows curiosity. Build tension and curiosity before selling."
            )

        # --------------------------------------------------
        # 4. OFFER-READY USER
        # --------------------------------------------------

        elif recommended_action == "offer" or buying_intent:
            behavior.update({
                "response_strategy": "offer",
                "pressure_level": "medium",
                "tone_mode": "flirty_confident",
                "should_sell": True,
                "should_send_offer": True,
            })

            behavior["behavior_notes"].append(
                "User is offer-ready. Present the offer confidently without over-explaining."
            )

        # --------------------------------------------------
        # 5. LOW INTENT / COLD USER
        # --------------------------------------------------

        elif intent_level in ["none", "low"] or buyer_likelihood == "low":
            behavior.update({
                "response_strategy": "chat",
                "pressure_level": "low",
                "tone_mode": "casual",
                "should_sell": False,
                "should_send_offer": False,
            })

            behavior["behavior_notes"].append(
                "Low-intent user. Keep response casual and avoid selling."
            )

        # --------------------------------------------------
        # 6. TIME-WASTER / LOW EFFORT MODE (APPLIED LAST)
        # --------------------------------------------------

        if effort_mode == "low":
            behavior["should_downgrade_effort"] = True
            behavior["pressure_level"] = "low"
            behavior["should_send_offer"] = False

            if behavior["response_strategy"] != "close":
                behavior["tone_mode"] = "casual"

            behavior["behavior_notes"].append(
                "Low-effort mode active. Keep responses short and reduce investment."
            )

        return behavior