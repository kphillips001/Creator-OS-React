"""Authoritative Photoshoot Sales Opportunity transitions and ownership coverage."""
from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus
from app.repositories.customer_photoshoot_lifecycle_repository import CustomerPhotoshootLifecycleRepository


class InvalidLifecycleTransition(ValueError):
    pass


class CustomerPhotoshootLifecycleService:
    """Compatibility-named boundary for the non-perpetual Sales Opportunity."""

    TERMINAL = {
        CustomerPhotoshootStatus.COMPLETED,
        CustomerPhotoshootStatus.CLOSED,
        CustomerPhotoshootStatus.DECLINED,
    }
    ALLOWED = {
        CustomerPhotoshootStatus.ACTIVE: TERMINAL | {CustomerPhotoshootStatus.OBJECTION},
        CustomerPhotoshootStatus.OBJECTION: TERMINAL | {CustomerPhotoshootStatus.ACTIVE},
    }

    def __init__(self, repository=None):
        self.repository = repository or CustomerPhotoshootLifecycleRepository()

    def resolve_recommendation(self, *, creator_profile_id, customer_commerce_profile_id,
                               recommendation, sales_session_id=None, reason=None):
        """Open one opportunity, but never reactivate terminal history."""
        self.expire_due(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
        )
        opportunity = self.repository.resolve(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
            photoshoot_id=recommendation.photoshoot_id,
            selected_offering_id=recommendation.commercial_offering_id,
            recommendation_reason=reason or recommendation.recommendation_explanation,
            metadata={"recommendation_score": recommendation.recommendation_score},
        )
        if sales_session_id and opportunity.status is CustomerPhotoshootStatus.ACTIVE:
            opportunity = self.repository.transition(
                opportunity.lifecycle_id,
                status=opportunity.status,
                event_type="SESSION_ASSOCIATED",
                sales_session_id=sales_session_id,
            )
        return opportunity

    def transition(self, lifecycle, status, **kwargs):
        status = CustomerPhotoshootStatus(status)
        if status != lifecycle.status and status not in self.ALLOWED.get(lifecycle.status, set()):
            raise InvalidLifecycleTransition(f"{lifecycle.status.value} -> {status.value}")
        return self.repository.transition(
            lifecycle.lifecycle_id,
            status=status,
            event_type=kwargs.pop("event_type", status.value),
            **kwargs,
        )

    def synchronize_purchase(self, *, creator_profile_id, customer_commerce_profile_id,
                             photoshoot_id, asset_ids, purchase_outcome_id,
                             offering_id=None, purchase_intent_id=None):
        opportunity = self.repository.resolve(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
            photoshoot_id=photoshoot_id,
            selected_offering_id=offering_id,
        )
        if opportunity.status in self.TERMINAL:
            return opportunity, self.repository.coverage(opportunity.lifecycle_id)
        authoritative = getattr(self.repository, "offering_asset_ids", None)
        if offering_id is not None and callable(authoritative):
            asset_ids = authoritative(offering_id)
        teaser_ids = set(self.repository.teaser_asset_ids(opportunity.lifecycle_id))
        for asset_id in dict.fromkeys(asset_ids):
            if asset_id in teaser_ids:
                continue
            opportunity = self.repository.transition(
                opportunity.lifecycle_id,
                status=CustomerPhotoshootStatus.ACTIVE,
                event_type="PURCHASED",
                asset_id=asset_id,
                purchase_outcome_id=purchase_outcome_id,
                purchase_intent_id=purchase_intent_id,
            )
        coverage = self.repository.coverage(opportunity.lifecycle_id)
        core_ids = set(self.repository.required_core_asset_ids(opportunity.lifecycle_id))
        video_ids = tuple(self.repository.finale_video_asset_ids(opportunity.lifecycle_id))
        if len(video_ids) > 1:
            raise ValueError("A protected Photoshoot supports at most one VIP finale video.")
        purchased = set(coverage["purchased_asset_ids"])
        core_complete = core_ids.issubset(purchased)
        finale_resolved = not video_ids or video_ids[0] in purchased
        if core_complete and finale_resolved:
            opportunity = self.transition(
                opportunity,
                CustomerPhotoshootStatus.COMPLETED,
                event_type="OPPORTUNITY_COMPLETED",
                metadata={"finale_decision": "PURCHASED" if video_ids else "NOT_APPLICABLE"},
            )
        return opportunity, coverage

    def synchronize_attributed_purchase(self, *, intent, customer_commerce_profile_id):
        """Project one verified, attributed Purchase Intent into an existing lifecycle."""
        status = getattr(getattr(intent, "status", None), "value", getattr(intent, "status", None))
        attribution = getattr(
            getattr(intent, "attribution_result", None),
            "value", getattr(intent, "attribution_result", None),
        )
        if status != "PURCHASED" or attribution != "ATTRIBUTED":
            return None
        opportunity = self.repository.get_for_purchase_intent(intent)
        if opportunity is None or opportunity.customer_commerce_profile_id != customer_commerce_profile_id:
            return None
        offering_assets = tuple(self.repository.offering_asset_ids(intent.commercial_offering_id))
        photoshoot_assets = set(self.repository.photoshoot_asset_ids(opportunity.lifecycle_id))
        if not offering_assets or not set(offering_assets).issubset(photoshoot_assets):
            return None
        selling_mode_reader = getattr(
            self.repository, "offering_selling_mode", None
        )
        selling_mode = (
            selling_mode_reader(intent.commercial_offering_id)
            if callable(selling_mode_reader) else "SESSION"
        )
        if selling_mode == "BUNDLE":
            if opportunity.status is CustomerPhotoshootStatus.COMPLETED:
                return opportunity, self.repository.coverage(
                    opportunity.lifecycle_id
                )
            transition_values = {
                "status": CustomerPhotoshootStatus.COMPLETED,
                "event_type": "BUNDLE_PURCHASED",
                "purchase_outcome_id": intent.purchase_intent_id,
                "purchase_intent_id": intent.purchase_intent_id,
                "metadata": {
                    "commercial_offering_id": str(
                        intent.commercial_offering_id
                    ),
                    "paid_asset_count": len(offering_assets),
                    "commercial_completion": "BUNDLE_OFFERING_PURCHASED",
                },
            }
            completed = (
                self.repository.transition(
                    opportunity.lifecycle_id, **transition_values
                )
                if opportunity.status in self.TERMINAL
                else self.transition(opportunity, **transition_values)
            )
            return completed, self.repository.coverage(
                opportunity.lifecycle_id
            )
        return self.synchronize_purchase(
            creator_profile_id=intent.creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
            photoshoot_id=opportunity.photoshoot_id,
            asset_ids=offering_assets,
            purchase_outcome_id=intent.purchase_intent_id,
            offering_id=intent.commercial_offering_id,
            purchase_intent_id=intent.purchase_intent_id,
        )

    def decline_finale(self, lifecycle):
        if lifecycle.status is not CustomerPhotoshootStatus.ACTIVE:
            return lifecycle
        coverage = self.repository.coverage(lifecycle.lifecycle_id)
        required = set(self.repository.required_core_asset_ids(lifecycle.lifecycle_id))
        if not required.issubset(set(coverage["purchased_asset_ids"])):
            raise InvalidLifecycleTransition("The VIP finale cannot be resolved before all paid image chapters.")
        return self.transition(
            lifecycle,
            CustomerPhotoshootStatus.COMPLETED,
            event_type="FINALE_DECLINED",
            metadata={"finale_decision": "DECLINED"},
        )

    def expire_due(self, **scope):
        expire = getattr(self.repository, "expire_due", None)
        return tuple(expire(**scope)) if callable(expire) else ()

    def enter_objection(self, lifecycle, *, reason=None, purchase_intent_id=None):
        if lifecycle.status is CustomerPhotoshootStatus.OBJECTION:
            return lifecycle
        if lifecycle.status is not CustomerPhotoshootStatus.ACTIVE:
            return lifecycle
        return self.transition(
            lifecycle, CustomerPhotoshootStatus.OBJECTION,
            event_type="OBJECTION_ENTERED", purchase_intent_id=purchase_intent_id,
            metadata={"reason": reason} if reason else {},
        )

    def attempt_recovery(self, lifecycle, *, recovered, recovery_limit, reason=None):
        if lifecycle.status is not CustomerPhotoshootStatus.OBJECTION:
            return lifecycle
        attempts = lifecycle.objection_attempts + 1
        metadata = {"objection_attempt_delta": 1, "attempt": attempts}
        if reason:
            metadata["reason"] = reason
        if recovered:
            return self.transition(
                lifecycle, CustomerPhotoshootStatus.ACTIVE,
                event_type="OBJECTION_RECOVERED", metadata=metadata,
            )
        terminal = attempts >= max(1, int(recovery_limit))
        return self.transition(
            lifecycle,
            CustomerPhotoshootStatus.DECLINED if terminal else CustomerPhotoshootStatus.OBJECTION,
            event_type="OBJECTION_RECOVERY_EXHAUSTED" if terminal else "OBJECTION_RECOVERY_ATTEMPTED",
            metadata=metadata,
        )

    def close_opportunity(self, lifecycle, *, reason, actor="SALES_BRAIN"):
        if lifecycle.status not in {CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION}:
            return lifecycle
        return self.transition(
            lifecycle, CustomerPhotoshootStatus.CLOSED,
            event_type="OPPORTUNITY_INTENTIONALLY_CLOSED",
            metadata={"reason": reason, "actor": actor},
        )

    def context_for_customer(self, *, creator_profile_id, customer_commerce_profile_id):
        self.expire_due(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
        )
        rows = self.repository.list_for_customer(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
        )
        return {row.photoshoot_id: row for row in rows}

    def active_for_customer(self, *, creator_profile_id, customer_commerce_profile_id):
        rows = self.context_for_customer(
            creator_profile_id=creator_profile_id,
            customer_commerce_profile_id=customer_commerce_profile_id,
        )
        return next((row for row in rows.values() if row.status in {
            CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION,
        }), None)

    def record_presentation(self, intent):
        opportunity = self.repository.get_for_purchase_intent(intent)
        if opportunity is None or opportunity.status is not CustomerPhotoshootStatus.ACTIVE:
            return opportunity
        selling_mode_reader = getattr(
            self.repository, "offering_selling_mode", None
        )
        if (
            callable(selling_mode_reader)
            and selling_mode_reader(intent.commercial_offering_id) == "BUNDLE"
        ):
            return self.repository.transition(
                opportunity.lifecycle_id,
                status=CustomerPhotoshootStatus.ACTIVE,
                event_type="BUNDLE_OFFER_PRESENTED",
                purchase_intent_id=intent.purchase_intent_id,
                metadata={
                    "commercial_offering_id": str(
                        intent.commercial_offering_id
                    ),
                    "session_progression": False,
                },
            )
        teaser_ids = set(self.repository.teaser_asset_ids(opportunity.lifecycle_id))
        for asset_id in self.repository.offering_asset_ids(intent.commercial_offering_id):
            if asset_id in teaser_ids:
                continue
            opportunity = self.repository.transition(
                opportunity.lifecycle_id,
                status=CustomerPhotoshootStatus.ACTIVE,
                event_type="PRESENTED",
                asset_id=asset_id,
                purchase_intent_id=intent.purchase_intent_id,
                sales_session_id=(getattr(intent, "created_metadata", {}) or {}).get("sales_session_id"),
            )
        return opportunity

    def record_free_teaser_delivery(
        self, *, lifecycle_id, asset_id: int, provider: str,
        provider_delivery_id: str, metadata=None,
    ):
        """Record confirmed free delivery without fabricating purchase or ownership."""
        if not str(provider_delivery_id or "").strip():
            raise ValueError("Confirmed free teaser delivery requires a provider delivery identifier.")
        getter = getattr(self.repository, "get_by_id", None)
        opportunity = getter(lifecycle_id) if callable(getter) else None
        if opportunity is None or opportunity.status not in {
            CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION,
        }:
            return opportunity
        if int(asset_id) not in set(self.repository.teaser_asset_ids(opportunity.lifecycle_id)):
            raise ValueError("Only a canonical FREE strategy Asset can be recorded as a free teaser delivery.")
        detail = {
            **dict(metadata or {}),
            "delivery_confirmation": "PROVIDER_CONFIRMED",
            "access_recommendation": "FREE",
        }
        recorder = getattr(self.repository, "record_presented_delivery", None)
        if callable(recorder):
            return recorder(
                opportunity.lifecycle_id, asset_id=int(asset_id),
                provider=str(provider), provider_delivery_id=str(provider_delivery_id),
                metadata=detail,
            )
        return self.repository.transition(
            opportunity.lifecycle_id, status=opportunity.status,
            event_type="PRESENTED", asset_id=int(asset_id),
            provider=str(provider), provider_delivery_id=str(provider_delivery_id),
            metadata=detail,
        )

    def bundle_teaser_presented(self, lifecycle) -> bool:
        return any(
            row.get("event_type") == "BUNDLE_TEASER_PRESENTED"
            for row in self.repository.history(lifecycle.lifecycle_id)
        )

    def bundle_offer_presented(self, lifecycle) -> bool:
        return any(
            row.get("event_type") == "BUNDLE_OFFER_PRESENTED"
            for row in self.repository.history(lifecycle.lifecycle_id)
        )

    def record_bundle_teaser_delivery(
        self, *, lifecycle_id, asset_id: int, provider: str,
        provider_delivery_id: str, metadata=None,
    ):
        if not str(provider_delivery_id or "").strip():
            raise ValueError(
                "Confirmed Bundle teaser delivery requires a provider identifier."
            )
        opportunity = self.repository.get_by_id(lifecycle_id)
        if opportunity is None or opportunity.status not in {
            CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION,
        }:
            return opportunity
        authoritative = self.repository.bundle_teaser_asset_id(lifecycle_id)
        if authoritative is None or int(asset_id) != authoritative:
            raise ValueError("Only the canonical Bundle teaser may be presented.")
        return self.repository.transition(
            opportunity.lifecycle_id, status=opportunity.status,
            event_type="BUNDLE_TEASER_PRESENTED", asset_id=int(asset_id),
            provider=str(provider), provider_delivery_id=str(provider_delivery_id),
            metadata={
                **dict(metadata or {}),
                "commercial_role": "BUNDLE_PROMOTIONAL_TEASER",
                "delivery_confirmation": "PROVIDER_CONFIRMED",
                "session_progression": False,
            },
        )

    def record_intent_outcome(self, intent, event_type):
        opportunity = self.repository.get_for_purchase_intent(intent)
        if opportunity is None or opportunity.status not in {
            CustomerPhotoshootStatus.ACTIVE, CustomerPhotoshootStatus.OBJECTION,
        }:
            return opportunity
        if event_type == "DECLINED":
            offered = set(self.repository.offering_asset_ids(intent.commercial_offering_id))
            finale = set(self.repository.finale_video_asset_ids(opportunity.lifecycle_id))
            coverage = self.repository.coverage(opportunity.lifecycle_id)
            core = set(self.repository.required_core_asset_ids(opportunity.lifecycle_id))
            if offered.intersection(finale) and core.issubset(set(coverage["purchased_asset_ids"])):
                return self.decline_finale(opportunity)
            return self.enter_objection(
                opportunity, reason="PURCHASE_INTENT_DECLINED",
                purchase_intent_id=intent.purchase_intent_id,
            )
        return opportunity

    def diagnostics(self, lifecycle):
        return {
            "lifecycle": lifecycle,
            "coverage": self.repository.coverage(lifecycle.lifecycle_id),
            "history": self.repository.history(lifecycle.lifecycle_id),
        }
