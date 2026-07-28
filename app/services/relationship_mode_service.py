"""Shadow-commerce recording and deterministic pre-launch responses."""

from hashlib import sha256
from collections.abc import Mapping

from app.models.customer_commerce import CustomerCommerceProfileState
from app.services.commerce_learning_service import CommerceLearningService
from app.services.customer_commerce_service import CustomerCommerceService


class RelationshipModeService:
    RESPONSES = (
        "I'm still getting everything ready behind the scenes 😊",
        "I'm working on putting everything together before I officially launch.",
        "You're catching me early 😊 I'm still preparing everything.",
        "I'm not officially launched yet, but I promise it'll be worth the wait.",
    )

    def __init__(self, *, learning=None, customers=None):
        self.learning = learning or CommerceLearningService()
        self.customers = customers or CustomerCommerceService()

    def response(self, *, customer_identifier: str, correlation_id: str) -> str:
        digest = sha256(f"{customer_identifier}:{correlation_id}".encode()).digest()
        return self.RESPONSES[int.from_bytes(digest[:2], "big") % len(self.RESPONSES)]

    def record_would_have_sold(self, decision, *, correlation_id: str):
        if not (
            decision.external_fanvue_buyer_uuid
            and decision.recommended_offering_id
        ):
            return None
        selector = dict(decision.decision_metadata or {}).get("offeringSelector") or {}
        trace = dict(selector) if isinstance(selector, Mapping) else {}
        result = self.learning.record_observed_outcome(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            external_fanvue_user_uuid=decision.external_fanvue_buyer_uuid,
            telegram_user_id=decision.telegram_user_id,
            commercial_offering_id=decision.recommended_offering_id,
            outcome_type="WOULD_HAVE_SOLD",
            source_event_key=f"relationship-mode:{correlation_id}",
            evidence={
                "would_have_sold": True,
                "suppression_reason": "RELATIONSHIP_MODE",
                "selected_title": decision.recommended_offering_title,
                "price_minor": decision.recommended_offering_price_minor,
                "semantic_reason": self._component(trace, "semantic_match"),
                "affinity_reason": self._component(trace, "customer_affinity"),
                "freshness": self._component(trace, "freshness"),
            },
            recommendation_trace=trace,
        )
        profile = self.customers.repository.get_by_buyer_uuid(
            creator_profile_id=decision.creator_profile_id,
            fanvue_account_id=decision.fanvue_account_id,
            external_fanvue_user_uuid=decision.external_fanvue_buyer_uuid,
        )
        if profile is not None and profile.purchase_count == 0:
            self.customers.update_profile(
                profile.customer_commerce_profile_id,
                display_name=profile.display_name,
                handle=profile.handle,
                profile_state=CustomerCommerceProfileState.PRE_LAUNCH_INTEREST,
                creator_profile_id=decision.creator_profile_id,
            )
        return result

    @staticmethod
    def _component(trace, key):
        candidates = trace.get("recommendationTrace") or trace.get("rankedCandidates") or ()
        selected = next((item for item in candidates if item.get("selected")), None)
        component = next(
            (item for item in (selected or {}).get("components", ()) if item.get("key") == key),
            None,
        )
        return component
