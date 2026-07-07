"""Canonical Customer Intelligence boundary for Creator OS.

CustomerIntelligenceService owns provider-neutral customer business memory read
models. It does not call provider APIs, execute commerce, make DecisionEngine
decisions, or migrate existing Telegram Commerce memory yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any

from app.models.business_learning import LearningContext
from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CustomerExperienceProgress,
    CustomerIdentity,
    CustomerIntelligenceReview,
    CustomerIntelligenceReviewSummary,
    CustomerIntelligenceSnapshot,
    CustomerProfile,
    CustomerRelationshipIntelligence,
    CustomerRelationshipStage,
)


class CustomerIntelligenceService:
    """Build provider-neutral customer intelligence from available context."""

    def __init__(self, customer_service: Any | None = None) -> None:
        self.customer_service = customer_service

    def build_customer_snapshot(
        self,
        customer_id: str | int | None = None,
        *,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
        telegram_context: Mapping[str, Any] | None = None,
        customer_profile: Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
        commerce_memory: Any | None = None,
        conversation_state: Any | None = None,
        experience_progression: Any | None = None,
        learning_context: LearningContext | None = None,
        last_interaction_metadata: Mapping[str, Any] | None = None,
    ) -> CustomerIntelligenceSnapshot:
        """Return a read-only Customer Intelligence snapshot.

        Missing data intentionally produces empty/default values. This keeps the
        architecture safe while persistence remains in existing customer systems.
        """

        loaded_customer_summary = customer_summary
        loaded_commerce_summary = commerce_summary
        if self.customer_service is not None:
            loaded_customer_summary = loaded_customer_summary or self._load_summary(
                customer_id,
                provider=provider,
                provider_customer_id=provider_customer_id,
                provider_account_id=provider_account_id,
            )
            loaded_commerce_summary = (
                loaded_commerce_summary
                or self._load_commerce_summary(
                    customer_id,
                    provider=provider,
                    provider_customer_id=provider_customer_id,
                    provider_account_id=provider_account_id,
                )
            )

        identity = self.resolve_customer_identity(
            customer_id=customer_id
            or self._first_value(loaded_customer_summary, "customer_id"),
            provider=provider,
            provider_customer_id=provider_customer_id,
            provider_account_id=provider_account_id,
            telegram_context=telegram_context,
            customer_profile=customer_profile,
            customer_summary=loaded_customer_summary,
        )
        profile = self._profile(
            customer_profile=customer_profile,
            customer_summary=loaded_customer_summary,
            commerce_summary=loaded_commerce_summary,
        )
        memory = self.summarize_customer_memory(
            commerce_memory=commerce_memory,
            commerce_summary=loaded_commerce_summary,
            customer_summary=loaded_customer_summary,
        )
        progress = self._experience_progress(
            conversation_state=conversation_state,
            experience_progression=experience_progression,
            commerce_summary=loaded_commerce_summary,
            customer_summary=loaded_customer_summary,
        )
        relationship_intelligence = self.update_relationship(
            profile=profile,
            commerce_memory=memory,
            experience_progress=progress,
            customer_summary=loaded_customer_summary,
            commerce_summary=loaded_commerce_summary,
            last_interaction_metadata=last_interaction_metadata,
        )
        relationship_stage = relationship_intelligence.stage

        return CustomerIntelligenceSnapshot(
            identity=identity,
            profile=profile,
            relationship_stage=relationship_stage,
            relationship_intelligence=relationship_intelligence,
            commerce_memory=memory,
            experience_progress=progress,
            last_interaction_metadata=dict(last_interaction_metadata or {}),
            compatibility_metadata={
                "source": "customer_intelligence",
                "owner": "CustomerIntelligenceService",
                "read_only": True,
                "provider_neutral": True,
                "calls_provider_apis": False,
                "executes_commerce": False,
                "makes_decision_engine_decisions": False,
                "telegram_commerce_memory_compatibility": True,
                "persistence_owner": "existing_customer_architecture",
                "learning_context_consumed": learning_context is not None,
                "learning_context_evidence_only": True,
                "learning_context_type": (
                    learning_context.context_type if learning_context else None
                ),
            },
        )

    def build_runtime_customer_context(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **snapshot_context: Any,
    ) -> dict[str, Any]:
        """Build provider-neutral customer context for runtime orchestration."""

        resolved = snapshot or self.build_customer_snapshot(**snapshot_context)
        return {
            "type": "customer_intelligence_snapshot",
            "source": "customer_intelligence",
            "owner": "CustomerIntelligenceService",
            "read_only": True,
            "provider_neutral": True,
            "snapshot": self._snapshot_context(resolved),
            "compatibility_metadata": {
                **dict(resolved.compatibility_metadata),
                "runtime_context": True,
            },
        }

    def build_decision_customer_context(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **snapshot_context: Any,
    ) -> dict[str, Any]:
        """Build Customer Intelligence context for DecisionEngine consumption."""

        resolved = snapshot or self.build_customer_snapshot(**snapshot_context)
        return {
            "type": "customer_intelligence_decision_context",
            "source": "customer_intelligence",
            "owner": "CustomerIntelligenceService",
            "decision_owner": "DecisionEngine",
            "generates_decisions": False,
            "snapshot": self._snapshot_context(resolved),
            "relationship": self.summarize_relationship(
                resolved.relationship_intelligence
            ),
            "commerce_history": self.summarize_commerce_history(
                resolved.commerce_memory
            ),
            "compatibility_metadata": {
                **dict(resolved.compatibility_metadata),
                "decision_context": True,
            },
        }

    def build_execution_customer_context(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **snapshot_context: Any,
    ) -> dict[str, Any]:
        """Build Customer Intelligence context for execution handoff."""

        resolved = snapshot or self.build_customer_snapshot(**snapshot_context)
        return {
            "type": "customer_intelligence_execution_context",
            "source": "customer_intelligence",
            "owner": "CustomerIntelligenceService",
            "execution_owner": "CommerceExecutionService",
            "executes_commerce": False,
            "identity": self._identity_context(resolved.identity),
            "relationship": self.summarize_relationship(
                resolved.relationship_intelligence
            ),
            "commerce_history": self.summarize_commerce_history(
                resolved.commerce_memory
            ),
            "experience_progress": self._experience_progress_context(
                resolved.experience_progress
            ),
            "compatibility_metadata": {
                **dict(resolved.compatibility_metadata),
                "execution_context": True,
            },
        }

    def enrich_customer_snapshot(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **updates: Any,
    ) -> CustomerIntelligenceSnapshot:
        """Return a snapshot enriched with partial Customer Intelligence data."""

        base = snapshot or self.build_customer_snapshot()
        profile = self.merge_profile(base.profile, updates.get("customer_profile"))
        commerce_memory = self.normalize_commerce_history(
            updates.get("commerce_memory") or base.commerce_memory
        )
        experience_progress = updates.get("experience_progress") or base.experience_progress
        if not isinstance(experience_progress, CustomerExperienceProgress):
            experience_progress = CustomerExperienceProgress(
                current_experience_id=self._text(
                    self._first_value(experience_progress, "current_experience_id")
                ),
                current_product_id=self._text(
                    self._first_value(experience_progress, "current_product_id")
                ),
                current_asset_id=self._text(
                    self._first_value(experience_progress, "current_asset_id")
                ),
                conversation_progress=self._text(
                    self._first_value(experience_progress, "conversation_progress")
                ),
                commerce_progress=self._text(
                    self._first_value(experience_progress, "commerce_progress")
                ),
                progress_percentage=self._int(
                    self._first_value(experience_progress, "progress_percentage")
                ),
            )
        last_interaction_metadata = {
            **dict(base.last_interaction_metadata),
            **self._safe_mapping(updates.get("last_interaction_metadata")),
        }
        relationship = self.update_relationship(
            profile=profile,
            commerce_memory=commerce_memory,
            experience_progress=experience_progress,
            last_interaction_metadata=last_interaction_metadata,
        )
        return replace(
            base,
            profile=profile,
            relationship_stage=relationship.stage,
            relationship_intelligence=relationship,
            commerce_memory=commerce_memory,
            experience_progress=experience_progress,
            last_interaction_metadata=last_interaction_metadata,
            compatibility_metadata={
                **dict(base.compatibility_metadata),
                **self._safe_mapping(updates.get("compatibility_metadata")),
                "enriched_by": "CustomerIntelligenceService",
            },
        )

    def build_customer_review(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **snapshot_context: Any,
    ) -> CustomerIntelligenceReview:
        """Build a read-only Customer Intelligence presentation model."""

        resolved = snapshot or self.build_customer_snapshot(**snapshot_context)
        relationship = self.summarize_relationship(
            resolved.relationship_intelligence
        )
        commerce_history = self.summarize_commerce_history(
            resolved.commerce_memory
        )
        activity = self.summarize_customer_activity(resolved)
        recommendation_rationale = self._recommendation_rationale(
            relationship=relationship,
            commerce_history=commerce_history,
            activity_summary=activity,
        )

        return CustomerIntelligenceReview(
            customer_id=resolved.identity.customer_id,
            display_name=(
                resolved.profile.preferred_name
                or resolved.profile.display_name
                or resolved.profile.username
            ),
            provider=resolved.identity.provider,
            relationship_stage=resolved.relationship_stage.value,
            engagement_level=resolved.relationship_intelligence.engagement_level,
            commerce_maturity=resolved.relationship_intelligence.commerce_maturity,
            profile=self._profile_context(resolved.profile),
            relationship=relationship,
            commerce_history=commerce_history,
            purchase_history_summary={
                "products_purchased": resolved.commerce_memory.products_purchased,
                "purchased_bundles": resolved.commerce_memory.purchased_bundles,
                "purchased_photoshoots": (
                    resolved.commerce_memory.purchased_photoshoots
                ),
                "purchased_stories": resolved.commerce_memory.purchased_stories,
                "purchase_count": commerce_history["purchase_count"],
                "last_purchase": commerce_history["last_purchase"],
            },
            delivery_history_summary={
                "free_assets_delivered": (
                    resolved.commerce_memory.free_assets_delivered
                ),
                "paid_products_delivered": (
                    resolved.commerce_memory.paid_products_delivered
                ),
                "delivered_free_products": (
                    resolved.commerce_memory.delivered_free_products
                ),
                "delivered_paid_products": (
                    resolved.commerce_memory.delivered_paid_products
                ),
                "delivery_count": commerce_history["delivery_count"],
                "last_delivery": commerce_history["last_delivery"],
            },
            experience_progress=self._experience_progress_context(
                resolved.experience_progress
            ),
            interests=resolved.profile.interests,
            preferences=dict(resolved.profile.preferences),
            tags=resolved.profile.tags,
            customer_segments=resolved.profile.customer_segments,
            recommendations=resolved.relationship_intelligence.recommendations,
            recommendation_rationale=recommendation_rationale,
            activity_summary=activity,
            compatibility_metadata={
                **dict(resolved.compatibility_metadata),
                "customer_review": True,
                "read_only_projection": True,
            },
            metadata={
                "source": "customer_intelligence_review",
                "owner": "CustomerIntelligenceService",
                "presentation_only": True,
                "read_only": True,
                "modifies_customer_state": False,
                "makes_business_decisions": False,
                "executes_commerce": False,
            },
        )

    def build_customer_review_summary(
        self,
        reviews: tuple[CustomerIntelligenceReview, ...]
        | list[CustomerIntelligenceReview]
        | None = None,
        *,
        snapshots: tuple[CustomerIntelligenceSnapshot, ...]
        | list[CustomerIntelligenceSnapshot]
        | None = None,
    ) -> CustomerIntelligenceReviewSummary:
        """Build a read-only dashboard projection for Customer Intelligence."""

        items = tuple(reviews or ())
        if snapshots is not None:
            items = tuple(self.build_customer_review(snapshot) for snapshot in snapshots)

        return CustomerIntelligenceReviewSummary(
            total_customers=len(items),
            relationship_stage_counts=self._count_values(
                item.relationship_stage for item in items
            ),
            engagement_level_counts=self._count_values(
                item.engagement_level for item in items
            ),
            commerce_maturity_counts=self._count_values(
                item.commerce_maturity for item in items
            ),
            customers_with_purchases=sum(
                1
                for item in items
                if self._int(item.purchase_history_summary.get("purchase_count")) > 0
            ),
            customers_with_active_experience=sum(
                1
                for item in items
                if bool(item.experience_progress.get("current_experience_id"))
            ),
            recommendation_counts=self._count_values(
                recommendation
                for item in items
                for recommendation in item.recommendations
            ),
            items=items,
            metadata={
                "source": "customer_intelligence_review",
                "owner": "CustomerIntelligenceService",
                "presentation_only": True,
                "read_only": True,
            },
        )

    def summarize_customer_activity(
        self,
        snapshot: CustomerIntelligenceSnapshot | None = None,
        **snapshot_context: Any,
    ) -> dict[str, Any]:
        """Summarize visible customer activity without changing state."""

        resolved = snapshot or self.build_customer_snapshot(**snapshot_context)
        commerce = self.summarize_commerce_history(resolved.commerce_memory)
        relationship = self.summarize_relationship(
            resolved.relationship_intelligence
        )
        experience = self._experience_progress_context(resolved.experience_progress)
        return {
            "relationship_stage": resolved.relationship_stage.value,
            "engagement_level": relationship["engagement_level"],
            "engagement_score": relationship["engagement_score"],
            "commerce_maturity": relationship["commerce_maturity"],
            "offer_count": commerce["offer_count"],
            "purchase_count": commerce["purchase_count"],
            "delivery_count": commerce["delivery_count"],
            "completed_experience_count": commerce["completed_experience_count"],
            "current_experience_id": experience["current_experience_id"],
            "progress_percentage": experience["progress_percentage"],
            "last_interaction_metadata": dict(
                resolved.last_interaction_metadata
            ),
            "has_visible_activity": any(
                (
                    commerce["has_commerce_history"],
                    experience["current_experience_id"],
                    relationship["engagement_score"],
                )
            ),
        }

    def resolve_customer_identity(
        self,
        customer_id: str | int | None = None,
        *,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
        telegram_context: Mapping[str, Any] | None = None,
        customer_profile: Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
    ) -> CustomerIdentity:
        context = dict(telegram_context or {})
        resolved_provider = provider or self._first_value(context, "provider")
        resolved_provider_customer_id = provider_customer_id or self._first_available(
            self._first_value(context, "provider_customer_id"),
            self._first_value(context, "telegram_user_id"),
            self._first_value(context, "user_id"),
        )
        resolved_provider_account_id = provider_account_id or self._first_available(
            self._first_value(context, "provider_account_id"),
            self._first_value(context, "telegram_chat_id"),
            self._first_value(context, "chat_id"),
        )

        engine_user_id = self._first_value(context, "engine_user_id")
        if engine_user_id and customer_id is None:
            customer_id = engine_user_id
        if resolved_provider is None and (
            resolved_provider_customer_id is not None
            or resolved_provider_account_id is not None
            or engine_user_id is not None
        ):
            resolved_provider = "telegram"

        provider_identity = self.normalize_provider_identity(
            provider=resolved_provider,
            provider_customer_id=resolved_provider_customer_id,
            provider_account_id=resolved_provider_account_id,
            metadata={
                "engine_user_id": engine_user_id,
                "provider_context": context,
            },
        )
        normalized_provider = self._first_value(provider_identity, "provider")
        provider_identities = {}
        platform_identifiers = {}
        if normalized_provider:
            provider_identities[normalized_provider] = provider_identity
            if provider_identity.get("provider_customer_id"):
                platform_identifiers[normalized_provider] = provider_identity[
                    "provider_customer_id"
                ]
        canonical_customer_id = self._text(
            customer_id or self._first_value(customer_summary, "customer_id")
        )

        return CustomerIdentity(
            canonical_customer_id=canonical_customer_id,
            customer_id=canonical_customer_id,
            provider=normalized_provider,
            provider_customer_id=self._first_value(
                provider_identity,
                "provider_customer_id",
            ),
            provider_account_id=self._first_value(
                provider_identity,
                "provider_account_id",
            ),
            telegram_identifier=(
                self._first_value(provider_identity, "provider_customer_id")
                if normalized_provider == "telegram"
                else None
            ),
            platform_identifiers=platform_identifiers,
            provider_identities=provider_identities,
            metadata={
                "source": "customer_intelligence",
                "display_name": self._first_value(
                    customer_profile,
                    "display_name",
                )
                or self._first_value(customer_summary, "display_name"),
            },
        )

    def normalize_provider_identity(
        self,
        *,
        provider: str | None = None,
        provider_customer_id: str | int | None = None,
        provider_account_id: str | int | None = None,
        provider_username: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Normalize one provider identity without provider-specific behavior."""

        normalized = {
            "provider": self._normalize_provider(provider),
            "provider_customer_id": self._text(provider_customer_id),
            "provider_account_id": self._text(provider_account_id),
            "provider_username": self._text(provider_username),
            "metadata": self._safe_mapping(metadata),
        }
        return {
            key: value
            for key, value in normalized.items()
            if value is not None and value != {}
        }

    def normalize_customer_profile(
        self,
        profile: CustomerProfile | Mapping[str, Any] | Any | None = None,
    ) -> CustomerProfile:
        """Build a canonical CustomerProfile from partial profile-like input."""

        if isinstance(profile, CustomerProfile):
            return profile
        return CustomerProfile(
            display_name=self._text(self._first_value(profile, "display_name")),
            username=self._text(self._first_value(profile, "username")),
            preferred_name=self._text(
                self._first_available(
                    self._first_value(profile, "preferred_name"),
                    self._first_value(profile, "name"),
                )
            ),
            timezone=self._text(self._first_value(profile, "timezone")),
            language=self._text(self._first_value(profile, "language")),
            interests=self._text_tuple(self._first_value(profile, "interests")),
            preferences=self._safe_mapping(self._first_value(profile, "preferences")),
            creator_notes=self._text_tuple(
                self._first_available(
                    self._first_value(profile, "creator_notes"),
                    self._first_value(profile, "notes"),
                )
            ),
            tags=self._text_tuple(self._first_value(profile, "tags")),
            customer_segments=self._text_tuple(
                self._first_available(
                    self._first_value(profile, "customer_segments"),
                    self._first_value(profile, "segments"),
                )
            ),
            metadata={
                **self._safe_mapping(self._first_value(profile, "metadata")),
                "source": "customer_intelligence",
            },
        )

    def merge_profile(
        self,
        base_profile: CustomerProfile | Mapping[str, Any] | Any | None = None,
        update: CustomerProfile | Mapping[str, Any] | Any | None = None,
    ) -> CustomerProfile:
        """Merge partial profile data into a canonical CustomerProfile."""

        base = self.normalize_customer_profile(base_profile)
        incoming = self.normalize_customer_profile(update)
        return CustomerProfile(
            display_name=incoming.display_name or base.display_name,
            username=incoming.username or base.username,
            preferred_name=incoming.preferred_name or base.preferred_name,
            timezone=incoming.timezone or base.timezone,
            language=incoming.language or base.language,
            interests=self._merge_text_tuples(base.interests, incoming.interests),
            preferences={
                **dict(base.preferences),
                **dict(incoming.preferences),
            },
            creator_notes=self._merge_text_tuples(
                base.creator_notes,
                incoming.creator_notes,
            ),
            tags=self._merge_text_tuples(base.tags, incoming.tags),
            customer_segments=self._merge_text_tuples(
                base.customer_segments,
                incoming.customer_segments,
            ),
            metadata={
                **dict(base.metadata),
                **dict(incoming.metadata),
                "source": "customer_intelligence",
            },
        )

    def update_preferences(
        self,
        profile: CustomerProfile | Mapping[str, Any] | Any | None,
        preferences: Mapping[str, Any] | None,
    ) -> CustomerProfile:
        """Return a profile with merged preference values."""

        normalized = self.normalize_customer_profile(profile)
        return replace(
            normalized,
            preferences={
                **dict(normalized.preferences),
                **self._safe_mapping(preferences),
            },
        )

    def update_interests(
        self,
        profile: CustomerProfile | Mapping[str, Any] | Any | None,
        interests: Any,
    ) -> CustomerProfile:
        """Return a profile with interests appended and deduplicated."""

        normalized = self.normalize_customer_profile(profile)
        return replace(
            normalized,
            interests=self._merge_text_tuples(
                normalized.interests,
                self._text_tuple(interests),
            ),
        )

    def summarize_profile(
        self,
        profile: CustomerProfile | Mapping[str, Any] | Any | None,
    ) -> dict[str, Any]:
        """Return a compact provider-neutral profile summary."""

        normalized = self.normalize_customer_profile(profile)
        return {
            "display_name": normalized.display_name,
            "username": normalized.username,
            "preferred_name": normalized.preferred_name,
            "timezone": normalized.timezone,
            "language": normalized.language,
            "interests": normalized.interests,
            "preferences": dict(normalized.preferences),
            "creator_notes": normalized.creator_notes,
            "tags": normalized.tags,
            "customer_segments": normalized.customer_segments,
            "metadata": dict(normalized.metadata),
            "summary_label": (
                normalized.preferred_name
                or normalized.display_name
                or normalized.username
                or "Unknown Customer"
            ),
            "has_profile_data": any(
                (
                    normalized.display_name,
                    normalized.username,
                    normalized.preferred_name,
                    normalized.timezone,
                    normalized.language,
                    normalized.interests,
                    normalized.preferences,
                    normalized.creator_notes,
                    normalized.tags,
                    normalized.customer_segments,
                )
            ),
        }

    def normalize_commerce_history(
        self,
        commerce_memory: CustomerCommerceMemory | Mapping[str, Any] | Any | None = None,
    ) -> CustomerCommerceMemory:
        """Build canonical provider-neutral commerce history from partial input."""

        if isinstance(commerce_memory, CustomerCommerceMemory):
            return commerce_memory
        return CustomerCommerceMemory(
            products_offered=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "products_offered"),
                    self._first_value(commerce_memory, "previous_offers"),
                )
            ),
            products_purchased=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "products_purchased"),
                    self._first_value(commerce_memory, "purchased_products"),
                )
            ),
            free_assets_delivered=self._text_tuple(
                self._first_value(commerce_memory, "free_assets_delivered")
            ),
            paid_products_delivered=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "paid_products_delivered"),
                    self._first_value(commerce_memory, "paid_media_links_delivered"),
                )
            ),
            delivered_free_products=self._text_tuple(
                self._first_value(commerce_memory, "delivered_free_products")
            ),
            delivered_paid_products=self._text_tuple(
                self._first_value(commerce_memory, "delivered_paid_products")
            ),
            purchased_bundles=self._text_tuple(
                self._first_value(commerce_memory, "purchased_bundles")
            ),
            purchased_photoshoots=self._text_tuple(
                self._first_value(commerce_memory, "purchased_photoshoots")
            ),
            purchased_stories=self._text_tuple(
                self._first_value(commerce_memory, "purchased_stories")
            ),
            completed_experience_ids=self._text_tuple(
                self._first_value(commerce_memory, "completed_experience_ids")
            ),
            previous_offers=self._text_tuple(
                self._first_value(commerce_memory, "previous_offers")
            ),
            previous_purchases=self._text_tuple(
                self._first_value(commerce_memory, "previous_purchases")
            ),
            declined_offers=self._text_tuple(
                self._first_value(commerce_memory, "declined_offers")
            ),
            offer_outcomes=self._text_mapping(
                self._first_value(commerce_memory, "offer_outcomes")
            ),
            offer_timestamps=self._safe_mapping(
                self._first_value(commerce_memory, "offer_timestamps")
            ),
            purchase_timestamps=self._safe_mapping(
                self._first_value(commerce_memory, "purchase_timestamps")
            ),
            delivery_timestamps=self._safe_mapping(
                self._first_value(commerce_memory, "delivery_timestamps")
            ),
            offer_events=self._mapping_tuple(
                self._first_value(commerce_memory, "offer_events")
            ),
            purchase_events=self._mapping_tuple(
                self._first_value(commerce_memory, "purchase_events")
            ),
            delivery_events=self._mapping_tuple(
                self._first_value(commerce_memory, "delivery_events")
            ),
            completed_experience_events=self._mapping_tuple(
                self._first_value(commerce_memory, "completed_experience_events")
            ),
            duplicate_prevention_signals=self._text_tuple(
                self._first_value(commerce_memory, "duplicate_prevention_signals")
            ),
            last_purchase=self._safe_mapping(
                self._first_value(commerce_memory, "last_purchase")
            ),
            last_delivery=self._safe_mapping(
                self._first_value(commerce_memory, "last_delivery")
            ),
            customer_spending_summary=self._safe_mapping(
                self._first_value(commerce_memory, "customer_spending_summary")
            ),
            customer_engagement_summary=self._safe_mapping(
                self._first_value(commerce_memory, "customer_engagement_summary")
            ),
            commerce_metadata=self._safe_mapping(
                self._first_value(commerce_memory, "commerce_metadata")
            ),
            metadata={
                **self._safe_mapping(self._first_value(commerce_memory, "metadata")),
                "source": "customer_intelligence",
                "canonical_commerce_history": True,
            },
        )

    def record_offer(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        *,
        product_id: str | int | None = None,
        offer_id: str | int | None = None,
        offered_at: Any | None = None,
        outcome: str | None = None,
        declined: bool = False,
        metadata: Mapping[str, Any] | None = None,
    ) -> CustomerCommerceMemory:
        """Return commerce history with a provider-neutral offer event recorded."""

        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        offer = self._text(offer_id) or product
        if product is None and offer is None:
            return history

        signal = self._duplicate_signal("offer", offer)
        duplicate_signals = history.duplicate_prevention_signals
        offer_events = history.offer_events
        if signal in duplicate_signals:
            return history

        event = self._commerce_event(
            event_type="offer",
            product_id=product,
            event_id=offer,
            timestamp=offered_at,
            outcome=outcome or ("declined" if declined else None),
            metadata=metadata,
        )
        offer_key = offer or product
        return replace(
            history,
            products_offered=self._merge_text_tuples(
                history.products_offered,
                (product,),
            ),
            previous_offers=self._merge_text_tuples(
                history.previous_offers,
                (offer_key,),
            ),
            declined_offers=(
                self._merge_text_tuples(history.declined_offers, (offer_key,))
                if declined
                else history.declined_offers
            ),
            offer_outcomes={
                **dict(history.offer_outcomes),
                **({offer_key: event["outcome"]} if event.get("outcome") else {}),
            },
            offer_timestamps={
                **dict(history.offer_timestamps),
                **({offer_key: offered_at} if offered_at is not None else {}),
            },
            offer_events=offer_events + (event,),
            duplicate_prevention_signals=self._merge_text_tuples(
                duplicate_signals,
                (signal,),
            ),
        )

    def record_purchase(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        *,
        product_id: str | int | None = None,
        purchase_id: str | int | None = None,
        purchased_at: Any | None = None,
        product_type: str | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CustomerCommerceMemory:
        """Return commerce history with a provider-neutral purchase recorded."""

        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        purchase = self._text(purchase_id) or product
        if product is None and purchase is None:
            return history

        signal = self._duplicate_signal("purchase", purchase)
        if signal in history.duplicate_prevention_signals:
            return history

        normalized_type = self._normalize_product_type(product_type)
        event = self._commerce_event(
            event_type="purchase",
            product_id=product,
            event_id=purchase,
            timestamp=purchased_at,
            product_type=normalized_type,
            metadata=metadata,
        )
        purchase_key = purchase or product
        return replace(
            history,
            products_purchased=self._merge_text_tuples(
                history.products_purchased,
                (product,),
            ),
            previous_purchases=self._merge_text_tuples(
                history.previous_purchases,
                (purchase_key,),
            ),
            purchased_bundles=(
                self._merge_text_tuples(history.purchased_bundles, (product,))
                if normalized_type == "bundle"
                else history.purchased_bundles
            ),
            purchased_photoshoots=(
                self._merge_text_tuples(history.purchased_photoshoots, (product,))
                if normalized_type == "photoshoot"
                else history.purchased_photoshoots
            ),
            purchased_stories=(
                self._merge_text_tuples(history.purchased_stories, (product,))
                if normalized_type == "story"
                else history.purchased_stories
            ),
            purchase_timestamps={
                **dict(history.purchase_timestamps),
                **({purchase_key: purchased_at} if purchased_at is not None else {}),
            },
            purchase_events=history.purchase_events + (event,),
            last_purchase=event,
            customer_spending_summary={
                **dict(history.customer_spending_summary),
                "purchase_count": len(history.purchase_events) + 1,
            },
            duplicate_prevention_signals=self._merge_text_tuples(
                history.duplicate_prevention_signals,
                (signal,),
            ),
        )

    def record_delivery(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        *,
        product_id: str | int | None = None,
        asset_id: str | int | None = None,
        delivery_id: str | int | None = None,
        delivery_type: str | None = None,
        delivered_at: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CustomerCommerceMemory:
        """Return commerce history with a provider-neutral delivery recorded."""

        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        asset = self._text(asset_id)
        delivery = self._text(delivery_id) or product or asset
        if delivery is None:
            return history

        signal = self._duplicate_signal("delivery", delivery)
        if signal in history.duplicate_prevention_signals:
            return history

        normalized_type = self._normalize_delivery_type(delivery_type)
        event = self._commerce_event(
            event_type="delivery",
            product_id=product,
            asset_id=asset,
            event_id=delivery,
            timestamp=delivered_at,
            delivery_type=normalized_type,
            metadata=metadata,
        )
        is_paid = normalized_type == "paid"
        delivery_item = product or asset
        return replace(
            history,
            free_assets_delivered=(
                self._merge_text_tuples(history.free_assets_delivered, (asset,))
                if not is_paid
                else history.free_assets_delivered
            ),
            paid_products_delivered=(
                self._merge_text_tuples(history.paid_products_delivered, (delivery_item,))
                if is_paid
                else history.paid_products_delivered
            ),
            delivered_free_products=(
                self._merge_text_tuples(history.delivered_free_products, (delivery_item,))
                if not is_paid
                else history.delivered_free_products
            ),
            delivered_paid_products=(
                self._merge_text_tuples(history.delivered_paid_products, (delivery_item,))
                if is_paid
                else history.delivered_paid_products
            ),
            delivery_timestamps={
                **dict(history.delivery_timestamps),
                **({delivery: delivered_at} if delivered_at is not None else {}),
            },
            delivery_events=history.delivery_events + (event,),
            last_delivery=event,
            duplicate_prevention_signals=self._merge_text_tuples(
                history.duplicate_prevention_signals,
                (signal,),
            ),
        )

    def record_completed_experience(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        *,
        experience_id: str | int | None = None,
        completed_at: Any | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> CustomerCommerceMemory:
        """Return commerce history with a completed experience recorded."""

        history = self.normalize_commerce_history(commerce_history)
        experience = self._text(experience_id)
        if experience is None:
            return history

        signal = self._duplicate_signal("experience", experience)
        if signal in history.duplicate_prevention_signals:
            return history

        event = self._commerce_event(
            event_type="completed_experience",
            event_id=experience,
            experience_id=experience,
            timestamp=completed_at,
            metadata=metadata,
        )
        return replace(
            history,
            completed_experience_ids=self._merge_text_tuples(
                history.completed_experience_ids,
                (experience,),
            ),
            completed_experience_events=history.completed_experience_events + (event,),
            duplicate_prevention_signals=self._merge_text_tuples(
                history.duplicate_prevention_signals,
                (signal,),
            ),
        )

    def has_seen_product(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        product_id: str | int | None,
    ) -> bool:
        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        return bool(product and product in history.products_offered)

    def has_purchased_product(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        product_id: str | int | None,
    ) -> bool:
        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        purchased = self._merge_text_tuples(
            history.products_purchased,
            history.purchased_bundles,
            history.purchased_photoshoots,
            history.purchased_stories,
        )
        return bool(product and product in purchased)

    def has_delivered_product(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        product_id: str | int | None,
    ) -> bool:
        history = self.normalize_commerce_history(commerce_history)
        product = self._text(product_id)
        delivered = self._merge_text_tuples(
            history.delivered_free_products,
            history.delivered_paid_products,
            history.paid_products_delivered,
        )
        return bool(product and product in delivered)

    def has_completed_experience(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
        experience_id: str | int | None,
    ) -> bool:
        history = self.normalize_commerce_history(commerce_history)
        experience = self._text(experience_id)
        return bool(experience and experience in history.completed_experience_ids)

    def summarize_commerce_history(
        self,
        commerce_history: CustomerCommerceMemory | Mapping[str, Any] | Any | None,
    ) -> dict[str, Any]:
        """Return a compact provider-neutral commerce history summary."""

        history = self.normalize_commerce_history(commerce_history)
        return {
            "products_offered": history.products_offered,
            "products_purchased": history.products_purchased,
            "delivered_free_products": history.delivered_free_products,
            "delivered_paid_products": history.delivered_paid_products,
            "completed_experience_ids": history.completed_experience_ids,
            "declined_offers": history.declined_offers,
            "offer_count": len(history.offer_events) or len(history.products_offered),
            "purchase_count": len(history.purchase_events)
            or len(history.products_purchased),
            "delivery_count": len(history.delivery_events),
            "completed_experience_count": len(history.completed_experience_ids),
            "duplicate_signal_count": len(history.duplicate_prevention_signals),
            "last_purchase": dict(history.last_purchase),
            "last_delivery": dict(history.last_delivery),
            "has_commerce_history": any(
                (
                    history.products_offered,
                    history.products_purchased,
                    history.delivered_free_products,
                    history.delivered_paid_products,
                    history.completed_experience_ids,
                    history.offer_events,
                    history.purchase_events,
                    history.delivery_events,
                )
            ),
            "metadata": {
                **dict(history.commerce_metadata),
                "source": "customer_intelligence",
                "canonical_commerce_history": True,
            },
        }

    def summarize_customer_memory(
        self,
        *,
        commerce_memory: Any | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
        customer_summary: Mapping[str, Any] | None = None,
    ) -> CustomerCommerceMemory:
        commerce_summary = dict(commerce_summary or {})
        summary_memory = self._mapping_or_empty(
            commerce_summary.get("commerce_memory")
        )

        products_purchased = self._text_tuple(
            self._first_available(
                self._first_value(commerce_memory, "purchased_products"),
                self._first_value(commerce_memory, "products_purchased"),
                summary_memory.get("purchased_products"),
                commerce_summary.get("products_purchased"),
                commerce_summary.get("products_owned"),
            )
        )
        products_offered = self._text_tuple(
            self._first_available(
                self._first_value(commerce_memory, "previous_offers"),
                summary_memory.get("previous_offers"),
                self._first_value(commerce_summary.get("products_offered"), "items"),
                self._first_value(customer_summary, "recent_product_ids"),
            )
        )
        free_assets = self._text_tuple(
            self._first_available(
                self._first_value(commerce_memory, "free_assets_delivered"),
                summary_memory.get("free_assets_delivered"),
            )
        )
        paid_products = self._text_tuple(
            self._first_available(
                self._first_value(commerce_memory, "paid_products_delivered"),
                self._first_value(commerce_memory, "paid_media_links_delivered"),
                summary_memory.get("paid_products_delivered"),
                summary_memory.get("paid_media_links_delivered"),
            )
        )

        return CustomerCommerceMemory(
            products_offered=products_offered,
            products_purchased=products_purchased,
            free_assets_delivered=free_assets,
            paid_products_delivered=paid_products,
            delivered_free_products=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "delivered_free_products"),
                    summary_memory.get("delivered_free_products"),
                )
            ),
            delivered_paid_products=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "delivered_paid_products"),
                    summary_memory.get("delivered_paid_products"),
                )
            ),
            purchased_bundles=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "purchased_bundles"),
                    summary_memory.get("purchased_bundles"),
                )
            ),
            purchased_photoshoots=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "purchased_photoshoots"),
                    summary_memory.get("purchased_photoshoots"),
                )
            ),
            purchased_stories=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "purchased_stories"),
                    summary_memory.get("purchased_stories"),
                )
            ),
            completed_experience_ids=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "completed_experience_ids"),
                    summary_memory.get("completed_experience_ids"),
                    self._first_value(customer_summary, "completed_experience_ids"),
                )
            ),
            previous_offers=products_offered,
            previous_purchases=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "previous_purchases"),
                    summary_memory.get("previous_purchases"),
                    products_purchased,
                )
            ),
            declined_offers=self._text_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "declined_offers"),
                    summary_memory.get("declined_offers"),
                )
            ),
            offer_outcomes=self._text_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "offer_outcomes"),
                    summary_memory.get("offer_outcomes"),
                )
            ),
            offer_timestamps=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "offer_timestamps"),
                    summary_memory.get("offer_timestamps"),
                )
            ),
            purchase_timestamps=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "purchase_timestamps"),
                    summary_memory.get("purchase_timestamps"),
                )
            ),
            delivery_timestamps=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "delivery_timestamps"),
                    summary_memory.get("delivery_timestamps"),
                )
            ),
            offer_events=self._mapping_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "offer_events"),
                    summary_memory.get("offer_events"),
                )
            ),
            purchase_events=self._mapping_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "purchase_events"),
                    summary_memory.get("purchase_events"),
                )
            ),
            delivery_events=self._mapping_tuple(
                self._first_available(
                    self._first_value(commerce_memory, "delivery_events"),
                    summary_memory.get("delivery_events"),
                )
            ),
            completed_experience_events=self._mapping_tuple(
                self._first_available(
                    self._first_value(
                        commerce_memory,
                        "completed_experience_events",
                    ),
                    summary_memory.get("completed_experience_events"),
                )
            ),
            duplicate_prevention_signals=self._text_tuple(
                self._first_available(
                    self._first_value(
                        commerce_memory,
                        "duplicate_prevention_signals",
                    ),
                    summary_memory.get("duplicate_prevention_signals"),
                )
            ),
            last_purchase=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "last_purchase"),
                    summary_memory.get("last_purchase"),
                    commerce_summary.get("purchase_summary"),
                )
            ),
            last_delivery=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "last_delivery"),
                    summary_memory.get("last_delivery"),
                    self._first_value(
                        commerce_summary.get("delivery_decision"),
                        "last_delivery",
                    ),
                )
            ),
            customer_spending_summary=self._safe_mapping(
                self._first_available(
                    self._first_value(
                        commerce_memory,
                        "customer_spending_summary",
                    ),
                    summary_memory.get("customer_spending_summary"),
                    commerce_summary.get("purchase_summary"),
                )
            ),
            customer_engagement_summary=self._safe_mapping(
                self._first_available(
                    self._first_value(
                        commerce_memory,
                        "customer_engagement_summary",
                    ),
                    summary_memory.get("customer_engagement_summary"),
                    {
                        "message_count": self._first_value(
                            customer_summary,
                            "message_count",
                        )
                        or 0,
                        "offer_count": self._first_value(
                            customer_summary,
                            "offer_count",
                        )
                        or 0,
                    },
                )
            ),
            commerce_metadata=self._safe_mapping(
                self._first_available(
                    self._first_value(commerce_memory, "commerce_metadata"),
                    summary_memory.get("commerce_metadata"),
                )
            ),
            metadata={
                "source": "customer_intelligence",
                "canonical_commerce_history": True,
                "compatibility_sources": (
                    "CustomerService",
                    "TelegramCommerceMemory",
                ),
            },
        )

    def update_relationship(
        self,
        *,
        profile: CustomerProfile | Mapping[str, Any] | Any | None = None,
        commerce_memory: CustomerCommerceMemory | Any | None = None,
        experience_progress: CustomerExperienceProgress | Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
        conversation_activity: Mapping[str, Any] | None = None,
        last_interaction_metadata: Mapping[str, Any] | None = None,
    ) -> CustomerRelationshipIntelligence:
        """Return provider-neutral relationship intelligence read model."""

        normalized_profile = self.normalize_customer_profile(profile)
        normalized_memory = self.normalize_commerce_history(commerce_memory)
        engagement = self.calculate_engagement(
            profile=normalized_profile,
            commerce_memory=normalized_memory,
            experience_progress=experience_progress,
            customer_summary=customer_summary,
            conversation_activity=conversation_activity,
        )
        commerce_maturity = self.determine_commerce_maturity(
            commerce_memory=normalized_memory,
            customer_summary=customer_summary,
            commerce_summary=commerce_summary,
        )
        stage = self.infer_relationship_stage(
            profile=normalized_profile,
            commerce_memory=normalized_memory,
            experience_progress=experience_progress,
            customer_summary=customer_summary,
            commerce_summary=commerce_summary,
            engagement=engagement,
            commerce_maturity=commerce_maturity,
            last_interaction_metadata=last_interaction_metadata,
        )
        recommendations = self.recommend_relationship_focus(
            relationship_stage=stage,
            engagement=engagement,
            commerce_maturity=commerce_maturity,
            commerce_memory=normalized_memory,
            experience_progress=experience_progress,
            last_interaction_metadata=last_interaction_metadata,
        )

        return CustomerRelationshipIntelligence(
            stage=stage,
            engagement_score=engagement["score"],
            engagement_level=engagement["level"],
            commerce_maturity=commerce_maturity,
            relationship_progression={
                "stage": stage.value,
                "commerce_maturity": commerce_maturity,
                "experience_active": bool(
                    self._first_value(experience_progress, "current_experience_id")
                    or self._first_value(experience_progress, "conversation_progress")
                ),
            },
            engagement_indicators=engagement,
            recommendations=recommendations,
            primary_recommendation=(recommendations[0] if recommendations else None),
            last_interaction_metadata=dict(last_interaction_metadata or {}),
            metadata={
                "source": "customer_intelligence",
                "provider_neutral": True,
                "read_only": True,
                "generates_conversation_text": False,
                "executes_commerce": False,
                "makes_decision_engine_decisions": False,
            },
        )

    def calculate_engagement(
        self,
        *,
        profile: CustomerProfile | Mapping[str, Any] | Any | None = None,
        commerce_memory: CustomerCommerceMemory | Any | None = None,
        experience_progress: CustomerExperienceProgress | Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        conversation_activity: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Calculate provider-neutral engagement indicators."""

        normalized_profile = self.normalize_customer_profile(profile)
        normalized_memory = self.normalize_commerce_history(commerce_memory)
        engagement_summary = self._safe_mapping(
            self._first_value(normalized_memory, "customer_engagement_summary")
        )
        message_count = self._int(
            self._first_available(
                self._first_value(conversation_activity, "message_count"),
                self._first_value(customer_summary, "message_count"),
                engagement_summary.get("message_count"),
            )
        )
        offer_count = self._int(
            self._first_available(
                self._first_value(customer_summary, "offer_count"),
                engagement_summary.get("offer_count"),
                len(normalized_memory.offer_events)
                or len(normalized_memory.products_offered),
            )
        )
        delivery_count = len(normalized_memory.delivery_events) or len(
            self._merge_text_tuples(
                normalized_memory.delivered_free_products,
                normalized_memory.delivered_paid_products,
                normalized_memory.free_assets_delivered,
                normalized_memory.paid_products_delivered,
            )
        )
        purchase_count = len(normalized_memory.purchase_events) or self._int(
            self._first_available(
                self._first_value(
                    normalized_memory.customer_spending_summary,
                    "purchase_count",
                ),
                len(normalized_memory.products_purchased),
            )
        )
        experience_active = bool(
            self._first_value(experience_progress, "current_experience_id")
            or self._first_value(experience_progress, "conversation_progress")
            or self._first_value(experience_progress, "commerce_progress")
        )
        completed_experience_count = len(
            self._merge_text_tuples(
                normalized_memory.completed_experience_ids,
                self._first_value(experience_progress, "completed_experience_ids"),
            )
        )

        score = min(
            100,
            message_count * 4
            + offer_count * 5
            + delivery_count * 8
            + purchase_count * 15
            + completed_experience_count * 10
            + (10 if experience_active else 0)
            + len(normalized_profile.interests) * 2
            + len(normalized_profile.tags) * 2,
        )
        if score >= 70:
            level = "high"
        elif score >= 35:
            level = "medium"
        elif score > 0:
            level = "low"
        else:
            level = "none"

        return {
            "score": score,
            "level": level,
            "message_count": message_count,
            "offer_count": offer_count,
            "delivery_count": delivery_count,
            "purchase_count": purchase_count,
            "completed_experience_count": completed_experience_count,
            "experience_active": experience_active,
            "profile_signal_count": len(normalized_profile.interests)
            + len(normalized_profile.tags)
            + len(normalized_profile.customer_segments),
        }

    def determine_commerce_maturity(
        self,
        *,
        commerce_memory: CustomerCommerceMemory | Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
    ) -> str:
        """Return high-level provider-neutral commerce maturity."""

        history = self.normalize_commerce_history(commerce_memory)
        purchase_count = len(history.purchase_events) or self._int(
            self._first_available(
                self._first_value(history.customer_spending_summary, "purchase_count"),
                self._first_value(customer_summary, "purchase_count"),
                self._first_value(commerce_summary, "purchase_summary", "purchase_count"),
                len(history.products_purchased),
            )
        )
        spend_cents = self._int(
            self._first_available(
                self._first_value(history.customer_spending_summary, "total_spend_cents"),
                self._first_value(commerce_summary, "purchase_summary", "total_spend_cents"),
            )
        )
        if spend_cents >= 10000 or purchase_count >= 5:
            return "vip"
        if purchase_count >= 2:
            return "repeat_buyer"
        if purchase_count == 1:
            return "buyer"
        if history.products_offered or history.offer_events:
            return "offer_aware"
        return "none"

    def summarize_relationship(
        self,
        relationship: CustomerRelationshipIntelligence | Mapping[str, Any] | Any | None = None,
        **context: Any,
    ) -> dict[str, Any]:
        """Return a compact provider-neutral relationship summary."""

        if isinstance(relationship, CustomerRelationshipIntelligence):
            intelligence = relationship
        else:
            intelligence = self.update_relationship(**context)
        return {
            "stage": intelligence.stage.value,
            "engagement_score": intelligence.engagement_score,
            "engagement_level": intelligence.engagement_level,
            "commerce_maturity": intelligence.commerce_maturity,
            "primary_recommendation": intelligence.primary_recommendation,
            "recommendations": intelligence.recommendations,
            "relationship_progression": dict(intelligence.relationship_progression),
            "metadata": dict(intelligence.metadata),
        }

    def recommend_relationship_focus(
        self,
        *,
        relationship_stage: CustomerRelationshipStage | str | None = None,
        engagement: Mapping[str, Any] | None = None,
        commerce_maturity: str | None = None,
        commerce_memory: CustomerCommerceMemory | Any | None = None,
        experience_progress: CustomerExperienceProgress | Any | None = None,
        last_interaction_metadata: Mapping[str, Any] | None = None,
    ) -> tuple[str, ...]:
        """Return high-level business guidance only, not conversation text."""

        if isinstance(relationship_stage, CustomerRelationshipStage):
            stage = relationship_stage
        else:
            try:
                stage = CustomerRelationshipStage(
                    self._normalize_provider(relationship_stage) or "new"
                )
            except ValueError:
                stage = CustomerRelationshipStage.NEW
        maturity = commerce_maturity or "none"
        recommendations: list[str] = []

        if stage == CustomerRelationshipStage.DORMANT:
            recommendations.append("Re-engage customer")
        elif self._first_value(experience_progress, "current_experience_id"):
            recommendations.append("Continue current Experience")
        elif maturity == "vip":
            recommendations.append("Prioritize VIP relationship care")
        elif maturity == "repeat_buyer":
            recommendations.append("Customer likely ready for bundles")
        elif maturity == "buyer":
            recommendations.append("Customer ready for premium offers")
        elif self._int(self._first_value(engagement, "score")) >= 45:
            recommendations.append("Customer ready for premium offers")
        else:
            recommendations.append("Continue relationship building")

        if stage in {
            CustomerRelationshipStage.NEW,
            CustomerRelationshipStage.RETURNING,
            CustomerRelationshipStage.ACTIVE,
        }:
            recommendations.append("Continue relationship building")
        if (
            self._first_value(last_interaction_metadata, "days_since_last_interaction")
            is not None
            and self._int(
                self._first_value(
                    last_interaction_metadata,
                    "days_since_last_interaction",
                )
            )
            >= 30
            and "Re-engage customer" not in recommendations
        ):
            recommendations.append("Re-engage customer")

        return tuple(dict.fromkeys(recommendations))

    def infer_relationship_stage(
        self,
        *,
        profile: CustomerProfile | Mapping[str, Any] | Any | None = None,
        commerce_memory: CustomerCommerceMemory | Any | None = None,
        experience_progress: CustomerExperienceProgress | Any | None = None,
        customer_summary: Mapping[str, Any] | None = None,
        commerce_summary: Mapping[str, Any] | None = None,
        engagement: Mapping[str, Any] | None = None,
        commerce_maturity: str | None = None,
        last_interaction_metadata: Mapping[str, Any] | None = None,
    ) -> CustomerRelationshipStage:
        if self._is_dormant(last_interaction_metadata, customer_summary):
            return CustomerRelationshipStage.DORMANT

        normalized_profile = self.normalize_customer_profile(profile)
        profile_segments = {
            self._normalize_provider(segment)
            for segment in normalized_profile.customer_segments + normalized_profile.tags
        }
        maturity = commerce_maturity or self.determine_commerce_maturity(
            commerce_memory=commerce_memory,
            customer_summary=customer_summary,
            commerce_summary=commerce_summary,
        )
        if maturity == "vip" or "vip" in profile_segments:
            return CustomerRelationshipStage.VIP
        if maturity == "repeat_buyer":
            return CustomerRelationshipStage.REPEAT_PURCHASER
        if maturity == "buyer":
            return CustomerRelationshipStage.PURCHASER

        purchased_products = self._text_tuple(
            self._first_value(commerce_memory, "products_purchased")
            or self._first_value(commerce_memory, "purchased_products")
        )
        purchase_count = int(
            self._first_value(
                self._first_value(commerce_memory, "customer_spending_summary"),
                "purchase_count",
            )
            or self._first_value(customer_summary, "purchase_count")
            or self._first_value(commerce_summary, "purchase_summary", "purchase_count")
            or 0
        )
        if purchased_products or purchase_count > 0:
            return CustomerRelationshipStage.PURCHASER

        engagement = engagement or self.calculate_engagement(
            profile=normalized_profile,
            commerce_memory=commerce_memory,
            experience_progress=experience_progress,
            customer_summary=customer_summary,
        )
        if self._int(self._first_value(engagement, "score")) >= 70:
            return CustomerRelationshipStage.ENGAGED

        message_count = int(
            self._first_value(customer_summary, "message_count")
            or self._first_value(
                self._first_value(commerce_memory, "customer_engagement_summary"),
                "message_count",
            )
            or 0
        )
        has_active_progress = bool(
            self._first_value(experience_progress, "current_experience_id")
            or self._first_value(experience_progress, "current_product_id")
            or self._first_value(experience_progress, "conversation_progress")
            or self._first_value(experience_progress, "commerce_progress")
        )
        delivered = bool(
            self._text_tuple(
                self._first_value(commerce_memory, "free_assets_delivered")
            )
            or self._text_tuple(
                self._first_value(commerce_memory, "paid_products_delivered")
            )
        )
        if message_count >= 5 or has_active_progress or delivered:
            return CustomerRelationshipStage.ACTIVE

        offered = bool(
            self._text_tuple(self._first_value(commerce_memory, "products_offered"))
            or self._text_tuple(self._first_value(commerce_memory, "previous_offers"))
        )
        if message_count > 0 or offered:
            return CustomerRelationshipStage.RETURNING

        return CustomerRelationshipStage.NEW

    def _profile(
        self,
        *,
        customer_profile: Any | None,
        customer_summary: Mapping[str, Any] | None,
        commerce_summary: Mapping[str, Any] | None,
    ) -> CustomerProfile:
        preferred_tags = self._text_tuple(
            self._first_value(customer_profile, "preferred_tags")
            or self._first_value(customer_summary, "preferred_tags")
        )
        preferred_themes = self._text_tuple(
            self._first_value(customer_profile, "preferred_themes")
            or self._first_value(customer_summary, "preferred_themes")
        )
        summary_profile = self.normalize_customer_profile(
            {
                "display_name": self._first_value(customer_summary, "display_name"),
                "username": self._first_value(customer_summary, "username"),
                "preferred_name": self._first_value(
                    customer_summary,
                    "preferred_name",
                ),
                "timezone": self._first_value(customer_summary, "timezone"),
                "language": self._first_value(customer_summary, "language"),
                "interests": tuple(dict.fromkeys(preferred_tags + preferred_themes)),
                "creator_notes": self._first_value(
                    customer_summary,
                    "creator_notes",
                ),
                "tags": self._first_value(customer_summary, "tags"),
                "customer_segments": self._first_value(
                    customer_summary,
                    "customer_segments",
                ),
            }
        )
        profile = self.merge_profile(summary_profile, customer_profile)
        return replace(
            profile,
            preferences={
                **dict(profile.preferences),
                "value_tier": self._first_value(customer_summary, "value_tier"),
                "buyer_tier": self._first_value(customer_summary, "buyer_tier"),
                "customer_value": self._safe_mapping(
                    self._first_value(commerce_summary, "customer_value")
                ),
            },
            metadata={
                **dict(profile.metadata),
                "source": "customer_intelligence",
                "canonical_profile": True,
            },
        )

    def _experience_progress(
        self,
        *,
        conversation_state: Any | None,
        experience_progression: Any | None,
        commerce_summary: Mapping[str, Any] | None,
        customer_summary: Mapping[str, Any] | None,
    ) -> CustomerExperienceProgress:
        telegram_state = self._mapping_or_empty(
            self._first_value(commerce_summary, "telegram_conversation_state")
        )
        progression_summary = self._mapping_or_empty(
            self._first_value(commerce_summary, "experience_progression")
        )
        current_experience = self._first_available(
            self._first_value(experience_progression, "current_experience_id"),
            self._first_value(conversation_state, "current_experience_id"),
            telegram_state.get("current_experience"),
            self._first_value(customer_summary, "current_experience_id"),
        )
        current_product = self._first_available(
            self._first_value(experience_progression, "current_product_id"),
            self._first_value(conversation_state, "current_product_id"),
            telegram_state.get("current_product"),
        )
        return CustomerExperienceProgress(
            current_experience_id=self._text(current_experience),
            current_product_id=self._text(current_product),
            current_asset_id=self._text(
                self._first_value(conversation_state, "current_asset_id")
            ),
            conversation_progress=self._text(
                self._first_available(
                    self._first_value(conversation_state, "conversation_mode"),
                    telegram_state.get("conversation_status"),
                )
            ),
            commerce_progress=self._text(
                self._first_available(
                    self._first_value(conversation_state, "commerce_state"),
                    telegram_state.get("commerce_progress"),
                )
            ),
            current_position=self._text(
                self._first_available(
                    self._first_value(experience_progression, "current_story_position"),
                    self._first_value(experience_progression, "current_asset_position"),
                    progression_summary.get("current_story_position"),
                    progression_summary.get("current_asset_position"),
                )
            ),
            progress_percentage=int(
                self._first_available(
                    self._first_value(experience_progression, "progress_percentage"),
                    progression_summary.get("progress_percentage"),
                    0,
                )
                or 0
            ),
            completed_experience_ids=self._text_tuple(
                self._first_value(customer_summary, "completed_experience_ids")
            ),
            seen_experience_ids=self._text_tuple(
                self._first_value(customer_summary, "seen_experience_ids")
            ),
            metadata={
                "source": "customer_intelligence",
                "telegram_compatibility": conversation_state is not None
                or experience_progression is not None
                or bool(telegram_state),
            },
        )

    def _load_summary(
        self,
        customer_id: str | int | None,
        **lookup: Any,
    ) -> Mapping[str, Any] | None:
        if self.customer_service is None:
            return None
        return self.customer_service.get_customer_summary(customer_id, **lookup)

    def _load_commerce_summary(
        self,
        customer_id: str | int | None,
        **lookup: Any,
    ) -> Mapping[str, Any] | None:
        if self.customer_service is None:
            return None
        return self.customer_service.get_customer_commerce_summary(
            customer_id,
            **lookup,
        )

    def _snapshot_context(
        self,
        snapshot: CustomerIntelligenceSnapshot,
    ) -> dict[str, Any]:
        return {
            "identity": self._identity_context(snapshot.identity),
            "profile": self._profile_context(snapshot.profile),
            "relationship_stage": snapshot.relationship_stage.value,
            "relationship_intelligence": self.summarize_relationship(
                snapshot.relationship_intelligence
            ),
            "commerce_memory": self._commerce_memory_context(
                snapshot.commerce_memory
            ),
            "commerce_history": self.summarize_commerce_history(
                snapshot.commerce_memory
            ),
            "experience_progress": self._experience_progress_context(
                snapshot.experience_progress
            ),
            "last_interaction_metadata": dict(snapshot.last_interaction_metadata),
        }

    @staticmethod
    def _identity_context(identity: CustomerIdentity) -> dict[str, Any]:
        return {
            "canonical_customer_id": identity.canonical_customer_id,
            "customer_id": identity.customer_id,
            "provider": identity.provider,
            "provider_customer_id": identity.provider_customer_id,
            "provider_account_id": identity.provider_account_id,
            "telegram_identifier": identity.telegram_identifier,
            "platform_identifiers": dict(identity.platform_identifiers),
            "provider_identities": {
                key: dict(value)
                for key, value in dict(identity.provider_identities).items()
            },
            "future_provider_identifiers": dict(
                identity.future_provider_identifiers
            ),
            "metadata": dict(identity.metadata),
        }

    @staticmethod
    def _profile_context(profile: CustomerProfile) -> dict[str, Any]:
        return {
            "display_name": profile.display_name,
            "username": profile.username,
            "preferred_name": profile.preferred_name,
            "timezone": profile.timezone,
            "language": profile.language,
            "interests": profile.interests,
            "preferences": dict(profile.preferences),
            "creator_notes": profile.creator_notes,
            "tags": profile.tags,
            "customer_segments": profile.customer_segments,
            "metadata": dict(profile.metadata),
        }

    @staticmethod
    def _commerce_memory_context(memory: CustomerCommerceMemory) -> dict[str, Any]:
        return {
            "products_offered": memory.products_offered,
            "products_purchased": memory.products_purchased,
            "free_assets_delivered": memory.free_assets_delivered,
            "paid_products_delivered": memory.paid_products_delivered,
            "delivered_free_products": memory.delivered_free_products,
            "delivered_paid_products": memory.delivered_paid_products,
            "purchased_bundles": memory.purchased_bundles,
            "purchased_photoshoots": memory.purchased_photoshoots,
            "purchased_stories": memory.purchased_stories,
            "completed_experience_ids": memory.completed_experience_ids,
            "previous_offers": memory.previous_offers,
            "previous_purchases": memory.previous_purchases,
            "declined_offers": memory.declined_offers,
            "offer_outcomes": dict(memory.offer_outcomes),
            "offer_timestamps": dict(memory.offer_timestamps),
            "purchase_timestamps": dict(memory.purchase_timestamps),
            "delivery_timestamps": dict(memory.delivery_timestamps),
            "offer_events": tuple(dict(event) for event in memory.offer_events),
            "purchase_events": tuple(
                dict(event) for event in memory.purchase_events
            ),
            "delivery_events": tuple(
                dict(event) for event in memory.delivery_events
            ),
            "completed_experience_events": tuple(
                dict(event) for event in memory.completed_experience_events
            ),
            "duplicate_prevention_signals": memory.duplicate_prevention_signals,
            "last_purchase": dict(memory.last_purchase),
            "last_delivery": dict(memory.last_delivery),
            "customer_spending_summary": dict(memory.customer_spending_summary),
            "customer_engagement_summary": dict(memory.customer_engagement_summary),
            "commerce_metadata": dict(memory.commerce_metadata),
            "metadata": dict(memory.metadata),
        }

    @staticmethod
    def _experience_progress_context(
        progress: CustomerExperienceProgress,
    ) -> dict[str, Any]:
        return {
            "current_experience_id": progress.current_experience_id,
            "current_product_id": progress.current_product_id,
            "current_asset_id": progress.current_asset_id,
            "conversation_progress": progress.conversation_progress,
            "commerce_progress": progress.commerce_progress,
            "current_position": progress.current_position,
            "progress_percentage": progress.progress_percentage,
            "completed_experience_ids": progress.completed_experience_ids,
            "seen_experience_ids": progress.seen_experience_ids,
            "metadata": dict(progress.metadata),
        }

    @classmethod
    def _count_values(cls, values: Any) -> dict[str, int]:
        counts: dict[str, int] = {}
        for value in values:
            text = cls._text(value)
            if text is None:
                continue
            counts[text] = counts.get(text, 0) + 1
        return counts

    @staticmethod
    def _recommendation_rationale(
        *,
        relationship: Mapping[str, Any],
        commerce_history: Mapping[str, Any],
        activity_summary: Mapping[str, Any],
    ) -> tuple[str, ...]:
        rationale = []
        stage = relationship.get("stage")
        if stage:
            rationale.append(f"Relationship stage: {stage}")
        maturity = relationship.get("commerce_maturity")
        if maturity:
            rationale.append(f"Commerce maturity: {maturity}")
        engagement = relationship.get("engagement_level")
        if engagement:
            rationale.append(f"Engagement level: {engagement}")
        purchase_count = commerce_history.get("purchase_count")
        if purchase_count:
            rationale.append(f"Purchase count: {purchase_count}")
        if activity_summary.get("current_experience_id"):
            rationale.append("Customer has active experience progress")
        return tuple(rationale)

    @classmethod
    def _first_value(cls, source: Any, *names: str) -> Any | None:
        if source is None:
            return None
        if len(names) > 1:
            current = source
            for name in names:
                current = cls._first_value(current, name)
                if current is None:
                    return None
            return current
        name = names[0] if names else None
        if name is None:
            return None
        if isinstance(source, Mapping):
            return source.get(name)
        return getattr(source, name, None)

    @staticmethod
    def _first_available(*values: Any) -> Any | None:
        for value in values:
            if value is not None:
                return value
        return None

    @staticmethod
    def _safe_mapping(value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, Mapping) else {}

    @staticmethod
    def _int(value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _mapping_or_empty(value: Any) -> Mapping[str, Any]:
        return value if isinstance(value, Mapping) else {}

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    @classmethod
    def _text_tuple(cls, value: Any) -> tuple[str, ...]:
        if value is None:
            return ()
        if isinstance(value, (str, bytes)):
            values = (value,)
        elif isinstance(value, Mapping):
            values = value.values()
        else:
            try:
                values = tuple(value)
            except TypeError:
                values = (value,)
        return tuple(
            dict.fromkeys(
                text for item in values if (text := cls._text(item)) is not None
            )
        )

    @classmethod
    def _merge_text_tuples(cls, *values: Any) -> tuple[str, ...]:
        merged: list[str] = []
        for value in values:
            for item in cls._text_tuple(value):
                if item not in merged:
                    merged.append(item)
        return tuple(merged)

    @staticmethod
    def _mapping_tuple(value: Any) -> tuple[Mapping[str, Any], ...]:
        if value is None:
            return ()
        if isinstance(value, Mapping):
            values = (value,)
        else:
            try:
                values = tuple(value)
            except TypeError:
                values = (value,)
        return tuple(dict(item) for item in values if isinstance(item, Mapping))

    @classmethod
    def _text_mapping(cls, value: Any) -> dict[str, str]:
        if not isinstance(value, Mapping):
            return {}
        normalized: dict[str, str] = {}
        for key, item in value.items():
            text_key = cls._text(key)
            text_value = cls._text(item)
            if text_key is not None and text_value is not None:
                normalized[text_key] = text_value
        return normalized

    @classmethod
    def _commerce_event(cls, **values: Any) -> dict[str, Any]:
        event = {}
        for key, value in values.items():
            if key == "metadata":
                metadata = cls._safe_mapping(value)
                if metadata:
                    event[key] = metadata
            elif value is not None:
                event[key] = value
        return event

    @classmethod
    def _duplicate_signal(cls, event_type: str, event_id: Any) -> str:
        return f"{event_type}:{cls._text(event_id) or 'unknown'}"

    @classmethod
    def _normalize_product_type(cls, value: Any) -> str | None:
        text = cls._normalize_provider(value)
        aliases = {
            "bundles": "bundle",
            "photo": "photoshoot",
            "photoshoots": "photoshoot",
            "stories": "story",
        }
        return aliases.get(text, text)

    @classmethod
    def _normalize_delivery_type(cls, value: Any) -> str:
        text = cls._normalize_provider(value)
        if text in {"paid", "premium", "paid_product", "paid_media"}:
            return "paid"
        return "free"

    @classmethod
    def _is_dormant(
        cls,
        last_interaction_metadata: Mapping[str, Any] | None,
        customer_summary: Mapping[str, Any] | None,
    ) -> bool:
        days = cls._first_available(
            cls._first_value(last_interaction_metadata, "days_since_last_interaction"),
            cls._first_value(customer_summary, "days_since_last_interaction"),
        )
        if cls._int(days) >= 30:
            return True
        status = cls._normalize_provider(
            cls._first_available(
                cls._first_value(last_interaction_metadata, "relationship_status"),
                cls._first_value(customer_summary, "relationship_status"),
                cls._first_value(customer_summary, "status"),
            )
        )
        return status == "dormant"

    @staticmethod
    def _normalize_provider(value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip().lower()
        return text or None
