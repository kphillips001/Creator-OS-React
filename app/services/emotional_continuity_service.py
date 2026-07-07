from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)

from app.services.buyer_momentum_service import (
    BuyerMomentumService,
)


class EmotionalContinuityService:

    """
    3D.10.13

    Prevents emotional whiplash and
    post-purchase emotional collapse.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

        self.momentum_service = (
            BuyerMomentumService()
        )

    def evaluate_continuity(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):

        profile = (
            self.profile_service.build_profile(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        momentum = (
            self.momentum_service
            .calculate_momentum(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        intimacy_tier = (
            profile.get(
                "intimacy_tier",
                0,
            )
        )

        buyer_momentum = (
            momentum.get(
                "buyer_momentum",
                "LOW",
            )
        )

        continuity_mode = (
            "LIGHT_CONTINUITY"
        )

        if intimacy_tier >= 2:

            continuity_mode = (
                "EMOTIONAL_CONTINUITY"
            )

        if buyer_momentum in [
            "HIGH",
            "HOT",
        ]:

            continuity_mode = (
                "PREMIUM_CONTINUITY"
            )

        protections = [

            "prevent_emotional_dropoff",
            "maintain_personality_consistency",
            "prevent_hard_sell_transitions",
            "preserve_emotional_warmth",
            "maintain_escalation_memory",
        ]

        return {

            "success": True,

            "fanvue_user_id": (
                fanvue_user_id
            ),

            "continuity_mode": (
                continuity_mode
            ),

            "buyer_momentum": (
                buyer_momentum
            ),

            "intimacy_tier": (
                intimacy_tier
            ),

            "protections": protections,

            "relationship_stability": (
                continuity_mode
                != "LIGHT_CONTINUITY"
            ),
        }
