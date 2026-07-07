import logging

from app.services.spend_intelligence_service import (
    SpendIntelligenceService,
)


logger = logging.getLogger(__name__)

from app.services.intimacy_eligibility_service import (
    IntimacyEligibilityService,
)

from app.services.spender_confidence_service import (
    SpenderConfidenceService,
)


class IntimacyProfileService:

    """
    3D.10.5

    Unified intimacy + spend + escalation profile.
    """

    def __init__(self):

        self.spend_service = (
            SpendIntelligenceService()
        )

        self.intimacy_service = (
            IntimacyEligibilityService()
        )

        self.confidence_service = (
            SpenderConfidenceService()
        )

    def build_profile(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):

        logger.info(
            "[IDENTITY FLOW] layer=IntimacyProfileService "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
        )

        spend_profile = (
            self.spend_service.get_spend_intelligence(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        intimacy_profile = (
            self.intimacy_service.get_intimacy_profile(
                fanvue_account_id=fanvue_account_id,
                fanvue_user_id=fanvue_user_id,
            )
        )

        confidence_profile = (
            self.confidence_service.calculate_confidence(
                purchase_count=spend_profile.get(
                    "purchase_count",
                    0,
                ),

                total_spend=float(
                    spend_profile.get(
                        "total_spend",
                        0,
                    )
                ),

                qualification_purchased=True,

                recent_purchase_active=(
                    spend_profile.get(
                        "recent_purchase_active",
                        False,
                    )
                ),
            )
        )

        return {
            "success": True,

            "fanvue_account_id": fanvue_account_id,

            "fanvue_user_id": fanvue_user_id,

            "buyer_tier": spend_profile.get(
                "buyer_tier"
            ),

            "intimacy_tier": intimacy_profile.get(
                "intimacy_tier"
            ),

            "max_intimacy_level": (
                intimacy_profile.get(
                    "max_intimacy_level"
                )
            ),

            "premium_sexting_allowed": (
                intimacy_profile.get(
                    "premium_sexting_allowed"
                )
            ),

            "explicit_allowed": (
                intimacy_profile.get(
                    "explicit_allowed"
                )
            ),

            "safe_to_escalate": (
                confidence_profile.get(
                    "safe_to_escalate"
                )
            ),

            "spender_confidence": (
                confidence_profile.get(
                    "spender_confidence"
                )
            ),

            "confidence_score": (
                confidence_profile.get(
                    "confidence_score"
                )
            ),

            "should_suppress_mass_ppv": (
                spend_profile.get(
                    "should_suppress_mass_ppv"
                )
            ),

            "escalation_priority": (
                spend_profile.get(
                    "escalation_priority"
                )
            ),

            "allowed_behaviors": (
                intimacy_profile.get(
                    "allowed_behaviors"
                )
            ),

            "blocked_behaviors": (
                intimacy_profile.get(
                    "blocked_behaviors"
                )
            ),
        }
