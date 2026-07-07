from app.repositories.qualification_ppv_repository import (
    mark_qualification_ppv_purchased,
)


class QualificationPPVService:

    """
    3D.10.2

    Handles qualification PPV purchase outcomes.
    """

    def process_qualification_purchase(
        self,
        *,
        qualification_event_id: int,
        purchase_event_id: int = None,
    ):

        result = mark_qualification_ppv_purchased(
            qualification_event_id=qualification_event_id,
            purchase_event_id=purchase_event_id,
        )

        return {
            "success": True,
            "qualification_result": result,
            "spender_confidence_increased": True,
            "buyer_confidence_increased": True,
            "safe_to_escalate": True,
        }