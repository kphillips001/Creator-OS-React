from app.repositories.buyer_intelligence_repository import (
    get_buyer_intelligence_by_user_id,
)

from app.repositories.buyer_memory_sync_repository import (
    sync_buyer_intelligence_to_user_memory,
)


class QualificationEscalationService:
    """
    3D.10.2

    Qualification PPV purchase escalation logic.

    Section 6 hardened:
    Buyer intelligence and memory sync are scoped by:
    - fanvue_account_id
    - fanvue_user_id
    """

    def process_successful_qualification_purchase(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):
        if not fanvue_account_id:
            return {
                "success": False,
                "reason": "missing_fanvue_account_id",
            }

        if not fanvue_user_id:
            return {
                "success": False,
                "reason": "missing_fanvue_user_id",
            }

        buyer = get_buyer_intelligence_by_user_id(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        if not buyer:
            return {
                "success": False,
                "reason": "buyer_not_found",
                "fanvue_account_id": fanvue_account_id,
                "fanvue_user_id": fanvue_user_id,
            }

        total_spend = float(
            buyer.get("total_spend") or 0
        )

        intimacy_tier = 0

        if total_spend >= 100:
            intimacy_tier = 2

        elif total_spend >= 20:
            intimacy_tier = 1

        escalation_result = sync_buyer_intelligence_to_user_memory(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "buyer_tier": buyer.get("buyer_tier"),
            "total_spend": total_spend,
            "intimacy_tier": intimacy_tier,
            "spender_confidence": "HIGH",
            "safe_to_escalate": True,
            "memory_sync_result": escalation_result,
        }