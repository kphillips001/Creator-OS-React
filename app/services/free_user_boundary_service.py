from random import choice

from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class FreeUserBoundaryService:

    """
    3D.10.8

    Prevents free users from consuming
    premium intimacy behavior.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

        self.boundary_responses = [

            (
                "I save the really naughty side "
                "of me for the people who spoil me 😘"
            ),

            (
                "Mmm maybe you need to unlock "
                "that side of me first 💋"
            ),

            (
                "Careful... that version of me "
                "is reserved for my good boys 😏"
            ),

            (
                "You’re tempting me... but I "
                "like being spoiled first 😘"
            ),

            (
                "That’s premium behavior baby 😇"
            ),
        ]

    def enforce_boundary(
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

        if intimacy_tier >= 2:

            return {
                "success": True,
                "boundary_triggered": False,
                "allow_escalation": True,
                "response": None,
            }

        response = choice(
            self.boundary_responses
        )

        return {
            "success": True,

            "boundary_triggered": True,

            "allow_escalation": False,

            "response": response,

            "intimacy_tier": intimacy_tier,

            "spender_confidence": (
                profile.get(
                    "spender_confidence"
                )
            ),
        }
