from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


class BuyerMomentumService:

    """
    3D.10.12

    Tracks active buyer momentum.
    """

    def __init__(self):

        self.profile_service = (
            IntimacyProfileService()
        )

    def calculate_momentum(
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

        confidence = (
            profile.get(
                "spender_confidence",
                "LOW",
            )
        )

        recent_purchase = (
            profile.get(
                "recent_purchase_active",
                False,
            )
        )

        recent_tip = (
            profile.get(
                "recent_tip_active",
                False,
            )
        )

        score = 0

        score += intimacy_tier * 20

        if confidence == "HIGH":
            score += 40

        if recent_purchase:
            score += 25

        if recent_tip:
            score += 15

        momentum = "LOW"

        if score >= 50:
            momentum = "MEDIUM"

        if score >= 90:
            momentum = "HIGH"

        if score >= 120:
            momentum = "HOT"

        return {

            "success": True,

            "fanvue_user_id": (
                fanvue_user_id
            ),

            "momentum_score": score,

            "buyer_momentum": momentum,

            "safe_for_escalation": (
                momentum in [
                    "HIGH",
                    "HOT",
                ]
            ),

            "priority_conversion_window": (
                momentum == "HOT"
            ),
        }
