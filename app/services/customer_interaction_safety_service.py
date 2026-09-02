from dataclasses import dataclass

from app.repositories.ai_training_control_repository import AiTrainingControlRepository
from app.repositories.customer_interaction_safety_repository import CustomerInteractionSafetyRepository


@dataclass(frozen=True)
class CustomerInteractionSafetyDecision:
    allowed: bool
    code: str
    safety_status: str
    policy_enabled: bool


class CustomerInteractionSafetyService:
    """Single account-scoped authority for autonomous customer interaction."""
    def __init__(self, repository=None, training_repository=None,
                 abuse_review_repository=None):
        self.repository = repository or CustomerInteractionSafetyRepository()
        self.training = training_repository or AiTrainingControlRepository()
        if abuse_review_repository is None:
            from app.repositories.customer_abuse_review_repository import CustomerAbuseReviewRepository
            abuse_review_repository = CustomerAbuseReviewRepository()
        self.abuse_reviews = abuse_review_repository

    def decide(self, *, creator_profile_id: int, fanvue_account_id: int,
               fanvue_user_id: int) -> CustomerInteractionSafetyDecision:
        state = self.repository.get(creator_profile_id=creator_profile_id,
                                    fanvue_account_id=fanvue_account_id,
                                    fanvue_user_id=fanvue_user_id)
        status = str((state or {}).get("safety_status") or "NORMAL")
        enabled = self.training.is_backend_policy_enabled(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            policy_key="UNDERAGE_CUSTOMER")
        # Customer safety state is deliberately fail-closed. Disabling the global
        # policy never silently restores a customer; only an audited operator action does.
        blocked = status == "UNDERAGE_BLOCKED"
        abuse = self.abuse_reviews.active_for_customer(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            fanvue_user_id=fanvue_user_id,
        )
        if abuse is not None:
            abuse_status = str(abuse.get("review_status") or "OPEN")
            return CustomerInteractionSafetyDecision(
                False,
                "BLOCKED_MANUAL_ABUSE" if abuse_status == "MANUALLY_BLOCKED"
                else "BLOCKED_ABUSE_REVIEW_HOLD",
                abuse_status, enabled,
            )
        return CustomerInteractionSafetyDecision(not blocked,
            "ALLOWED" if not blocked else "BLOCKED_UNDERAGE", status, enabled)

    def set_status(self, *, creator_profile_id: int, fanvue_account_id: int,
                   fanvue_user_id: int, safety_status: str, reason: str,
                   actor_identifier: str = "CREATOR_OS_OPERATOR"):
        status = str(safety_status).upper()
        if status not in {"NORMAL", "UNDERAGE_BLOCKED"}:
            raise ValueError("Safety status must be NORMAL or UNDERAGE_BLOCKED.")
        reason = str(reason or "").strip()
        if len(reason) < 5:
            raise ValueError("A deliberate operator reason is required.")
        if status == "UNDERAGE_BLOCKED" and not self.training.is_backend_policy_enabled(
            creator_profile_id=creator_profile_id, fanvue_account_id=fanvue_account_id,
            policy_key="UNDERAGE_CUSTOMER"):
            raise ValueError("Enable the Underage Customer Hard Stop global policy first.")
        return self.repository.set_status(creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, fanvue_user_id=fanvue_user_id,
            safety_status=status, reason=reason, actor_identifier=actor_identifier)

    def decide_for_customer(self, *, fanvue_account_id: int, fanvue_user_id: int):
        from app.repositories.creator_profile_repository import get_active_creator_profile
        profile = get_active_creator_profile(str(fanvue_account_id)) or {}
        if not profile.get("id"):
            return CustomerInteractionSafetyDecision(False, "BLOCKED_IDENTITY_UNRESOLVED", "UNKNOWN", False)
        return self.decide(creator_profile_id=int(profile["id"]),
            fanvue_account_id=int(fanvue_account_id), fanvue_user_id=int(fanvue_user_id))
