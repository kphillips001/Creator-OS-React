from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class IntimacySafetyService:

    """
    3D.10.9

    Prevents unsafe escalation pacing.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

    def validate_escalation(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
        requested_style: str,
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

        blocked = []

        if (
            requested_style
            == "HARDCORE_EXPLICIT"
            and intimacy_tier < 3
        ):

            blocked.append(
                "hardcore_requires_whale"
            )

        if (
            requested_style
            == "PREMIUM_SEXTING"
            and not profile.get(
                "premium_sexting_allowed"
            )
        ):

            blocked.append(
                "premium_sexting_locked"
            )

        safe = len(blocked) == 0

        return {

            "success": True,

            "safe_to_escalate": safe,

            "requested_style": (
                requested_style
            ),

            "intimacy_tier": intimacy_tier,

            "blocked_reasons": blocked,

            "allowed_behaviors": (
                profile.get(
                    "allowed_behaviors",
                    [],
                )
            ),
        }
