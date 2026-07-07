class UserValueService:
    def determine_user_value(self, memory: dict) -> str:
        memory = memory or {}

        total_spent_cents = memory.get("total_spent_cents", 0) or 0
        purchase_count = memory.get("purchase_count", 0) or 0
        tip_count = memory.get("tip_count", 0) or 0
        avg_spend_cents = memory.get("avg_spend_cents", 0) or 0
        max_single_purchase_cents = memory.get("max_single_purchase_cents", 0) or 0
        message_count = memory.get("message_count", 0) or 0
        exclusive_interest_count = memory.get("exclusive_interest_count", 0) or 0
        closing_questions_count = memory.get("closing_questions_count", 0) or 0
        price_questions_count = memory.get("price_questions_count", 0) or 0

        # Whale: very high spend or repeated strong buying behavior
        if (
            total_spent_cents >= 50000
            or avg_spend_cents >= 15000
            or max_single_purchase_cents >= 25000
            or (purchase_count >= 5 and total_spent_cents >= 30000)
        ):
            return "whale"

        # Buyer: already monetized meaningfully
        if (
            purchase_count >= 1
            or tip_count >= 1
            or total_spent_cents >= 5000
        ):
            return "buyer"

        # Warm: engaged AND showing at least some purchase-style interest
        # Do not make pure chatter "warm" just because message_count is high.
        if (
            exclusive_interest_count >= 1
            or closing_questions_count >= 1
            or price_questions_count >= 1
            or message_count >= 12
        ):
            return "warm"

        return "cold"

    def is_whale(self, memory: dict) -> bool:
        return self.determine_user_value(memory) == "whale"

    def determine_user_type(self, memory: dict) -> str:
        memory = memory or {}

        # Future Fanvue/API-backed fields
        if memory.get("is_subscriber") is True:
            return "subscriber"
        if memory.get("is_follower") is True:
            return "follower"

        # Flexible fallback fields in case naming changes later
        relationship_status = (memory.get("relationship_status") or "").strip().lower()
        if relationship_status == "subscriber":
            return "subscriber"
        if relationship_status == "follower":
            return "follower"

        subscription_status = (memory.get("subscription_status") or "").strip().lower()
        if subscription_status in ["active", "subscriber", "subscribed"]:
            return "subscriber"

        follow_status = (memory.get("follow_status") or "").strip().lower()
        if follow_status in ["follower", "following"]:
            return "follower"

        return "unknown"

    def evaluate_attention(self, memory: dict) -> dict:
        memory = memory or {}

        user_type = self.determine_user_type(memory)
        user_value_tier = self.determine_user_value(memory)

        total_spent_cents = memory.get("total_spent_cents", 0) or 0
        purchase_count = memory.get("purchase_count", 0) or 0
        tip_count = memory.get("tip_count", 0) or 0
        message_count = memory.get("message_count", 0) or 0
        offers_shown_count = memory.get("offers_shown_count", 0) or 0
        intent_score = memory.get("intent_score", 0) or 0
        exclusive_interest_count = memory.get("exclusive_interest_count", 0) or 0
        closing_questions_count = memory.get("closing_questions_count", 0) or 0
        price_questions_count = memory.get("price_questions_count", 0) or 0
        signals = memory.get("intent_signals", []) or []

        normalized_signals = {str(sig).strip().lower() for sig in signals if sig}
        flags = []

        # Neutral starting point
        score = 50

        # Soft bias only — behavior still wins
        if user_type == "follower":
            score -= 8
            flags.append("follower_bias_low_efficiency")
        elif user_type == "subscriber":
            score += 6
            flags.append("subscriber_bias_higher_value")
        else:
            flags.append("user_type_unknown")

        # Existing monetization = strong positive
        if purchase_count >= 1:
            score += 22
            flags.append("has_purchase_history")

        if tip_count >= 1:
            score += 8
            flags.append("has_tip_history")

        if total_spent_cents >= 5000:
            score += 10
            flags.append("meaningful_spend_history")

        if total_spent_cents >= 20000:
            score += 10
            flags.append("high_spend_history")

        # Buying / closing behavior
        if intent_score >= 70:
            score += 18
            flags.append("hot_intent")
        elif intent_score >= 30:
            score += 10
            flags.append("medium_intent")
        elif intent_score <= 10 and message_count >= 6:
            score -= 12
            flags.append("low_intent_with_high_chat_volume")

        if price_questions_count >= 1:
            score += 8
            flags.append("price_question_behavior")

        if closing_questions_count >= 1:
            score += 10
            flags.append("closing_question_behavior")

        if exclusive_interest_count >= 1:
            score += 6
            flags.append("exclusive_interest_behavior")

        if "send_request" in normalized_signals:
            score += 8
            flags.append("send_request_signal")

        if "best_request" in normalized_signals:
            score += 12
            flags.append("best_request_signal")

        if "closing_intent" in normalized_signals:
            score += 10
            flags.append("closing_intent_signal")

        if "repeat_price_question" in normalized_signals:
            score += 8
            flags.append("repeat_price_question_signal")

        if "continued_interest" in normalized_signals:
            score += 6
            flags.append("continued_interest_signal")

        # Time-waster style patterns
        if message_count >= 8 and purchase_count == 0 and tip_count == 0:
            score -= 14
            flags.append("high_chat_no_purchase")

        if message_count >= 10 and offers_shown_count >= 2 and purchase_count == 0:
            score -= 14
            flags.append("chatty_after_multiple_offers_no_purchase")

        if offers_shown_count >= 3 and intent_score < 30 and purchase_count == 0:
            score -= 12
            flags.append("multiple_offers_low_intent")

        if (
            message_count >= 8
            and price_questions_count == 0
            and closing_questions_count == 0
            and exclusive_interest_count == 0
            and purchase_count == 0
            and tip_count == 0
        ):
            score -= 18
            flags.append("chatty_no_progress")

        # Extra compression for very obvious empty chatter users
        if (
            message_count >= 10
            and intent_score <= 10
            and offers_shown_count >= 1
            and purchase_count == 0
            and tip_count == 0
            and price_questions_count == 0
            and closing_questions_count == 0
            and exclusive_interest_count == 0
        ):
            score -= 10
            flags.append("persistent_low_value_chatter")

        # Protect high-value users from getting misclassified too easily
        if user_value_tier == "whale":
            score += 25
            flags.append("whale_protection")
        elif user_value_tier == "buyer":
            score += 18
            flags.append("buyer_protection")
        elif user_value_tier == "warm":
            score += 4
            flags.append("warm_user_boost")

        # Clamp
        score = max(0, min(100, score))

        if score >= 75:
            attention_tier = "high"
        elif score >= 45:
            attention_tier = "medium"
        else:
            attention_tier = "low"

        if score < 45:
            effort_mode = "compressed"
        elif score < 75:
            effort_mode = "balanced"
        else:
            effort_mode = "full"

        return {
            "user_type": user_type,
            "user_value_tier": user_value_tier,
            "value_score": score,
            "attention_tier": attention_tier,
            "effort_mode": effort_mode,
            "timewaster_flags": list(dict.fromkeys(flags)),
        }

    def is_time_waster(self, memory: dict) -> bool:
        result = self.evaluate_attention(memory)
        return result["attention_tier"] == "low"