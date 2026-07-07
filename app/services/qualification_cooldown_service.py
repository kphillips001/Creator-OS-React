from app.repositories.qualification_ppv_repository import (
    mark_qualification_ppv_purchased,
)


class QualificationCooldownService:

    """
    3D.10.2

    Handles ignored qualification PPVs.
    """

    def process_ignored_qualification_ppv(
        self,
        *,
        fanvue_user_id: str,
        qualification_event_id: int,
    ):

        return {
            "success": True,
            "fanvue_user_id": fanvue_user_id,
            "qualification_event_id": qualification_event_id,

            "reduce_ppv_frequency": True,
            "reduce_aggressive_upsells": True,
            "slow_pacing_enabled": True,
            "soft_monetization_path": True,

            "safe_to_hard_escalate": False,
            "spender_confidence": "LOW",

            "next_behavior_mode": "SOFT_FLIRT",
        }