"""Operator HVP authority; never changes commercial or delivery authority."""
from app.services.ava_human_availability_service import AvaHumanAvailabilityService
from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
from app.repositories.relationship_value_override_repository import RelationshipValueOverrideRepository


class RelationshipValueOverrideService:
    CLASSIFICATION = "HIGH_VALUE_PROSPECT"

    def __init__(self, *, repository=None, availability=None,
                 effective_permissions=None, market_tiers=None):
        self.repository = repository or RelationshipValueOverrideRepository()
        self.availability = availability or AvaHumanAvailabilityService()
        self.effective_permissions = effective_permissions or CustomerEffectivePermissionsService()
        self.market_tiers = market_tiers

    def active(self, **scope):
        return self.repository.active(**scope)

    def set(self, *, classification, changed_by, reason=None, **scope):
        if classification != self.CLASSIFICATION:
            raise ValueError("Unsupported operator classification.")
        row, created = self.repository.set_high_value(
            changed_by=changed_by, reason=reason, **scope)
        advanced = None
        if created and self._may_reschedule(scope):
            if self.market_tiers is None:
                from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository
                self.market_tiers = RelationshipMarketTierRepository()
            tier = self.market_tiers.active(**scope)
            market_tier = tier.market_tier.value if tier else None
            kwargs = {"high_value_prospect": True}
            if market_tier == "HIGH":
                kwargs["market_tier"] = "HIGH"
            decision = self.availability.calculate(**kwargs)
            advanced = self.repository.advance_eligible(
                telegram_user_id=scope["telegram_user_id"],
                telegram_chat_id=scope["telegram_chat_id"],
                available_at=decision.available_at)
        return {"override": row, "scheduleAdvanced": advanced is not None,
                "advancedOperation": advanced}

    def remove(self, *, removed_by, **scope):
        # Deliberately does not push an already-committed schedule later.
        return {"override": self.repository.remove(removed_by=removed_by, **scope),
                "scheduleAdvanced": False, "advancedOperation": None}

    def _may_reschedule(self, scope):
        result = self.effective_permissions.read(**scope)
        return bool(result["effective"]["chatAllowed"])
