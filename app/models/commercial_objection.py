"""Canonical, side-effect-free objection scope for the Sales Brain."""
from dataclasses import dataclass, field
from enum import Enum
from types import MappingProxyType
from typing import Any, Mapping


class CommercialObjectionType(str, Enum):
    NONE = "NONE"
    PRICE_RESISTANCE = "PRICE_RESISTANCE"
    DISCOUNT_REQUEST = "DISCOUNT_REQUEST"
    BUDGET_LIMIT = "BUDGET_LIMIT"
    CONTENT_MISMATCH = "CONTENT_MISMATCH"
    PRODUCT_REJECTION = "PRODUCT_REJECTION"
    TEMPORARY_HESITATION = "TEMPORARY_HESITATION"
    GLOBAL_DECLINE = "GLOBAL_DECLINE"
    PAYMENT_TECHNICAL = "PAYMENT_TECHNICAL"
    TRUST_OR_SUPPORT = "TRUST_OR_SUPPORT"


@dataclass(frozen=True)
class CommercialObjection:
    objection_type: CommercialObjectionType
    strength: str
    current_product_scoped: bool
    continue_selling: bool
    current_offer_authoritative: bool
    consider_alternative: bool
    pressure_decrease: bool
    evidence: tuple[str, ...] = ()
    selector_constraints: Mapping[str, Any] = field(
        default_factory=lambda: MappingProxyType({})
    )
    recovery_strategy: str = "NONE"
    negative_contact_authorized: bool = False
    budget_constraint_minor: int | None = None

    def to_mapping(self) -> Mapping[str, Any]:
        return MappingProxyType({
            "type": self.objection_type.value,
            "strength": self.strength,
            "scope": (
                "CURRENT_PRODUCT" if self.current_product_scoped else
                "GLOBAL" if self.objection_type is not CommercialObjectionType.NONE
                else "NONE"
            ),
            "customerStillCommerciallyReceptive": self.continue_selling,
            "currentOfferAuthoritative": self.current_offer_authoritative,
            "alternativeSelectionAllowed": self.consider_alternative,
            "pressureDecrease": self.pressure_decrease,
            "selectorConstraints": dict(self.selector_constraints),
            "evidence": self.evidence,
            "recoveryStrategy": self.recovery_strategy,
            "negativeContactAuthorized": self.negative_contact_authorized,
            "budgetConstraintDetected": self.budget_constraint_minor is not None,
            "budgetConstraintAmount": self.budget_constraint_minor,
            "noDynamicDiscount": True,
            "falseScarcityAllowed": False,
        })
