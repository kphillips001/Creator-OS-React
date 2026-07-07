from datetime import datetime, timedelta, timezone

from app.repositories.memory_repository import update_memory_fields

class BuyerSessionService:
    """
    Controls what should happen next during an active buyer session.

    Current behavior:
    - session_start -> bridge message
    - bridge_message -> PPV
    - ppv -> wait
    - wait expired -> bridge message
    - max PPVs -> cooldown
    """

    MAX_PPVS_PER_SESSION = 3
    
    # --------------------------------------------------
    # DECISION ENGINE
    # --------------------------------------------------

    def decide_next_action(self, memory: dict) -> dict:
        if not memory.get("buyer_session_active"):
            return {
                "action": "wait",
                "reason": "no_active_buyer_session",
            }

        ppv_count = memory.get("buyer_session_ppv_count", 0) or 0
        last_action = memory.get("buyer_session_last_action")

        if ppv_count >= self.MAX_PPVS_PER_SESSION:
            return {
                "action": "cooldown",
                "reason": "max_ppvs_reached",
            }

        if last_action == "session_start":
            return {
                "action": "send_bridge_message",
                "reason": "connection_before_next_ppv",
            }

        if last_action == "bridge_message":
            return {
                "action": "send_ppv",
                "reason": "bridge_completed",
            }

        if last_action == "ppv":
            now = datetime.now(timezone.utc)
            wait_until = memory.get("buyer_session_wait_until")

            if wait_until:
                if wait_until.tzinfo is None:
                    wait_until = wait_until.astimezone()

                wait_until = wait_until.astimezone(timezone.utc)

            print(f"[WAIT DEBUG] now={now} | wait_until={wait_until}")

            if wait_until and now < wait_until:
                print("[SESSION ACTION] WAIT MODE")
                return {
                    "action": "wait",
                    "reason": "cooldown_active",
                }

            print("[SESSION ACTION] RESUME AFTER WAIT")
            return {
                "action": "send_bridge_message",
                "reason": "resume_after_wait",
            }

        if last_action == "wait":
            return {
                "action": "send_bridge_message",
                "reason": "resume_after_wait",
            }

        if last_action == "cooldown":
            return {
                "action": "cooldown",
                "reason": "session_in_cooldown",
            }

        return {
            "action": "send_bridge_message",
            "reason": "default_session_bridge",
        }

    # --------------------------------------------------
    # STATE UPDATE HELPERS
    # --------------------------------------------------

    def mark_bridge_sent(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ):
        now = datetime.utcnow()

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_last_action": "bridge_message",
            "buyer_session_last_action_at": now,
            "buyer_session_last_message_at": now,
        })

    def mark_ppv_sent(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        current_ppv_count: int,
    ):
        now = datetime.utcnow()

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_last_action": "ppv",
            "buyer_session_last_action_at": now,
            "buyer_session_ppv_count": current_ppv_count + 1,
            "buyer_session_last_ppv_at": now,
        })

    def mark_wait(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
    ):
        now = datetime.utcnow()

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_last_action": "wait",
            "buyer_session_last_action_at": now,
        })

    def mark_cooldown(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        cooldown_minutes: int = 30,
    ):
        now = datetime.utcnow()
        cooldown_until = now + timedelta(minutes=cooldown_minutes)

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_last_action": "cooldown",
            "buyer_session_last_action_at": now,
            "buyer_session_cooldown_until": cooldown_until,
            "buyer_session_active": False,
            "buyer_session_ended_at": now,
        })

    def start_wait_timer(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        memory: dict,
    ):
        now = datetime.utcnow()

        intent_score = memory.get("intent_score", 0)
        is_hot = memory.get("is_hot_buyer", False)

        if is_hot:
            wait_seconds = 60
        elif intent_score >= 60:
            wait_seconds = 180
        elif intent_score >= 30:
            wait_seconds = 300
        else:
            wait_seconds = 900

        wait_until = now + timedelta(seconds=wait_seconds)

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_last_action": "wait",
            "buyer_session_last_action_at": now,
            "buyer_session_wait_until": wait_until,
        })

        print(f"[WAIT TIMER] set for {wait_seconds}s until {wait_until}")

    def start_or_refresh_session(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        memory: dict,
    ):
        """
        Starts a buyer session if one is not active.
        If already active, keeps the session alive without resetting progress.
        """

        now = datetime.utcnow()

        if memory.get("buyer_session_active"):
            print("[BUYER SESSION] already active — refreshing last action time")

            update_memory_fields(fanvue_account_id, fanvue_user_id, {
                "buyer_session_last_action_at": now,
            })

            return {
                "success": True,
                "status": "session_refreshed",
            }

        print("[BUYER SESSION START] starting new buyer session")

        update_memory_fields(fanvue_account_id, fanvue_user_id, {
            "buyer_session_active": True,
            "buyer_session_started_at": now,
            "buyer_session_last_action": "session_start",
            "buyer_session_last_action_at": now,
            "buyer_session_step": 1,
            "buyer_session_ppv_count": 0,
        })

        return {
            "success": True,
            "status": "session_started",
        }

    def get_session_offer_tier(self, memory: dict) -> dict:
        """
        Step-based offer escalation during buyer session.

        Step 1 → TEASE
        Step 2 → VIP
        Step 3+ → PREMIUM
        """

        session_step = memory.get("buyer_session_step", 1) or 1
        buyer_tier = memory.get("buyer_tier")
        user_value_tier = memory.get("user_value_tier")
        is_whale = memory.get("is_whale", False)

        print(f"[SESSION STEP LOGIC] step={session_step}")

        if is_whale or user_value_tier == "high" or buyer_tier in ("HIGH_VALUE", "WHALE"):
            return {
                "offer_tier": "premium_offer",
                "classification": "PREMIUM",
                "caption_tone": "high_intent",
                "price_multiplier": 1.5,
                "reason": "high_value_override",
            }

        if session_step == 1:
            return {
                "offer_tier": "tease_offer",
                "classification": "TEASE",
                "caption_tone": "soft_tease",
                "price_multiplier": 0.6,
                "reason": "step_1_tease",
            }

        if session_step == 2:
            return {
                "offer_tier": "vip_offer",
                "classification": "VIP",
                "caption_tone": "playful_push",
                "price_multiplier": 1.0,
                "reason": "step_2_vip",
            }

        return {
            "offer_tier": "premium_offer",
            "classification": "PREMIUM",
            "caption_tone": "high_intent",
            "price_multiplier": 1.3,
            "reason": "step_3_premium",
        }

    def detect_close_intent(
        self,
        message: str,
        memory: dict,
        classifier_result: dict | None = None,
    ) -> dict:
        """
        19D / 19M — GPT-based close detection.

        No hard-coded user phrases.
        Uses precomputed classifier_result to avoid duplicate GPT calls.
        """

        result = classifier_result or {}

        buyer_session_active = bool(memory.get("buyer_session_active", False))
        buyer_session_step = int(memory.get("buyer_session_step") or 0)
        last_action = memory.get("buyer_session_last_action")

        ppv_has_been_presented = (
            buyer_session_active
            and buyer_session_step >= 3
            and last_action in ["ppv_offer_presented", "ppv", "wait"]
        )

        close_ready = bool(result.get("close_ready", False))
        recommended_action = result.get("recommended_action")
        confidence = float(result.get("confidence", 0.0) or 0.0)

        user_state = result.get("user_state")

        should_close = (
            ppv_has_been_presented
            and confidence >= 0.6
            and (
                close_ready
                or recommended_action == "close"
                or user_state == "ready_to_buy"
                or user_state == "converted"
            )
        )

        return {
            "should_close": should_close,
            "reason": "gpt_close_detection" if should_close else "no_gpt_close_intent",
            "classifier_result": result,
        }

    def detect_exit_intent(
        self,
        message: str,
        memory: dict,
        classifier_result: dict | None = None,
    ) -> dict:
        """
        19D / 19M — GPT-based exit detection.

        No hard-coded user phrases.
        Uses precomputed classifier_result to avoid duplicate GPT calls.
        """

        result = classifier_result or {}

        buyer_session_active = bool(memory.get("buyer_session_active", False))
        buyer_session_ppv_count = int(memory.get("buyer_session_ppv_count") or 0)

        if not buyer_session_active:
            return {
                "should_exit": False,
                "reason": "no_active_buyer_session",
                "exit_type": None,
                "classifier_result": result,
            }

        exit_ready = bool(result.get("exit_ready", False))
        user_state = result.get("user_state")
        recommended_action = result.get("recommended_action")
        confidence = float(result.get("confidence", 0.0) or 0.0)

        if buyer_session_ppv_count >= self.MAX_PPVS_PER_SESSION:
            return {
                "should_exit": True,
                "reason": "max_ppvs_reached",
                "exit_type": "cooldown",
                "classifier_result": result,
            }

        if (
            confidence >= 0.6
            and (
                user_state == "converted"
                or (exit_ready and user_state != "rejecting")
            )
        ):
            return {
                "should_exit": True,
                "reason": "gpt_detected_conversion",
                "exit_type": "converted",
                "classifier_result": result,
            }

        if (
            confidence >= 0.6
            and (
                recommended_action == "exit"
                or user_state == "rejecting"
            )
        ):
            return {
                "should_exit": True,
                "reason": "gpt_detected_rejection",
                "exit_type": "cooldown",
                "classifier_result": result,
            }

        return {
            "should_exit": False,
            "reason": "session_should_continue",
            "exit_type": None,
            "classifier_result": result,
        }

    def exit_session(
        self,
        fanvue_account_id: int,
        fanvue_user_id: int,
        exit_type: str,
        reason: str,
    ):
        """
        STEP 7 — Ends buyer session and returns user to normal routing.
        """

        now = datetime.utcnow()

        updates = {
            "buyer_session_active": False,
            "buyer_session_step": 0,
            "buyer_session_last_action": f"session_exit_{exit_type}",
            "buyer_session_last_action_at": now,
            "buyer_session_ended_at": now,
            "buyer_session_wait_until": None,
            "conversation_mode": "casual",
            "current_route": "chat",
            "last_route": "chat",
            "last_route_reason": reason,
        }

        if exit_type == "converted":
            updates["last_ppv_purchase_at"] = now
            updates["buyer_session_cooldown_until"] = None

        else:
            updates["buyer_session_cooldown_until"] = now + timedelta(minutes=30)

        update_memory_fields(
            fanvue_account_id,
            fanvue_user_id,
            updates,
        )

        print(f"[15H-X STEP 7 EXIT] type={exit_type} | reason={reason}")

        return {
            "success": True,
            "exit_type": exit_type,
            "reason": reason,
            "updates": updates,
        }