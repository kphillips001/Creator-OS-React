"""Restricted commerce context containing no invented Fanvue history."""
from types import SimpleNamespace

from app.models.customer_commerce_memory import CustomerCommerceMemory
from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer, OwnershipAnswerState, OwnershipIdentity,
)
from app.repositories.telegram_sales_prospect_repository import TelegramSalesProspectRepository


class UnmappedTelegramProspectService:
    def __init__(self, repository=None):
        self.repository = repository or TelegramSalesProspectRepository()

    def observe(self, **values):
        return self.repository.observe(**values)

    def graduate(self, **values):
        return self.repository.graduate(**values)

    @staticmethod
    def sales_progression(prospect):
        relationship = dict(
            getattr(prospect, "relationship_state", {}) or {}
        )
        progression = relationship.get("salesProgression")
        return dict(progression) if isinstance(progression, dict) else None

    def record_sales_progression(self, **values):
        return self.repository.record_sales_progression(**values)

    @staticmethod
    def contact_block(prospect):
        relationship = dict(getattr(prospect, "relationship_state", {}) or {})
        value = relationship.get("telegramContactBlock")
        return dict(value) if isinstance(value, dict) else None

    def record_contact_block(self, **values):
        return self.repository.record_contact_block(**values)

    @staticmethod
    def supporter_attention_boundary(prospect):
        relationship = dict(getattr(prospect, "relationship_state", {}) or {})
        value = relationship.get("supporterAttentionBoundary")
        return dict(value) if isinstance(value, dict) else None

    def record_supporter_boundary_delivery(self, **values):
        return self.repository.record_supporter_boundary_delivery(**values)

    @staticmethod
    def deferred_continuation(prospect):
        relationship = dict(getattr(prospect, "relationship_state", {}) or {})
        value = relationship.get("deferredContinuation")
        return dict(value) if isinstance(value, dict) else None

    def record_deferred_continuation(self, **values):
        return self.repository.record_deferred_continuation(**values)

    def ready_deferred_continuation(self, **values):
        return self.repository.transition_deferred_continuation(
            from_states=("PENDING_ACKNOWLEDGEMENT",), target_state="READY", **values)

    def claim_deferred_continuation(self, **values):
        return self.repository.transition_deferred_continuation(
            from_states=("READY", "CLAIMED"), target_state="CLAIMED", **values)

    def consume_deferred_continuation(self, **values):
        return self.repository.transition_deferred_continuation(
            from_states=("CLAIMED",), target_state="CONSUMED", **values)

    def invalidate_deferred_continuation(self, **values):
        return self.repository.transition_deferred_continuation(
            from_states=("PENDING_ACKNOWLEDGEMENT", "READY", "CLAIMED"),
            target_state="INVALIDATED", **values)

    @staticmethod
    def session_proposal(prospect):
        relationship = dict(getattr(prospect, "relationship_state", {}) or {})
        value = relationship.get("sessionProposal")
        return dict(value) if isinstance(value, dict) else None

    def record_session_proposal(self, **values):
        return self.repository.record_session_proposal(**values)

    def transition_session_proposal(self, **values):
        return self.repository.transition_session_proposal(**values)

    def context(self, *, creator_profile_id, fanvue_account_id,
                telegram_user_id, telegram_chat_id=None):
        prospect = self.repository.get(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        if prospect is None:
            if telegram_chat_id is None:
                return None
            prospect = self.repository.observe(
                creator_profile_id=creator_profile_id,
                fanvue_account_id=fanvue_account_id,
                telegram_user_id=telegram_user_id,
                telegram_chat_id=telegram_chat_id,
            )
        identity = OwnershipIdentity(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_user_id=telegram_user_id,
        )
        ownership = CanonicalOwnershipAnswer(
            identity=identity, evidence=(), owned_offering_ids=(),
            owned_product_ids=(), owned_asset_ids=(),
            state=OwnershipAnswerState.INSUFFICIENT,
            diagnostics={"fanvueOwnership": "UNKNOWN",
                         "duplicateVaultOfferRiskAccepted": True},
        )
        memory = CustomerCommerceMemory(
            identity=identity, ownership=ownership,
            attribution_insufficiencies=(
                "Fanvue history intentionally unavailable before mapping.",
            ),
        )
        profile = SimpleNamespace(
            fanvue_account_id=fanvue_account_id,
            external_fanvue_user_uuid=None, purchase_count=0,
            last_purchase_at=None, profile_state="PROSPECT", core_user_id=None,
        )
        return SimpleNamespace(prospect=prospect, profile=profile, memory=memory)
