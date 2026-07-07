from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class WhaleProtectionService:

    """
    3D.10.10

    Protects high-value buyers from:
    - generic routing
    - cheap mass behavior
    - low-effort engagement
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

    def build_whale_protection(
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

        intimacy_tier = (
            profile.get(
                "intimacy_tier",
                0,
            )
        )

        is_whale = (
            intimacy_tier >= 3
        )

        if not is_whale:

            return {

                "success": True,

                "is_whale": False,

                "priority_mode": False,
            }

        protections = [

            "disable_generic_mass_ppv",
            "priority_response_queue",
            "premium_continuity_mode",
            "enhanced_memory_weight",
            "soft_retention_monitoring",
            "priority_emotional_routing",
        ]

        return {

            "success": True,

            "is_whale": True,

            "priority_mode": True,

            "protections": protections,

            "max_personalization": True,

            "drop_risk_prevention": True,
        }
