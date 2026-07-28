"""Internal per-turn Commerce execution policy.

The policy is derived from the already-evaluated Customer Sales Brain result.
It is deliberately not a public sales decision or a second decision engine.
"""
from __future__ import annotations

from enum import Enum

from app.models.customer_sales_decision import (
    CustomerSalesDecision,
    CustomerSalesDecisionType,
)


class CommerceExecutionPolicy(str, Enum):
    DISABLED_FOR_TURN = "COMMERCE_DISABLED_FOR_TURN"
    PRESENTATION_ALLOWED = "COMMERCE_PRESENTATION_ALLOWED"
    NUDGE_ALLOWED = "COMMERCE_NUDGE_ALLOWED"
    ACKNOWLEDGEMENT_ALLOWED = "COMMERCE_ACKNOWLEDGEMENT_ALLOWED"
    PAYMENT_PENDING = "COMMERCE_PAYMENT_PENDING"
    MANUAL_REVIEW = "COMMERCE_MANUAL_REVIEW"


def derive_commerce_execution_policy(
    decision: CustomerSalesDecision,
) -> CommerceExecutionPolicy:
    mapping = {
        CustomerSalesDecisionType.PRESENT_OFFER: (
            CommerceExecutionPolicy.PRESENTATION_ALLOWED
        ),
        CustomerSalesDecisionType.NUDGE_ACTIVE_OFFER: (
            CommerceExecutionPolicy.NUDGE_ALLOWED
        ),
        CustomerSalesDecisionType.CONGRATULATE_PURCHASE: (
            CommerceExecutionPolicy.ACKNOWLEDGEMENT_ALLOWED
        ),
        CustomerSalesDecisionType.PAYMENT_PENDING: (
            CommerceExecutionPolicy.PAYMENT_PENDING
        ),
        CustomerSalesDecisionType.MANUAL_REVIEW: (
            CommerceExecutionPolicy.MANUAL_REVIEW
        ),
    }
    return mapping.get(
        decision.decision,
        CommerceExecutionPolicy.DISABLED_FOR_TURN,
    )
