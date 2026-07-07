from app.services.spend_intelligence_service import (
    SpendIntelligenceService,
)


class IntimacyEligibilityService:
    """
    3D.10 — Intimacy Eligibility Tiers

    Converts realtime spend intelligence into explicit
    intimacy access rules for DecisionEngine/GPT routing.
    """

    def __init__(self):
        self.spend_service = SpendIntelligenceService()

    def get_intimacy_profile(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):
        spend_profile = (
            self.spend_service
            .get_spend_intelligence(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        if not spend_profile.get("success"):
            return self._non_spender_profile(
                fanvue_user_id=fanvue_user_id,
                reason=spend_profile.get("reason"),
            )

        tier = int(
            spend_profile.get("intimacy_tier") or 0
        )

        if tier <= 0:
            return self._tier_0_profile(
                spend_profile
            )

        if tier == 1:
            return self._tier_1_profile(
                spend_profile
            )

        if tier == 2:
            return self._tier_2_profile(
                spend_profile
            )

        return self._tier_3_profile(
            spend_profile
        )

    def _tier_0_profile(self, spend_profile: dict):
        return {
            **spend_profile,
            "intimacy_allowed": True,
            "explicit_allowed": False,
            "adult_llm_allowed": False,
            "premium_sexting_allowed": False,
            "max_intimacy_level": "tease_only",
            "response_style": "playful_withholding",
            "boundary_message": (
                "I save the really naughty side of me "
                "for the people who spoil me 😘"
            ),
            "allowed_behaviors": [
                "playful_flirting",
                "teasing",
                "suggestive_behavior",
                "soft_sexual_tension",
            ],
            "blocked_behaviors": [
                "explicit_dirty_talk",
                "premium_sexting",
                "high_effort_erotic_engagement",
            ],
        }

    def _tier_1_profile(self, spend_profile: dict):
        return {
            **spend_profile,
            "intimacy_allowed": True,
            "explicit_allowed": False,
            "adult_llm_allowed": False,
            "premium_sexting_allowed": False,
            "max_intimacy_level": "warm_tease",
            "response_style": "warmer_personalized_tease",
            "allowed_behaviors": [
                "warmer_flirting",
                "stronger_tension",
                "mild_intimate_teasing",
                "personalized_engagement",
            ],
            "blocked_behaviors": [
                "instant_extreme_escalation",
                "full_premium_sexting",
            ],
        }

    def _tier_2_profile(self, spend_profile: dict):
        return {
            **spend_profile,
            "intimacy_allowed": True,
            "explicit_allowed": True,
            "adult_llm_allowed": False,
            "premium_sexting_allowed": False,
            "max_intimacy_level": "premium_tease",
            "response_style": "deeper_emotional_intimacy",
            "allowed_behaviors": [
                "deeper_intimacy",
                "emotionally_charged_flirting",
                "premium_romantic_tension",
                "personalized_dirty_talk_light",
            ],
            "blocked_behaviors": [
                "hardcore_jump_without_warmup",
                "unlimited_explicit_chat",
            ],
        }

    def _tier_3_profile(self, spend_profile: dict):
        return {
            **spend_profile,
            "intimacy_allowed": True,
            "explicit_allowed": True,
            "adult_llm_allowed": True,
            "premium_sexting_allowed": True,
            "max_intimacy_level": "premium_intimacy",
            "response_style": "premium_high_personalization",
            "allowed_behaviors": [
                "highest_priority_engagement",
                "premium_emotional_continuity",
                "premium_intimacy_mode",
                "high_personalization",
                "premium_retention_behavior",
            ],
            "blocked_behaviors": [
                "generic_mass_message_feel",
                "emotional_drop_after_purchase",
            ],
        }

    def _non_spender_profile(
        self,
        fanvue_user_id: str,
        reason: str = None,
    ):
        return {
            "success": True,
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": "NON_BUYER",
            "intimacy_tier": 0,
            "intimacy_allowed": True,
            "explicit_allowed": False,
            "adult_llm_allowed": False,
            "premium_sexting_allowed": False,
            "max_intimacy_level": "tease_only",
            "response_style": "playful_withholding",
            "boundary_message": (
                "I save the really naughty side of me "
                "for the people who spoil me 😘"
            ),
            "reason": reason,
        }
