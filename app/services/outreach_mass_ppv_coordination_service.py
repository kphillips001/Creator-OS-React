class OutreachMassPPVCoordinationService:
    """
    Connects Outreach Engine and Mass PPV Engine.

    PURPOSE:
    - Outreach tries to spark conversation.
    - If ignored repeatedly, stop outreach.
    - Ignored users may still receive Mass PPV.
    - Responders get higher monetization priority.
    - Time-wasters get throttled, not endless chat.
    """

    def __init__(
        self,
        max_ignored_outreach_attempts: int = 3,
        max_nonbuyer_chat_messages: int = 8,
        max_ignored_offer_count: int = 2,
    ):
        self.max_ignored_outreach_attempts = max_ignored_outreach_attempts
        self.max_nonbuyer_chat_messages = max_nonbuyer_chat_messages
        self.max_ignored_offer_count = max_ignored_offer_count

    def evaluate(self, user_memory: dict) -> dict:
        user_memory = user_memory or {}
        from app.services.customer_value_attention_service import CustomerValueAttentionService

        supplied_projection = dict(user_memory.get("customer_value_attention") or {})
        if supplied_projection:
            value_attention = supplied_projection
        else:
            value_attention = dict(CustomerValueAttentionService().project(
                behavior=user_memory,
                legacy=user_memory,
            ).to_mapping())

        outreach_attempts = user_memory.get("outreach_attempts", 0) or 0
        outreach_ignore_count = user_memory.get("outreach_ignore_count", 0) or 0
        outreach_response_count = user_memory.get("outreach_response_count", 0) or 0

        purchase_count = (
            value_attention.get("purchaseCount", 0)
            if supplied_projection else user_memory.get("purchase_count", 0)
        ) or 0
        total_spend = float(
            (value_attention.get("lifetimeSpendMinor", 0) / 100.0)
            if supplied_projection else user_memory.get("total_spend", 0)
            or 0
        )

        inbound_message_count = user_memory.get("inbound_message_count", 0) or 0
        ignored_offer_count = user_memory.get("ignored_offer_count", 0) or 0

        is_whale = bool(user_memory.get("is_whale"))
        buyer_tier = (user_memory.get("buyer_tier") or "").lower()
        user_value_tier = (user_memory.get("user_value_tier") or "").lower()

        buyer_session_active = bool(user_memory.get("buyer_session_active"))
        close_ready = bool(user_memory.get("close_ready"))

        canonical_protected = (
            bool(value_attention.get("buyerProtectionApplied"))
            or value_attention.get("retentionPriority") in {"HIGH", "VIP"}
        )
        legacy_protected = (
            is_whale
            or buyer_tier in {"whale", "high_value"}
            or user_value_tier in {"high", "whale"}
        )
        protected_user = (
            canonical_protected
            or (not supplied_projection and legacy_protected)
            or buyer_session_active
            or close_ready
        )

        outreach_exhausted = (
            outreach_attempts >= self.max_ignored_outreach_attempts
            or outreach_ignore_count >= self.max_ignored_outreach_attempts
        )

        responded_to_outreach = outreach_response_count > 0

        has_spent = purchase_count > 0 or total_spend > 0

        time_waster = value_attention.get("timeWasterRisk") == "HIGH" or (
            inbound_message_count >= self.max_nonbuyer_chat_messages
            and not has_spent
        ) or (
            ignored_offer_count >= self.max_ignored_offer_count
            and not has_spent
        )

        allow_outreach = not protected_user and not outreach_exhausted and not time_waster

        allow_mass_ppv = not protected_user

        if responded_to_outreach and not protected_user:
            mass_ppv_priority = "boosted"
        elif outreach_exhausted and not protected_user:
            mass_ppv_priority = "normal"
        elif time_waster and not protected_user:
            mass_ppv_priority = "normal"
        elif not protected_user:
            mass_ppv_priority = "eligible"
        else:
            mass_ppv_priority = "blocked"

        if protected_user:
            action = "protect_user"
        elif time_waster:
            action = "throttle_chat_keep_mass_ppv"
        elif outreach_exhausted:
            action = "stop_outreach_keep_mass_ppv"
        elif responded_to_outreach:
            action = "continue_light_engagement_boost_ppv"
        else:
            action = "allow_outreach_and_mass_ppv"

        return {
            "allow_outreach": allow_outreach,
            "allow_mass_ppv": allow_mass_ppv,
            "mass_ppv_priority": mass_ppv_priority,
            "outreach_exhausted": outreach_exhausted,
            "responded_to_outreach": responded_to_outreach,
            "time_waster": time_waster,
            "protected_user": protected_user,
            "recommended_action": action,
            "customer_value_attention": value_attention,
        }
