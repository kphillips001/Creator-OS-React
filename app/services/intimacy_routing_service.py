from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class IntimacyRoutingService:

    """
    3D.10.7

    Controls live intimacy routing behavior.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

    def determine_route(
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

        safe_to_escalate = (
            profile.get(
                "safe_to_escalate",
                False,
            )
        )

        if intimacy_tier == 0:

            route = "SOFT_FLIRT"

            escalation_style = (
                "LIGHT_TEASE_ONLY"
            )

            allow_explicit = False

            allow_premium_sexting = False

        elif intimacy_tier == 1:

            route = "WARM_FLIRT"

            escalation_style = (
                "MILD_INTIMACY"
            )

            allow_explicit = False

            allow_premium_sexting = False

        elif intimacy_tier == 2:

            route = "BUYER_INTIMACY"

            escalation_style = (
                "EMOTIONAL_SEXUAL_TENSION"
            )

            allow_explicit = (
                safe_to_escalate
            )

            allow_premium_sexting = False

        else:

            route = "VIP_INTIMACY"

            escalation_style = (
                "PREMIUM_PERSONALIZED"
            )

            allow_explicit = True

            allow_premium_sexting = True

        return {
            "success": True,

            "fanvue_user_id": fanvue_user_id,

            "route": route,

            "escalation_style": (
                escalation_style
            ),

            "allow_explicit": (
                allow_explicit
            ),

            "allow_premium_sexting": (
                allow_premium_sexting
            ),

            "intimacy_tier": (
                intimacy_tier
            ),

            "safe_to_escalate": (
                safe_to_escalate
            ),
        }
