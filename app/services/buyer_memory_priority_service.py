"""Resolve canonical buyer memory investment without changing memory truth."""
from __future__ import annotations

from app.repositories.customer_commerce_repository import CustomerCommerceRepository
from app.services.customer_value_attention_service import CustomerValueAttentionService


class BuyerMemoryPriorityService:
    """Read provider-backed buyer value and return its canonical memory priority."""

    def __init__(self, *, customer_repository=None, value_service=None) -> None:
        self.customers = customer_repository or CustomerCommerceRepository()
        self.values = value_service or CustomerValueAttentionService()

    def resolve(self, *, creator_profile_id: int, canonical_identity) -> str:
        if canonical_identity is None:
            return "STANDARD"
        profile = self.customers.get_by_buyer_uuid(
            creator_profile_id=int(creator_profile_id),
            external_fanvue_user_uuid=canonical_identity.external_fanvue_user_uuid,
        )
        if profile is None:
            return "STANDARD"
        projection = self.values.project(commerce_memory={
            "schemaVersion": "customer_commerce_profile_v1",
            "verifiedPurchaseCount": int(profile.purchase_count or 0),
            "lifetimeGrossMinor": int(profile.lifetime_gross_minor or 0),
            "lifetimeNetMinor": int(profile.lifetime_net_minor or 0),
            "averageOrderValueMinor": int(profile.average_order_value_minor or 0),
            "largestOrderMinor": int(profile.largest_purchase_minor or 0),
            "lastPurchaseAt": (
                profile.last_purchase_at.isoformat()
                if profile.last_purchase_at is not None else None
            ),
        })
        return projection.memory_priority
