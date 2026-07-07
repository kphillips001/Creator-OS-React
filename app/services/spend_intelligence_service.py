import logging

from app.repositories.buyer_intelligence_repository import (
    get_buyer_intelligence_by_user_id,
)


logger = logging.getLogger(__name__)


class SpendIntelligenceService:
    """
    3D.9A — Realtime Spend Intelligence Service

    Converts buyer + monetization data into reusable
    intelligence signals for:

    - DecisionEngine
    - monetization routing
    - intimacy eligibility
    - PPV aggression logic
    - retention systems
    """

    def get_spend_intelligence(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str | None,
    ):
        logger.info(
            "[IDENTITY FLOW] layer=SpendIntelligenceService "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
        )
        if not fanvue_user_id:
            logger.info(
                "[BUYER INTELLIGENCE SKIPPED] reason=missing_mapped_fanvue_user_id "
                "fanvue_account_id=%r",
                fanvue_account_id,
            )
            return {
                "success": False,
                "reason": "missing_mapped_fanvue_user_id",
            }

        buyer = get_buyer_intelligence_by_user_id(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        if not buyer:
            return {
                "success": False,
                "reason": "buyer_not_found",
            }

        buyer_tier = buyer.get(
            "buyer_tier"
        )

        total_spend = float(
            buyer.get("total_spend") or 0
        )

        total_tip_amount = float(
            buyer.get("total_tip_amount") or 0
        )

        purchase_count = int(
            buyer.get("purchase_count") or 0
        )

        is_spender = bool(
            buyer.get("is_spender")
        )

        is_whale = bool(
            buyer.get("is_whale")
        )

        recent_purchase_active = (
            total_spend > 0
        )

        recent_tip_active = (
            total_tip_amount > 0
        )

        intimacy_tier = self._determine_intimacy_tier(
            buyer_tier
        )

        ppv_aggression_level = (
            self._determine_ppv_aggression(
                buyer_tier
            )
        )

        should_suppress_mass_ppv = (
            recent_purchase_active
            or recent_tip_active
        )

        escalation_priority = (
            self._determine_escalation_priority(
                buyer_tier
            )
        )

        retention_risk = (
            self._determine_retention_risk(
                buyer
            )
        )

        return {
            "success": True,
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": buyer_tier,
            "total_spend": total_spend,
            "total_tip_amount": total_tip_amount,
            "purchase_count": purchase_count,
            "is_spender": is_spender,
            "is_whale": is_whale,
            "recent_purchase_active": (
                recent_purchase_active
            ),
            "recent_tip_active": (
                recent_tip_active
            ),
            "intimacy_tier": intimacy_tier,
            "ppv_aggression_level": (
                ppv_aggression_level
            ),
            "should_suppress_mass_ppv": (
                should_suppress_mass_ppv
            ),
            "escalation_priority": (
                escalation_priority
            ),
            "retention_risk": retention_risk,
        }

    def _determine_intimacy_tier(
        self,
        buyer_tier: str,
    ):
        mapping = {
            "NON_BUYER": 0,
            "LOW_SPENDER": 1,
            "ACTIVE_BUYER": 2,
            "HIGH_VALUE": 3,
            "WHALE": 3,
        }

        return mapping.get(
            buyer_tier,
            0,
        )

    def _determine_ppv_aggression(
        self,
        buyer_tier: str,
    ):
        mapping = {
            "NON_BUYER": "low",
            "LOW_SPENDER": "medium",
            "ACTIVE_BUYER": "medium",
            "HIGH_VALUE": "high",
            "WHALE": "high",
        }

        return mapping.get(
            buyer_tier,
            "low",
        )

    def _determine_escalation_priority(
        self,
        buyer_tier: str,
    ):
        mapping = {
            "NON_BUYER": "low",
            "LOW_SPENDER": "medium",
            "ACTIVE_BUYER": "high",
            "HIGH_VALUE": "high",
            "WHALE": "critical",
        }

        return mapping.get(
            buyer_tier,
            "low",
        )

    def _determine_retention_risk(
        self,
        buyer: dict,
    ):
        is_spender = buyer.get(
            "is_spender"
        )

        is_subscriber = buyer.get(
            "is_subscriber"
        )

        if is_spender and not is_subscriber:
            return "medium"

        if is_spender and is_subscriber:
            return "low"

        return "high"
