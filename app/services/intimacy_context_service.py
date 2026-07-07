import logging

from app.services.intimacy_profile_service import (
    IntimacyProfileService,
)


logger = logging.getLogger(__name__)


class IntimacyContextService:
    """
    3D.10.6

    Converts intimacy profile into GPT-safe context.

    Compatibility-safe version for older/newer profile outputs.
    """

    def __init__(self):
        self.profile_service = IntimacyProfileService()

    def build_gpt_context(
        self,
        fanvue_account_id: int,
        fanvue_user_id: str,
    ):
        logger.info(
            "[IDENTITY FLOW] layer=IntimacyContextService "
            "fanvue_account_id=%r fanvue_account_id_type=%s "
            "fanvue_user_id=%r fanvue_user_id_type=%s",
            fanvue_account_id,
            type(fanvue_account_id).__name__,
            fanvue_user_id,
            type(fanvue_user_id).__name__,
        )
        profile = self.profile_service.build_profile(
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )

        if not isinstance(profile, dict):
            profile = {}

        allowed_behaviors = (
            profile.get("allowed_behaviors") or []
        )

        blocked_behaviors = (
            profile.get("blocked_behaviors") or []
        )

        context_lines = []

        context_lines.append(
            f"Buyer Tier: {profile.get('buyer_tier', 'NON_BUYER')}"
        )
        context_lines.append(
            f"Intimacy Tier: {profile.get('intimacy_tier', 'none')}"
        )
        context_lines.append(
            f"Spender Confidence: {profile.get('spender_confidence', 'low')}"
        )
        context_lines.append(
            f"Max Intimacy Level: {profile.get('max_intimacy_level', 0)}"
        )
        context_lines.append(
            f"Safe To Escalate: {profile.get('safe_to_escalate', False)}"
        )
        context_lines.append(
            f"Premium Sexting Allowed: {profile.get('premium_sexting_allowed', False)}"
        )
        context_lines.append(
            f"Explicit Allowed: {profile.get('explicit_allowed', False)}"
        )

        context_lines.append("Allowed Behaviors:")

        for behavior in allowed_behaviors:
            context_lines.append(f"- {behavior}")

        context_lines.append("Blocked Behaviors:")

        for behavior in blocked_behaviors:
            context_lines.append(f"- {behavior}")

        gpt_context = "\n".join(context_lines)

        return {
            "success": True,
            "fanvue_account_id": fanvue_account_id,
            "fanvue_user_id": fanvue_user_id,
            "gpt_context": gpt_context,
            "profile": profile,
        }
