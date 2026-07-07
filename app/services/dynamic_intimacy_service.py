from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class DynamicIntimacyService:

    """
    3D.10.11

    Runtime intimacy escalation engine.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

    def determine_runtime_state(
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

        confidence = (
            profile.get(
                "spender_confidence",
                "LOW",
            )
        )

        intimacy_tier = (
            profile.get(
                "intimacy_tier",
                0,
            )
        )

        should_suppress = (
            profile.get(
                "should_suppress_mass_ppv",
                False,
            )
        )

        runtime_mode = "SOFT_FLIRT"

        if intimacy_tier >= 2:

            runtime_mode = (
                "EMOTIONAL_SEXUAL_TENSION"
            )

        if (
            intimacy_tier >= 3
            and confidence == "HIGH"
        ):

            runtime_mode = (
                "PREMIUM_INTIMACY"
            )

        if should_suppress:

            runtime_mode = (
                "RELATIONSHIP_NURTURE"
            )

        escalation_allowed = (
            intimacy_tier >= 1
        )

        return {

            "success": True,

            "fanvue_user_id": (
                fanvue_user_id
            ),

            "runtime_mode": runtime_mode,

            "intimacy_tier": intimacy_tier,

            "spender_confidence": confidence,

            "escalation_allowed": (
                escalation_allowed
            ),

            "mass_ppv_suppressed": (
                should_suppress
            ),

            "premium_mode": (
                runtime_mode
                == "PREMIUM_INTIMACY"
            ),
        }
