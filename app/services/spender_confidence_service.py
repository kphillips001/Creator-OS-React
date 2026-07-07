class SpenderConfidenceService:

    """
    3D.10.4

    Calculates buyer confidence and escalation safety.
    """

    def calculate_confidence(
        self,
        *,
        purchase_count: int,
        total_spend: float,
        qualification_purchased: bool,
        recent_purchase_active: bool,
    ):

        confidence_score = 0

        if qualification_purchased:
            confidence_score += 25

        if purchase_count >= 1:
            confidence_score += 20

        if purchase_count >= 3:
            confidence_score += 20

        if total_spend >= 50:
            confidence_score += 15

        if total_spend >= 100:
            confidence_score += 20

        if recent_purchase_active:
            confidence_score += 15

        if confidence_score >= 80:
            spender_confidence = "HIGH"

        elif confidence_score >= 50:
            spender_confidence = "MEDIUM"

        else:
            spender_confidence = "LOW"

        safe_to_escalate = (
            spender_confidence in [
                "MEDIUM",
                "HIGH",
            ]
        )

        return {
            "success": True,

            "confidence_score": confidence_score,

            "spender_confidence": spender_confidence,

            "safe_to_escalate": safe_to_escalate,

            "qualification_purchased": qualification_purchased,

            "recent_purchase_active": recent_purchase_active,
        }