"""Side-effect-free Market Tier state and effective-investment projection."""
from dataclasses import asdict

from app.models.relationship_market_tier import (
    EffectiveProspectInvestment, RelationshipMarketTier,
)
from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository


class RelationshipMarketTierService:
    def __init__(self, repository=None, *, availability=None,
                 effective_permissions=None):
        self.repository = repository or RelationshipMarketTierRepository()
        self.availability = availability
        self.effective_permissions = effective_permissions

    def read(self, *, high_value_prospect=False, verified_buyer=False, **scope):
        return self._project(self.repository.active(**scope),
                             high_value_prospect=high_value_prospect,
                             verified_buyer=verified_buyer)

    def set(self, *, market_tier, changed_by, reason=None,
            high_value_prospect=False, verified_buyer=False, **scope):
        try:
            tier = RelationshipMarketTier(str(getattr(market_tier, "value", market_tier)))
        except ValueError as error:
            raise ValueError("Market Tier must be HIGH, MEDIUM, or LOW.") from error
        previous=self.repository.active(**scope)
        record, changed = self.repository.set(
            market_tier=tier.value, changed_by=changed_by, reason=reason, **scope)
        advanced = None
        advance = getattr(self.repository, "advance_eligible", None)
        if (changed and tier is RelationshipMarketTier.HIGH and not verified_buyer
                and callable(advance) and self._may_reschedule(scope)):
            if self.availability is None:
                from app.services.ava_human_availability_service import AvaHumanAvailabilityService
                self.availability = AvaHumanAvailabilityService()
            decision = self.availability.calculate(
                market_tier="HIGH", high_value_prospect=high_value_prospect)
            advanced = advance(
                telegram_user_id=scope["telegram_user_id"],
                telegram_chat_id=scope["telegram_chat_id"],
                available_at=decision.available_at,
                high_value_prospect=high_value_prospect)
        if changed and tier in {RelationshipMarketTier.HIGH,RelationshipMarketTier.MEDIUM}:
            old=previous.market_tier if previous else None
            promoted=(tier is RelationshipMarketTier.HIGH and old in {RelationshipMarketTier.MEDIUM,RelationshipMarketTier.LOW}) or (tier is RelationshipMarketTier.MEDIUM and old is RelationshipMarketTier.LOW)
            if promoted:
                from app.services.market_tier_resource_gate_service import MarketTierResourceGateService
                MarketTierResourceGateService().reconsider_after_promotion(
                    **scope,new_tier=tier.value,high_value_prospect=high_value_prospect,
                    verified_buyer=verified_buyer)
        return {**self._project(record,high_value_prospect=high_value_prospect,
                                verified_buyer=verified_buyer),"changed":changed,
                "scheduleAdvanced":advanced is not None,
                "advancedOperation":advanced}

    def remove(self, *, removed_by, high_value_prospect=False,
               verified_buyer=False, **scope):
        removed = self.repository.remove(removed_by=removed_by, **scope)
        return {**self._project(None,high_value_prospect=high_value_prospect,
                                verified_buyer=verified_buyer),
                "changed":removed is not None}

    def _may_reschedule(self, scope):
        if self.effective_permissions is None:
            from app.services.customer_effective_permissions_service import CustomerEffectivePermissionsService
            self.effective_permissions = CustomerEffectivePermissionsService()
        result = self.effective_permissions.read(**scope)
        return bool(result["effective"]["chatAllowed"])

    @staticmethod
    def effective_investment(*, market_tier=None, high_value_prospect=False,
                             verified_buyer=False):
        if verified_buyer:
            return EffectiveProspectInvestment.BUYER_AUTHORITY
        tier = RelationshipMarketTier(market_tier) if market_tier else None
        if tier is RelationshipMarketTier.LOW:
            return EffectiveProspectInvestment.LOW
        if tier is RelationshipMarketTier.HIGH and high_value_prospect:
            return EffectiveProspectInvestment.MAXIMUM
        if tier is RelationshipMarketTier.HIGH or high_value_prospect:
            return EffectiveProspectInvestment.HIGH
        return EffectiveProspectInvestment.STANDARD

    @classmethod
    def _project(cls, record, *, high_value_prospect, verified_buyer):
        tier = record.market_tier.value if record else None
        return {
            "marketTier": tier or "UNCLASSIFIED",
            "effectiveProspectInvestment": cls.effective_investment(
                market_tier=tier, high_value_prospect=high_value_prospect,
                verified_buyer=verified_buyer).value,
            "highValueProspect": bool(high_value_prospect),
            "verifiedBuyer": bool(verified_buyer),
            "record": asdict(record) if record else None,
        }
