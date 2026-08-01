"""Canonical Customer Intelligence boundary for Creator OS.

CustomerIntelligenceService owns provider-neutral customer business memory read
models. It does not call provider APIs, execute commerce, make DecisionEngine
decisions, or migrate existing Telegram Commerce memory yet.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from datetime import datetime, timezone
import re
from typing import Any

from app.models.business_learning import LearningContext
from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CanonicalCustomerIntelligenceProfile,
    CustomerEvidenceReference,
    CustomerExperienceProgress,
    CustomerIdentity,
    CustomerIntelligenceReview,
    CustomerIntelligenceReviewSummary,
    CustomerIntelligenceSnapshot,
    CustomerIntelligenceMetric,
    CustomerIntelligencePreference,
    CustomerIntelligenceState,
    CustomerProfile,
    CustomerRelationshipIntelligence,
    CustomerRelationshipStage,
    CustomerSignalQuality,
    deep_freeze,
)


class CustomerIntelligenceCompatibilityAdapter:
    """Deprecated customer-memory compatibility boundary.

    This adapter retains historical profile mutation, relationship scoring, and
    recommendation behavior for migrated production callers. It is owned by
    the legacy Customer Business compatibility surface and is not canonical
    Customer Intelligence. New production consumers must use
    :class:`CustomerIntelligenceService`.
    """

    DEPRECATED_COMPATIBILITY_BOUNDARY = True
    OWNING_AUTHORITY = "CustomerBusinessService legacy customer-memory compatibility"
    RETAINED_DECISION_METHODS = {
        "recommend_relationship_focus": "legacy relationship guidance",
        "infer_relationship_stage": "legacy relationship classification",
        "calculate_engagement": "legacy customer-memory engagement score",
        "determine_commerce_maturity": "legacy commerce maturity classification",
        "update_relationship": "legacy relationship read-model composition",
        "update_preferences": "legacy customer-memory preference update",
    }
    CANONICAL_SOURCE_DEPENDENCIES = {
        "identity": ("identity",),
        "spending": ("transactions",),
        "purchase_history": ("transactions", "purchase_intents", "entitlements"),
        "ownership": ("ownership",),
        "entitlements": ("entitlements",),
        "sessions": ("sessions",),
        "media": ("purchase_intents", "conversations", "lineage"),
        "bundles": ("purchase_intents", "entitlements", "ownership"),
        "video": ("purchase_intents", "lineage"),
        "engagement": ("conversations",),
        "recommendations": ("recommendations", "purchase_intents"),
        "classifications": ("classifications",),
        "commercial_roles": ("roles",),
        "asset_lineage": ("lineage",),
        "publications": ("publications",),
        "fulfillment": ("fulfillment",),
        "delivery": ("delivery",),
        "provenance": ("provenance",),
    }

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
                "owner": "CustomerIntelligenceCompatibilityAdapter",
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
            "owner": "CustomerIntelligenceCompatibilityAdapter",
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
            "owner": "CustomerIntelligenceCompatibilityAdapter",
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
            "owner": "CustomerIntelligenceCompatibilityAdapter",
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
                "enriched_by": "CustomerIntelligenceCompatibilityAdapter",
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
                "owner": "CustomerIntelligenceCompatibilityAdapter",
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
                "owner": "CustomerIntelligenceCompatibilityAdapter",
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

    def build_canonical_profile(
        self, *, customer_context: Mapping[str, Any], transactions=(),
        purchase_intents=(), entitlements=(), ownership=None, sessions=(),
        messages=(), recommendations=(), commercial_roles=(), lineage=(),
        publications=(), fulfillments=(), deliveries=(), classifications=(),
        source_failures: Mapping[str, str] | None = None,
    ) -> CanonicalCustomerIntelligenceProfile:
        """Compose one immutable, query-time evidence profile.

        Inputs are canonical read projections. This method never loads, writes,
        recommends, authorizes, or mutates source state.
        """
        now = datetime.now(timezone.utc).isoformat()
        context = dict(customer_context or {})
        creator_id = self._int(context.get("creator_profile_id"))
        account_id = self._int(context.get("fanvue_account_id"))
        customer_id = self._text(
            context.get("canonical_customer_id") or context.get("customer_id")
        )
        external_uuid = self._text(context.get("external_fanvue_user_uuid"))
        identity_path = self._text(context.get("identity_path")) or "unresolved"
        identity_conflicts = tuple(context.get("identity_conflicts") or ()) + tuple(context.get("telegram_mapping_conflicts") or ()) + tuple(context.get("core_user_conflicts") or ())
        conflicts = list(identity_conflicts)
        insufficiencies = []
        identity_insufficiencies = []
        if not creator_id: insufficiencies.append("CREATOR_SCOPE_REQUIRED")
        if not account_id: insufficiencies.append("ACCOUNT_SCOPE_REQUIRED")
        if not customer_id and not external_uuid:
            insufficiencies.append("CUSTOMER_IDENTITY_UNRESOLVED")
        supported_identity_paths = {
            "fanvue_account:legacy_user", "fanvue_account:external_uuid",
            "telegram_mapping:core_user", "core_user:fanvue_mapping",
        }
        if identity_path not in supported_identity_paths:
            identity_insufficiencies.append(f"UNSUPPORTED_IDENTITY_PATH:{identity_path}")
        identity_authorities = self._plain_mapping(context.get("identity_authorities"))
        telegram_identifier = context.get("telegram_user_id") or context.get("telegram_identifier")
        if telegram_identifier and not (
            context.get("telegram_mapping_source") or identity_authorities.get("telegram_user_id")
        ):
            identity_insufficiencies.append("TELEGRAM_MAPPING_UNVERIFIED")
        if context.get("core_user_id") and not (
            context.get("core_user_source") or identity_authorities.get("core_user_id")
        ):
            identity_insufficiencies.append("CORE_USER_ID_SOURCE_REQUIRED")
        if identity_path == "fanvue_account:external_uuid" and not external_uuid:
            identity_insufficiencies.append("EXTERNAL_FANVUE_UUID_REQUIRED_FOR_IDENTITY_PATH")
        if identity_path == "telegram_mapping:core_user" and not telegram_identifier:
            identity_insufficiencies.append("TELEGRAM_IDENTITY_REQUIRED_FOR_IDENTITY_PATH")
        if identity_path == "core_user:fanvue_mapping" and not context.get("core_user_id"):
            identity_insufficiencies.append("CORE_USER_ID_REQUIRED_FOR_IDENTITY_PATH")
        context["identity_provenance"] = {
            "creator_profile_id": identity_authorities.get("creator_profile_id") or context.get("creator_profile_source") or "CreatorProfileRepository",
            "fanvue_account_id": identity_authorities.get("fanvue_account_id") or context.get("fanvue_account_source") or "FanvueAccountAuthority",
            "canonical_customer_id": identity_authorities.get("canonical_customer_id") or ("LegacyFanvueCustomerMapping" if identity_path == "fanvue_account:legacy_user" else "CanonicalIdentityMapping"),
            "external_fanvue_user_uuid": identity_authorities.get("external_fanvue_user_uuid") or ("FanvueCustomerAuthority" if external_uuid else None),
            "telegram_user_id": identity_authorities.get("telegram_user_id") or context.get("telegram_mapping_source"),
            "core_user_id": identity_authorities.get("core_user_id") or context.get("core_user_source"),
            "identity_path": identity_path,
        }
        insufficiencies.extend(identity_insufficiencies)
        confidence = 1.0 if creator_id and account_id and customer_id and external_uuid else .8 if creator_id and account_id and (customer_id or external_uuid) else 0.0
        if identity_conflicts: confidence = min(confidence, .25)

        failures = self._normalize_source_failures(source_failures)
        raw_sources = {
            "transactions": tuple(transactions or ()),
            "purchase_intents": tuple(purchase_intents or ()),
            "entitlements": tuple(entitlements or ()),
            "ownership": ((ownership,) if ownership else ()),
            "sessions": tuple(sessions or ()),
            "conversations": tuple(messages or ()),
            "recommendations": tuple(recommendations or ()),
            "roles": tuple(commercial_roles or ()),
            "lineage": tuple(lineage or ()),
            "publications": tuple(publications or ()),
            "fulfillment": tuple(fulfillments or ()),
            "delivery": tuple(deliveries or ()),
            "classifications": tuple(classifications or ()),
        }
        valid_sources = {
            name: (() if name in failures else values)
            for name, values in raw_sources.items()
        }
        excluded_source_counts = {
            name: len(raw_sources[name]) for name in failures if name in raw_sources
        }
        transactions = valid_sources["transactions"]
        purchase_intents = valid_sources["purchase_intents"]
        entitlements = valid_sources["entitlements"]
        ownership = valid_sources["ownership"][0] if valid_sources["ownership"] else None
        sessions = valid_sources["sessions"]
        messages = valid_sources["conversations"]
        recommendations = valid_sources["recommendations"]
        commercial_roles = valid_sources["roles"]
        lineage = valid_sources["lineage"]
        publications = valid_sources["publications"]
        fulfillments = valid_sources["fulfillment"]
        deliveries = valid_sources["delivery"]
        classifications = valid_sources["classifications"]

        sources = {
            "Customer Commerce Transactions": tuple(transactions or ()),
            "Purchase Intents": tuple(purchase_intents or ()),
            "Customer Entitlements": tuple(entitlements or ()),
            "Ownership Intelligence": ((ownership,) if ownership else ()),
            "Sales Sessions": tuple(sessions or ()),
            "Conversation History": tuple(messages or ()),
            "Recommendation and Outcome History": tuple(recommendations or ()),
            "Commercial Roles": tuple(commercial_roles or ()),
            "Asset Lineage": tuple(lineage or ()),
            "Publication": tuple(publications or ()),
            "Fulfillment": tuple(fulfillments or ()),
            "Delivery": tuple(deliveries or ()),
        }
        facts = tuple(
            self._canonical_fact(authority, item, creator_id, identity_path)
            for authority, items in sources.items() for item in items
        )
        dependencies = self.CANONICAL_SOURCE_DEPENDENCIES
        evidence_by_section = {
            "identity": context if "identity" not in failures and creator_id and account_id and (customer_id or external_uuid) else (),
            "spending": transactions,
            "purchase_history": tuple(transactions or ()) + tuple(purchase_intents or ()) + tuple(entitlements or ()),
            "ownership": ownership,
            "entitlements": entitlements,
            "sessions": sessions,
            "media": tuple(purchase_intents or ()) + tuple(messages or ()) + tuple(lineage or ()),
            "bundles": tuple(purchase_intents or ()) + tuple(entitlements or ()),
            "video": tuple(purchase_intents or ()) + tuple(lineage or ()),
            "engagement": messages,
            "recommendations": recommendations,
            "classifications": classifications,
            "commercial_roles": commercial_roles,
            "asset_lineage": lineage,
            "publications": publications,
            "fulfillment": fulfillments,
            "delivery": deliveries,
            "provenance": facts,
        }
        partial_sections = {
            "purchase_history": not bool(transactions and purchase_intents),
            "media": not bool(lineage and (purchase_intents or messages)),
            "bundles": True,
            "video": not bool(lineage and purchase_intents),
            "recommendations": True,
            "classifications": bool(classifications),
            "provenance": bool(failures),
        }
        section_states = {}
        section_state_reasons = {}
        for section, evidence in evidence_by_section.items():
            failed = tuple(key for key in dependencies[section] if key in failures)
            evidence_conflicts = self._evidence_conflicts(evidence)
            if section == "identity" and identity_conflicts:
                evidence_conflicts = identity_conflicts
            remaining_count = 1 if isinstance(evidence, Mapping) and evidence else len(tuple(evidence or ()))
            excluded_count = sum(excluded_source_counts.get(key, 0) for key in failed)
            failure_reasons = tuple(f"SOURCE_UNAVAILABLE:{key}:{failures[key]}" for key in failed) + (
                (f"EXCLUDED_EVIDENCE_COUNT:{excluded_count}",
                 f"AFFECTED_INTERPRETATION:{section}",
                 f"REMAINING_VALID_EVIDENCE_COUNT:{remaining_count}") if failed else ()
            )
            if evidence_conflicts:
                state = CustomerIntelligenceState.CONFLICTING
                reasons = tuple(f"CONFLICT:{value}" for value in evidence_conflicts) + failure_reasons
            elif failed:
                state = CustomerIntelligenceState.PARTIAL if evidence else CustomerIntelligenceState.UNAVAILABLE
                reasons = failure_reasons
            elif not evidence:
                state = CustomerIntelligenceState.INSUFFICIENT
                reasons = (f"EVIDENCE_REQUIRED:{section}",)
            elif self._evidence_incomplete(evidence) or (
                partial_sections.get(section, False) and not self._evidence_complete(evidence)
            ):
                state = CustomerIntelligenceState.PARTIAL
                reasons = (f"INCOMPLETE_EVIDENCE:{section}",)
            else:
                state = CustomerIntelligenceState.SUFFICIENT
                reasons = ("EVIDENCE_COMPLETE",)
            section_states[section] = state
            section_state_reasons[section] = reasons
        if identity_insufficiencies and section_states["identity"] != CustomerIntelligenceState.CONFLICTING:
            section_states["identity"] = CustomerIntelligenceState.INSUFFICIENT
            section_state_reasons["identity"] = tuple(identity_insufficiencies)
        conflicts.extend(
            reason.removeprefix("CONFLICT:")
            for section, state in section_states.items()
            if state == CustomerIntelligenceState.CONFLICTING
            for reason in section_state_reasons[section]
        )
        purchase_history = self._unified_purchase_history(
            transactions, purchase_intents, entitlements, sessions,
            publications, fulfillments, deliveries,
        )
        spending = self._spending_metrics(transactions, now)
        session_profile = self._session_metrics(sessions, purchase_intents, now)
        engagement = self._engagement_metrics(messages, now)
        purchase_preferences, media_preferences = self._preferences(
            purchase_intents, entitlements, messages, now,
        )
        provenance_context = {
            "creator_profile_id": creator_id,
            "customer_identity_path": identity_path,
            "calculated_at": now,
        }
        spending = {
            key: replace(metric, provenance=self._output_provenance(
                source_authority="Customer Commerce Transactions",
                source_ids=metric.included_records,
                included=metric.included_records,
                excluded=metric.excluded_records,
                method=metric.calculation_method,
                confidence=metric.confidence,
                conflicts=metric.conflicts,
                insufficiencies=metric.insufficiencies,
                excluded_record_reasons=tuple("MISSING_CURRENCY" for _ in metric.excluded_records),
                lifecycle_filters=metric.lifecycle_filters,
                **provenance_context,
            )) for key, metric in spending.items()
        }
        purchase_preferences = tuple(self._preference_with_provenance(item, provenance_context) for item in purchase_preferences)
        media_preferences = tuple(self._preference_with_provenance(item, provenance_context) for item in media_preferences)
        bundle = self._bundle_metrics(purchase_history, now)
        video = self._video_metrics(purchase_intents, lineage, now)
        recommendation = self._recommendation_metrics(recommendations, now)
        if "purchase_intents" in failures and recommendations:
            recommendation = {
                **recommendation,
                "recommendation_conversion": None,
                "insufficiencies": tuple(recommendation.get("insufficiencies") or ())
                + ("PURCHASE_INTENT_SOURCE_UNAVAILABLE_FOR_CONVERSION",),
            }
        session_profile = self._metric_group_provenance(session_profile, sessions, "Sales Sessions", provenance_context, section_states["sessions"])
        engagement = self._metric_group_provenance(engagement, messages, "Conversation History", provenance_context, section_states["engagement"])
        bundle = self._metric_group_provenance(bundle, purchase_intents or entitlements, "Purchase Intents and Entitlements", provenance_context, section_states["bundles"])
        video = self._metric_group_provenance(video, purchase_intents or lineage, "Purchase Intents and Asset Lineage", provenance_context, section_states["video"])
        recommendation = self._metric_group_provenance(recommendation, recommendations, "Historical Recommendation and Outcome Evidence", provenance_context, section_states["recommendations"])
        if section_states["spending"] == CustomerIntelligenceState.UNAVAILABLE:
            spending = {"unavailable": CustomerIntelligenceMetric(
                "spending", None, "unknown", CustomerIntelligenceState.UNAVAILABLE,
                "source unavailable", now,
                insufficiencies=section_state_reasons["spending"],
                provenance=self._output_provenance(
                    source_authority="Customer Commerce Transactions", source_ids=(),
                    included=(), excluded=(), method="source unavailable",
                    confidence=0.0, insufficiencies=section_state_reasons["spending"],
                    **provenance_context,
                ),
            )}
        ownership_map = self._plain_mapping(ownership)
        ownership_conflicts = tuple(ownership_map.get("conflicts") or ())
        conflicts.extend(str(item) for item in ownership_conflicts)
        ownership_insufficient = tuple(ownership_map.get("insufficiencies") or ())
        insufficiencies.extend(str(item) for item in ownership_insufficient)
        identity_allows_interpretation = section_states["identity"] == CustomerIntelligenceState.SUFFICIENT
        interests = tuple(self._interpretation(item, "INTEREST", now, provenance_context) for item in purchase_preferences + media_preferences if identity_allows_interpretation and item.direction == "positive" and item.confidence >= .5)
        aversions = tuple(self._interpretation(item, "AVERSION", now, provenance_context) for item in purchase_preferences + media_preferences if identity_allows_interpretation and item.direction == "negative" and item.exposure_count >= 2 and item.confidence >= .6)
        opportunities = self._opportunities(bundle, video, session_profile, purchase_preferences, now, purchase_intents, purchase_history) if identity_allows_interpretation else ()
        risks = self._risks(session_profile, recommendation, context, now, sessions) if identity_allows_interpretation else ()
        opportunities = tuple(self._attach_mapping_provenance(item, provenance_context, "Customer Intelligence deterministic opportunity evidence") for item in opportunities)
        risks = tuple(self._attach_mapping_provenance(item, provenance_context, "Customer Intelligence deterministic risk evidence") for item in risks)
        classification_values = tuple(self._classification(item, provenance_context) for item in classifications)
        if failures: insufficiencies.extend(f"SOURCE_UNAVAILABLE:{key}:{value}" for key, value in failures.items())
        if section_states["identity"] in {CustomerIntelligenceState.INSUFFICIENT, CustomerIntelligenceState.UNAVAILABLE}:
            profile_state = CustomerIntelligenceState.INSUFFICIENT
        elif any(value == CustomerIntelligenceState.CONFLICTING for value in section_states.values()):
            profile_state = CustomerIntelligenceState.CONFLICTING
        elif any(value != CustomerIntelligenceState.SUFFICIENT for value in section_states.values()):
            profile_state = CustomerIntelligenceState.PARTIAL
        else:
            profile_state = CustomerIntelligenceState.SUFFICIENT
        provenance = {
            "authorities": {key: len(value) for key, value in sources.items()},
            "source_failures": failures, "creator_profile_id": creator_id,
            "customer_identity_path": identity_path,
            "included_evidence_count": len(facts),
            "excluded_source_evidence_counts": excluded_source_counts,
            "excluded_evidence_count": sum(excluded_source_counts.values()),
            "calculated_at": now,
        }
        commercial_summary = {
            "purchase_count": len([item for item in purchase_history if item.get("purchase_state") == "PURCHASED"]) if section_states["purchase_history"] not in {CustomerIntelligenceState.UNAVAILABLE, CustomerIntelligenceState.INSUFFICIENT} else None,
            "session_count": len(sessions) if section_states["sessions"] not in {CustomerIntelligenceState.UNAVAILABLE, CustomerIntelligenceState.INSUFFICIENT} else None,
            "recommendation_count": len(recommendations) if section_states["recommendations"] not in {CustomerIntelligenceState.UNAVAILABLE, CustomerIntelligenceState.INSUFFICIENT} else None,
            "owned_asset_count": len(ownership_map.get("owned_asset_ids") or ()) if section_states["ownership"] not in {CustomerIntelligenceState.UNAVAILABLE, CustomerIntelligenceState.INSUFFICIENT} else None,
            "owned_offering_count": len(ownership_map.get("owned_offering_ids") or ()) if section_states["ownership"] not in {CustomerIntelligenceState.UNAVAILABLE, CustomerIntelligenceState.INSUFFICIENT} else None,
        }
        return CanonicalCustomerIntelligenceProfile(
            profile_state=profile_state, customer_context=context,
            identity_confidence=confidence, facts=facts,
            commercial_summary=commercial_summary,
            unified_purchase_history=purchase_history, spending_profile=spending,
            ownership_summary=ownership_map, session_profile=session_profile,
            purchase_preferences=purchase_preferences,
            media_preferences=media_preferences, bundle_behavior=bundle,
            video_conversion=video, engagement_profile=engagement,
            recommendation_history=recommendation, interests=interests,
            aversions=aversions, opportunities=opportunities, risks=risks,
            classifications=classification_values, section_states=section_states,
            section_state_reasons=section_state_reasons,
            conflicts=tuple(dict.fromkeys(conflicts)),
            insufficiencies=tuple(dict.fromkeys(insufficiencies)),
            provenance=provenance,
            calculation_metadata={"method_version": "customer-intelligence-v1", "calculated_at": now, "query_time": True, "prediction_outputs": False, "commercial_decisions": False},
        )

    def project_canonical_profile(
        self, profile: CanonicalCustomerIntelligenceProfile, consumer: str,
    ) -> Mapping[str, Any]:
        """Return a purpose-limited view without recomputing profile truth."""
        common = {"profile_state": profile.profile_state.value, "customer_context": profile.customer_context, "identity_confidence": profile.identity_confidence, "section_states": profile.section_states, "section_state_reasons": profile.section_state_reasons, "conflicts": profile.conflicts, "insufficiencies": profile.insufficiencies, "provenance": profile.provenance, "calculation_metadata": profile.calculation_metadata}
        views = {
            "commercial_intelligence": {"spending_profile": profile.spending_profile, "purchase_preferences": profile.purchase_preferences, "media_preferences": profile.media_preferences, "bundle_behavior": profile.bundle_behavior, "session_profile": profile.session_profile, "engagement_profile": profile.engagement_profile, "interests": profile.interests, "aversions": profile.aversions, "opportunities": profile.opportunities, "risks": profile.risks},
            "offering_selector": {"purchase_preferences": profile.purchase_preferences, "media_preferences": profile.media_preferences, "bundle_behavior": profile.bundle_behavior, "purchase_history": profile.unified_purchase_history, "aversions": profile.aversions},
            "customer_sales_brain": {"spending_profile": profile.spending_profile, "session_profile": profile.session_profile, "engagement_profile": profile.engagement_profile, "recommendation_history": profile.recommendation_history, "opportunities": profile.opportunities, "risks": profile.risks},
            "product_recommendation": {"purchase_history": profile.unified_purchase_history, "media_preferences": profile.media_preferences, "ownership_summary": profile.ownership_summary, "recommendation_history": profile.recommendation_history},
            "sales_sessions": {"session_profile": profile.session_profile, "bundle_behavior": profile.bundle_behavior, "ownership_summary": profile.ownership_summary},
            "conversation": {"commercial_summary": profile.commercial_summary, "interests": profile.interests, "aversions": profile.aversions, "profile_state": profile.profile_state.value},
            "customer_workspace": self._profile_payload(profile),
            "commercial_administration": self._profile_payload(profile),
        }
        key = str(consumer).strip().lower()
        if key not in views: raise ValueError("Unsupported Customer Intelligence consumer projection.")
        return deep_freeze({**common, **views[key], "consumer_projection": key})

    def _canonical_fact(self, authority, item, creator_id, identity_path):
        record_id = self._text(self._read_value(item, "record_id") or self._read_value(item, "id") or self._read_value(item, "purchase_intent_id") or self._read_value(item, "purchaseIntentId") or self._read_value(item, "sales_session_id") or self._read_value(item, "salesSessionId") or self._read_value(item, "transaction_order_id") or self._read_value(item, "entitlement_id") or self._read_value(item, "entitlementId") or self._read_value(item, "assignment_id") or self._read_value(item, "assignmentId") or self._read_value(item, "lineage_id") or self._read_value(item, "lineageId") or self._read_value(item, "publication_id") or self._read_value(item, "publicationId") or self._read_value(item, "fulfillment_id") or self._read_value(item, "fulfillmentId") or self._read_value(item, "delivery_id") or self._read_value(item, "deliveryId"))
        lifecycle = self._text(self._read_value(item, "status") or self._read_value(item, "state") or self._read_value(item, "lifecycle"))
        timestamp = self._text(self._read_value(item, "timestamp") or self._read_value(item, "created_at") or self._read_value(item, "createdAt") or self._read_value(item, "updated_at"))
        currency = self._text(self._read_value(item, "currency") or self._read_value(item, "expected_currency"))
        quality = CustomerSignalQuality.STRONG_COMMERCIAL if authority in {"Customer Commerce Transactions", "Purchase Intents", "Customer Entitlements"} else CustomerSignalQuality.STRONG_BEHAVIORAL if authority in {"Sales Sessions", "Conversation History"} else CustomerSignalQuality.SUPPORTING
        return CustomerEvidenceReference(authority, record_id, creator_id, identity_path, lifecycle, timestamp, currency, quality, {"referenced_only": True, "aggregate_evidence": record_id is None, "conflicts": tuple(self._read_value(item, "conflicts") or ()), "insufficiencies": tuple(self._read_value(item, "insufficiencies") or ())})

    def _unified_purchase_history(self, transactions, intents, entitlements, sessions, publications, fulfillments, deliveries):
        values = []
        for item in tuple(transactions or ()):
            transaction_id = self._text(self._read_value(item, "transaction_order_id") or self._read_value(item, "record_id"))
            matched = next((intent for intent in intents if transaction_id and transaction_id == self._text(self._read_value(intent, "provider_transaction_order_id"))), None)
            offering_id = self._text(self._read_value(matched, "commercial_offering_id") or self._read_value(matched, "commercialOfferingId")) if matched else None
            values.append({"transaction_reference": transaction_id, "purchase_intent_reference": self._text(self._read_value(matched, "purchase_intent_id") or self._read_value(matched, "purchaseIntentId")) if matched else None, "offering_reference": offering_id, "gross_minor": self._int(self._read_value(item, "gross_minor")), "net_minor": self._int(self._read_value(item, "net_minor")), "currency": self._text(self._read_value(item, "currency")), "purchase_state": "PURCHASED", "attribution_confidence": "HIGH" if matched else "UNKNOWN", "ambiguity": not bool(matched), "source_authority": "Customer Commerce Transactions"})
        known_transactions = {value.get("transaction_reference") for value in values}
        for intent in tuple(intents or ()):
            transaction_id = self._text(self._read_value(intent, "provider_transaction_order_id"))
            if transaction_id in known_transactions: continue
            status = self._text(self._read_value(intent, "status")) or "UNKNOWN"
            values.append({"transaction_reference": transaction_id, "purchase_intent_reference": self._text(self._read_value(intent, "purchase_intent_id") or self._read_value(intent, "purchaseIntentId")), "offering_reference": self._text(self._read_value(intent, "commercial_offering_id") or self._read_value(intent, "commercialOfferingId")), "gross_minor": None, "net_minor": None, "currency": self._text(self._read_value(intent, "expected_currency")), "purchase_state": status, "attribution_confidence": self._text(self._read_value(intent, "attribution_result")) or "UNKNOWN", "ambiguity": status == "PURCHASED" and not transaction_id, "expected_price_not_settled": self._int(self._read_value(intent, "expected_price_minor")), "source_authority": "Purchase Intents"})
        return tuple(values)

    def _spending_metrics(self, transactions, now):
        by_currency = {}
        excluded = []
        for item in tuple(transactions or ()):
            currency = self._text(self._read_value(item, "currency"))
            record = self._text(self._read_value(item, "transaction_order_id") or self._read_value(item, "record_id")) or "unidentified"
            if not currency: excluded.append(record); continue
            by_currency.setdefault(currency, []).append(item)
        metrics = {}
        for currency, items in by_currency.items():
            gross = sum(self._int(self._read_value(item, "gross_minor")) for item in items); net = sum(self._int(self._read_value(item, "net_minor")) for item in items); ids = tuple(self._text(self._read_value(item, "transaction_order_id")) or "unidentified" for item in items); count = len(items)
            base = dict(state=CustomerIntelligenceState.SUFFICIENT, calculated_at=now, currency=currency, included_records=ids, excluded_records=tuple(excluded), lifecycle_filters=("verified transaction",), confidence=1.0)
            metrics[f"{currency}:lifetime_gross"] = CustomerIntelligenceMetric("lifetime_gross", gross, "minor_currency_unit", calculation_method="sum(verified.gross_minor)", **base)
            metrics[f"{currency}:lifetime_net"] = CustomerIntelligenceMetric("lifetime_net", net, "minor_currency_unit", calculation_method="sum(verified.net_minor)", **base)
            metrics[f"{currency}:purchase_count"] = CustomerIntelligenceMetric("purchase_count", count, "transactions", calculation_method="count(verified transactions)", **base)
            metrics[f"{currency}:average_order"] = CustomerIntelligenceMetric("average_order", gross / count if count else None, "minor_currency_unit", numerator=gross, denominator=count, calculation_method="gross/count", **base)
            metrics[f"{currency}:largest_order"] = CustomerIntelligenceMetric("largest_order", max((self._int(self._read_value(item, "gross_minor")) for item in items), default=0), "minor_currency_unit", calculation_method="max(verified.gross_minor)", **base)
        if not metrics: metrics["unavailable"] = CustomerIntelligenceMetric("spending", None, "unknown", CustomerIntelligenceState.INSUFFICIENT, "verified transactions grouped by original currency", now, excluded_records=tuple(excluded), insufficiencies=("NO_CURRENCY_SAFE_VERIFIED_TRANSACTIONS",))
        return metrics

    def _session_metrics(self, sessions, intents, now):
        items = tuple(sessions or ()); states = [str(self._read_value(item, "state") or "UNKNOWN").upper() for item in items]; terminal = {name: states.count(name) for name in ("COMPLETED", "ABANDONED", "EXPIRED", "CANCELLED", "ACTIVE")}; durations = []
        for item in items:
            start = self._as_datetime(self._read_value(item, "started_at") or self._read_value(item, "startedAt")); end = self._as_datetime(self._read_value(item, "ended_at") or self._read_value(item, "endedAt"));
            if start and end: durations.append((end - start).total_seconds())
        denominator = len(items)
        return {"state": (CustomerIntelligenceState.SUFFICIENT if items else CustomerIntelligenceState.INSUFFICIENT).value, "lifecycle_counts": terminal if items else None, "completion_rate": terminal["COMPLETED"] / denominator if denominator else None, "abandonment_rate": terminal["ABANDONED"] / denominator if denominator else None, "expiration_rate": terminal["EXPIRED"] / denominator if denominator else None, "average_duration_seconds": sum(durations) / len(durations) if durations else None, "duration_evidence_count": len(durations) if items else None, "session_count": denominator if items else None, "progression_reached": tuple(dict.fromkeys(str(self._read_value(item, "progression_stage") or self._read_value(item, "progressionStage") or "UNKNOWN") for item in items)), "terminal_reasons": tuple(self._text(self._read_value(item, "terminal_reason") or self._read_value(item, "terminalReason")) for item in items if self._read_value(item, "terminal_reason") or self._read_value(item, "terminalReason")), "calculated_at": now, "insufficiencies": (("SESSION_EVIDENCE_REQUIRED",) if not items else () if len(durations) == len([item for item in items if str(self._read_value(item, "state") or "").upper() != "ACTIVE"]) else ("SESSION_DURATION_TIMESTAMPS_INCOMPLETE",))}

    def _engagement_metrics(self, messages, now):
        items = tuple(messages or ()); inbound = [item for item in items if str(self._read_value(item, "direction") or "").lower() == "inbound"]; outbound = [item for item in items if str(self._read_value(item, "direction") or "").lower() == "outbound"]; timestamps = [value for item in items if (value := self._as_datetime(self._read_value(item, "sent_at") or self._read_value(item, "timestamp")))]; latencies = []
        ordered = sorted(((self._as_datetime(self._read_value(item, "sent_at") or self._read_value(item, "timestamp")), item) for item in items), key=lambda value: value[0] or datetime.min.replace(tzinfo=timezone.utc))
        for index, (stamp, item) in enumerate(ordered[:-1]):
            next_stamp, next_item = ordered[index + 1]
            if stamp and next_stamp and str(self._read_value(item, "direction") or "").lower() == "inbound" and str(self._read_value(next_item, "direction") or "").lower() == "outbound": latencies.append((next_stamp - stamp).total_seconds())
        return {"state": (CustomerIntelligenceState.SUFFICIENT if items else CustomerIntelligenceState.INSUFFICIENT).value, "inbound_count": len(inbound) if items else None, "outbound_count": len(outbound) if items else None, "message_count": len(items) if items else None, "first_message_at": min(timestamps).isoformat() if timestamps else None, "last_message_at": max(timestamps).isoformat() if timestamps else None, "average_response_latency_seconds": sum(latencies) / len(latencies) if latencies else None, "response_latency_observations": len(latencies) if items else None, "explicit_requests": tuple(self._text(self._read_value(item, "requested_media_type") or self._read_value(item, "requested_theme")) for item in items if self._read_value(item, "requested_media_type") or self._read_value(item, "requested_theme")), "calculated_at": now, "insufficiencies": (() if latencies else ("RESPONSE_PAIRS_UNAVAILABLE",))}

    def _preferences(self, intents, entitlements, messages, now):
        evidence = {}
        def bucket(dimension, subject):
            return evidence.setdefault((dimension, subject), {"positive": [], "negative": [], "supporting": [], "exposure": 0, "strong": 0, "timestamps": []})
        for item in tuple(intents or ()):
            status = str(self._read_value(item, "status") or "").upper(); attributed = str(self._read_value(item, "attribution_result") or "").upper() in {"ATTRIBUTED", "DIRECT"}; record = self._text(self._read_value(item, "purchase_intent_id") or self._read_value(item, "purchaseIntentId")) or "intent"; metadata = self._plain_mapping(self._read_value(item, "created_metadata") or self._read_value(item, "createdMetadata")); stamp = self._text(self._read_value(item, "updated_at") or self._read_value(item, "created_at") or self._read_value(item, "createdAt"))
            for dimension, keys in {"media_type": ("media_type", "mediaType"), "offering_type": ("offering_type", "offeringType"), "product_type": ("product_type", "productType"), "bundle_size": ("bundle_size", "bundleSize"), "commercial_role": ("commercial_role", "commercialRole"), "photoshoot": ("photoshoot_reference", "photoshootReference"), "progression": ("progression_stage", "progressionStage"), "lineage_family": ("lineage_family", "lineageFamily"), "theme": ("theme", "requested_theme")}.items():
                subject = next((self._text(metadata.get(key) or self._read_value(item, key)) for key in keys if metadata.get(key) or self._read_value(item, key)), None)
                if subject:
                    value = bucket(dimension, subject); value["exposure"] += 1
                    if stamp: value["timestamps"].append(stamp)
                    disqualified = bool(metadata.get("refunded") or metadata.get("revoked")) or str(metadata.get("lifecycle") or "").upper() in {"REFUNDED", "REVOKED"}
                    if status == "PURCHASED" and attributed and not disqualified:
                        value["positive"].append(record); value["strong"] += 1
                    elif disqualified or status in {"DECLINED", "REJECTED", "SUPPRESSED", "ABANDONED", "REFUNDED", "REVOKED"}:
                        value["negative"].append(record)
                    else:
                        value["supporting"].append(record)
        for item in tuple(entitlements or ()):
            lifecycle = str(self._read_value(item, "status") or self._read_value(item, "lifecycle") or "UNKNOWN").upper(); record = self._text(self._read_value(item, "entitlement_id") or self._read_value(item, "entitlementId")) or "entitlement"; metadata = self._plain_mapping(self._read_value(item, "metadata")); stamp = self._text(self._read_value(item, "updated_at") or self._read_value(item, "created_at"))
            for dimension, keys in {"offering_type": ("offering_type", "offeringType"), "product_type": ("product_type", "productType"), "media_type": ("media_type", "mediaType")}.items():
                subject = next((self._text(metadata.get(key) or self._read_value(item, key)) for key in keys if metadata.get(key) or self._read_value(item, key)), None)
                if subject:
                    value = bucket(dimension, subject)
                    if stamp: value["timestamps"].append(stamp)
                    if lifecycle in {"REVOKED", "REFUNDED", "EXPIRED"}: value["negative"].append(record)
                    else: value["supporting"].append(record)
        for item in tuple(messages or ()):
            subject = self._text(self._read_value(item, "requested_media_type")); record = self._text(self._read_value(item, "id") or self._read_value(item, "message_id")) or "message"; stamp = self._text(self._read_value(item, "sent_at") or self._read_value(item, "timestamp"))
            if subject:
                value = bucket("media_type", subject); value["positive"].append(record)
                if stamp: value["timestamps"].append(stamp)
        preferences = []
        for (dimension, subject), value in evidence.items():
            positive = tuple(value["positive"]); negative = tuple(value["negative"]); supporting = tuple(value["supporting"]); observations = len(positive) + len(negative) + len(supporting); conflict = bool(positive and negative); confidence = min(.95, .2 + .2 * value["strong"] + .1 * max(0, len(positive) - value["strong"]) + .2 * len(negative) + .05 * len(supporting)); quality = CustomerSignalQuality.AMBIGUOUS if conflict else CustomerSignalQuality.STRONG_COMMERCIAL if value["strong"] >= 2 else CustomerSignalQuality.SUPPORTING if positive or supporting or len(negative) >= 2 else CustomerSignalQuality.WEAK; direction = "ambiguous" if conflict else "positive" if positive else "negative" if negative else "ambiguous"; state = CustomerIntelligenceState.CONFLICTING if conflict else CustomerIntelligenceState.SUFFICIENT if value["strong"] >= 2 else CustomerIntelligenceState.PARTIAL; latest = max(value["timestamps"]) if value["timestamps"] else None
            preferences.append(CustomerIntelligencePreference(
                dimension=dimension, subject=subject, direction=direction,
                state=state, quality=quality, confidence=confidence,
                positive_evidence=positive, contradictory_evidence=negative,
                observation_count=observations, exposure_count=value["exposure"],
                latest_evidence_at=latest,
                derivation_method="weighted explicit purchase, request, and lifecycle evidence",
                conflicts=(("CONTRADICTORY_PREFERENCE_EVIDENCE",) if conflict else ()),
                insufficiencies=(() if value["strong"] >= 2 else ("SPARSE_PREFERENCE_EVIDENCE",)),
                supporting_evidence=supporting,
            ))
        values = tuple(preferences); return tuple(item for item in values if item.dimension != "media_type"), tuple(item for item in values if item.dimension == "media_type")

    def _bundle_metrics(self, history, now):
        purchases = [item for item in history if item.get("purchase_state") == "PURCHASED"]; bundles = [item for item in purchases if str(item.get("offering_type") or "").upper() in {"PHOTOSET", "STORY_SET", "MIXED_SET", "BUNDLE"}]
        return {"state": (CustomerIntelligenceState.PARTIAL if purchases else CustomerIntelligenceState.INSUFFICIENT).value, "bundle_purchase_count": len(bundles) if purchases else None, "single_item_purchase_count": len(purchases) - len(bundles) if purchases else None, "bundle_purchase_ratio": len(bundles) / len(purchases) if purchases else None, "calculated_at": now, "insufficiencies": ("OFFERING_COMPOSITION_REQUIRED_FOR_COMPLETE_BUNDLE_PROFILE",)}

    def _video_metrics(self, intents, lineage, now):
        presented = [item for item in intents if str(self._read_value(item, "media_type") or self._plain_mapping(self._read_value(item, "created_metadata")).get("media_type") or "").upper() == "VIDEO" and str(self._read_value(item, "status") or "").upper() in {"PRESENTED", "CLICKED", "PURCHASED"}]; purchased = [item for item in presented if str(self._read_value(item, "status") or "").upper() == "PURCHASED"]
        return {"state": (CustomerIntelligenceState.SUFFICIENT if presented else CustomerIntelligenceState.INSUFFICIENT).value, "videos_presented": len(presented) if presented else None, "videos_purchased": len(purchased) if presented else None, "conversion_rate": len(purchased) / len(presented) if presented else None, "numerator": len(purchased) if presented else None, "denominator": len(presented) if presented else None, "lineage_relationship_count": len(tuple(lineage or ())) if lineage else None, "calculated_at": now, "insufficiencies": (() if presented else ("VALID_VIDEO_EXPOSURE_DENOMINATOR_REQUIRED",))}

    def _recommendation_metrics(self, recommendations, now):
        items = tuple(recommendations or ()); states = [str(self._read_value(item, "state") or self._read_value(item, "event_state") or "UNKNOWN").upper() for item in items]; presented = sum(value in {"PRESENTED", "OFFERED"} for value in states); purchased = states.count("PURCHASED")
        return {"state": (CustomerIntelligenceState.PARTIAL if items else CustomerIntelligenceState.INSUFFICIENT).value, "recommendation_count": len(items) if items else None, "presented_count": presented if items else None, "purchased_count": purchased if items else None, "suppression_count": states.count("SUPPRESSED") if items else None, "rejection_count": states.count("REJECTED") if items else None, "refund_count": states.count("REFUNDED") if items else None, "delivery_success_count": states.count("DELIVERED") if items else None, "recommendation_conversion": purchased / presented if presented else None, "calculated_at": now, "insufficiencies": (() if presented else ("RECOMMENDATION_EXPOSURE_DENOMINATOR_REQUIRED",))}

    @staticmethod
    def _output_provenance(
        *, source_authority, source_ids, creator_profile_id,
        customer_identity_path, calculated_at, included, excluded, method,
        confidence, conflicts=(), insufficiencies=(), time_window="all_available",
        excluded_record_reasons=(), lifecycle_filters=(), signal_quality=None,
        direction=None, aggregate_evidence=False, aggregate_name=None,
    ):
        return {
            "source_authority": source_authority,
            "source_ids": tuple(source_ids),
            "creator_profile_id": creator_profile_id,
            "customer_identity_path": customer_identity_path,
            "time_window": time_window,
            "calculated_at": calculated_at,
            "included_evidence": tuple(included),
            "excluded_evidence": tuple(excluded),
            "included_evidence_count": len(tuple(included)),
            "excluded_evidence_count": len(tuple(excluded)),
            "excluded_record_reasons": tuple(excluded_record_reasons),
            "lifecycle_filters": tuple(lifecycle_filters),
            "derivation_method": method,
            "signal_quality": signal_quality,
            "direction": direction,
            "confidence": confidence,
            "conflicts": tuple(conflicts),
            "insufficiencies": tuple(insufficiencies),
            "aggregate_evidence": bool(aggregate_evidence),
            "aggregate_name": aggregate_name,
        }

    def _preference_with_provenance(self, item, context):
        included = item.positive_evidence + item.contradictory_evidence + item.supporting_evidence
        return replace(item, provenance=self._output_provenance(
            source_authority="Purchase Intents, Entitlements, and Conversation History",
            source_ids=included,
            included=included,
            excluded=(),
            method=item.derivation_method,
            confidence=item.confidence,
            signal_quality=item.quality.value,
            direction=item.direction,
            conflicts=item.conflicts,
            insufficiencies=item.insufficiencies,
            **context,
        ))

    def _metric_group_provenance(self, metric, evidence, authority, context, section_state):
        source_ids = tuple(value for value in (
            self._canonical_fact(authority, item, context["creator_profile_id"],
                                 context["customer_identity_path"]).record_id
            for item in tuple(evidence or ())
        ) if value is not None)
        group_provenance = self._output_provenance(
            source_authority=authority, source_ids=source_ids,
            included=source_ids, excluded=(),
            method="deterministic aggregate from referenced evidence",
            confidence=1.0 if source_ids else 0.0,
            insufficiencies=metric.get("insufficiencies") or (),
            lifecycle_filters=("source lifecycle preserved",),
            aggregate_evidence=not bool(source_ids), **context,
        )
        if section_state == CustomerIntelligenceState.UNAVAILABLE:
            return {"state": section_state.value,
                    "insufficiencies": metric.get("insufficiencies") or ("SOURCE_UNAVAILABLE",),
                    "metric_details": {}, "provenance": group_provenance}
        numeric = {
            key: value for key, value in metric.items()
            if key not in {"state", "calculated_at", "insufficiencies", "provenance", "metric_details"}
            and isinstance(value, (int, float)) and not isinstance(value, bool)
        }
        details = {}
        for name, value in numeric.items():
            numerator = denominator = None
            if name == "completion_rate": numerator, denominator = metric.get("lifecycle_counts", {}).get("COMPLETED"), metric.get("session_count")
            elif name == "abandonment_rate": numerator, denominator = metric.get("lifecycle_counts", {}).get("ABANDONED"), metric.get("session_count")
            elif name == "expiration_rate": numerator, denominator = metric.get("lifecycle_counts", {}).get("EXPIRED"), metric.get("session_count")
            elif name == "bundle_purchase_ratio": numerator, denominator = metric.get("bundle_purchase_count"), (metric.get("bundle_purchase_count") or 0) + (metric.get("single_item_purchase_count") or 0)
            elif name == "conversion_rate": numerator, denominator = metric.get("numerator"), metric.get("denominator")
            elif name == "recommendation_conversion": numerator, denominator = metric.get("purchased_count"), metric.get("presented_count")
            elif name == "average_response_latency_seconds": denominator = metric.get("response_latency_observations"); numerator = value * denominator if value is not None and denominator else None
            unit = "ratio" if name.endswith("_rate") or name.endswith("_ratio") or name.endswith("_conversion") else "seconds" if name.endswith("_seconds") else "records" if name.endswith("_count") or name in {"numerator", "denominator"} else "value"
            details[name] = CustomerIntelligenceMetric(
                name=name, value=value, unit=unit, state=section_state,
                calculation_method=f"deterministic {name} from referenced {authority}",
                calculated_at=context["calculated_at"], numerator=numerator,
                denominator=denominator, included_records=source_ids,
                lifecycle_filters=("source lifecycle preserved",),
                confidence=1.0 if source_ids else 0.0,
                insufficiencies=tuple(metric.get("insufficiencies") or ()),
                provenance={**group_provenance, "derivation_method": f"deterministic {name} from referenced {authority}"},
            )
        return {**metric, "metric_details": details, "provenance": group_provenance}

    def _attach_mapping_provenance(self, item, context, authority):
        source_ids = tuple(item.get("source_record_ids") or ())
        aggregate_evidence = bool(item.get("aggregate_evidence"))
        return {**item, "provenance": self._output_provenance(
            source_authority=item.get("source_authority") or authority,
            source_ids=source_ids,
            included=source_ids,
            excluded=(),
            method=item.get("type", "evidence interpretation"),
            confidence=float(item.get("confidence") or 0),
            conflicts=item.get("conflicts") or (),
            insufficiencies=item.get("insufficiencies") or (),
            signal_quality=item.get("signal_quality"),
            direction=item.get("direction"),
            aggregate_evidence=aggregate_evidence,
            aggregate_name=item.get("aggregate_name"),
            **context,
        )}

    def _classification(self, item, context):
        evidence = tuple(self._read_value(item, "evidence") or ())
        source = self._text(self._read_value(item, "source")) or "Unknown authority"
        confidence = float(self._read_value(item, "confidence") or 0)
        conflicts = tuple(self._read_value(item, "conflicts") or ())
        insufficiencies = tuple(self._read_value(item, "insufficiencies") or ())
        return {
            "label": self._text(self._read_value(item, "label")) or "UNKNOWN",
            "source": source,
            "source_definition": self._text(self._read_value(item, "source_definition")),
            "confidence": confidence,
            "calculated_at": self._text(self._read_value(item, "calculated_at")) or context["calculated_at"],
            "evidence": evidence,
            "conflicts": conflicts,
            "insufficiencies": insufficiencies,
            "provenance": self._output_provenance(
                source_authority=source, source_ids=evidence,
                included=evidence, excluded=(), method="preserve source classification",
                confidence=confidence, conflicts=conflicts,
                insufficiencies=insufficiencies, **context,
            ),
        }

    def _interpretation(self, item, kind, now, context):
        primary = item.contradictory_evidence if kind == "AVERSION" else item.positive_evidence
        contradictory = item.positive_evidence if kind == "AVERSION" else item.contradictory_evidence
        value = {"type": kind, "dimension": item.dimension, "subject": item.subject, "confidence": item.confidence, "signal_quality": item.quality.value, "direction": item.direction, "evidence": primary, "source_record_ids": primary, "supporting_evidence": item.supporting_evidence, "contradictory_evidence": contradictory, "calculated_at": now, "authorizes_action": False}
        return self._attach_mapping_provenance(value, context, "Customer Intelligence evidence-backed preference")

    @classmethod
    def _opportunities(cls, bundle, video, sessions, preferences, now, purchase_intents, purchase_history):
        values = []
        if bundle.get("bundle_purchase_count", 0):
            records = tuple(dict.fromkeys(
                value for item in purchase_history
                for value in (item.get("purchase_intent_reference"), item.get("transaction_reference"))
                if value
            ))
            values.append({"type": "BUNDLE_HISTORY", "confidence": .6,
                           "source_authority": "Purchase Intents and Customer Commerce Transactions",
                           "source_record_ids": records,
                           "aggregate_evidence": not bool(records),
                           "aggregate_name": None if records else "bundle_purchase_count",
                           "calculated_at": now, "authorizes_action": False})
        if (video.get("videos_purchased") or 0) >= 2:
            purchased = tuple(item for item in purchase_intents
                              if str(cls._read_value(item, "status") or "").upper() == "PURCHASED"
                              and str(cls._read_value(item, "media_type") or cls._plain_mapping(cls._read_value(item, "created_metadata")).get("media_type") or "").upper() == "VIDEO")
            records = tuple(filter(None, (cls._text(cls._read_value(item, "purchase_intent_id") or cls._read_value(item, "purchaseIntentId")) for item in purchased)))
            related = tuple({"authority": "Commercial Offering", "record_id": value} for value in dict.fromkeys(filter(None, (cls._text(cls._read_value(item, "commercial_offering_id") or cls._read_value(item, "commercialOfferingId")) for item in purchased))))
            values.append({"type": "REPEATED_VIDEO_PURCHASE", "confidence": .8,
                           "source_authority": "Purchase Intents",
                           "source_record_ids": records,
                           "related_source_references": related,
                           "aggregate_evidence": not bool(records),
                           "aggregate_name": None if records else "video_purchase_aggregate",
                           "calculated_at": now, "authorizes_action": False})
        return tuple(values)

    @classmethod
    def _risks(cls, session_profile, recommendation, context, now, sessions):
        values = []
        if session_profile.get("abandonment_rate") is not None and session_profile["abandonment_rate"] >= .5 and (session_profile.get("session_count") or 0) >= 2:
            abandoned = tuple(item for item in sessions if str(cls._read_value(item, "state") or "").upper() == "ABANDONED")
            records = tuple(filter(None, (cls._text(cls._read_value(item, "sales_session_id") or cls._read_value(item, "salesSessionId")) for item in abandoned)))
            values.append({"type": "REPEATED_SESSION_ABANDONMENT", "confidence": .7,
                           "source_authority": "Sales Sessions",
                           "source_record_ids": records,
                           "aggregate_evidence": not bool(records),
                           "aggregate_name": None if records else "session_abandonment_aggregate",
                           "calculated_at": now, "authorizes_action": False})
        if context.get("identity_conflicts"):
            values.append({"type": "IDENTITY_CONFLICT", "confidence": 1.0,
                           "source_authority": "Canonical Identity Context",
                           "source_record_ids": (), "aggregate_evidence": True,
                           "aggregate_name": "identity_conflicts",
                           "conflicts": tuple(context["identity_conflicts"]),
                           "calculated_at": now, "authorizes_action": False})
        return tuple(values)

    @staticmethod
    def _read_value(item, name):
        if item is None: return None
        if isinstance(item, Mapping): return item.get(name)
        return getattr(item, name, None)

    @classmethod
    def _evidence_conflicts(cls, evidence):
        if isinstance(evidence, Mapping):
            items = (evidence,)
        elif isinstance(evidence, (tuple, list, set)):
            items = evidence
        else:
            items = (evidence,) if evidence else ()
        values = []
        for item in items:
            values.extend(str(value) for value in (cls._read_value(item, "conflicts") or ()))
            metadata = cls._read_value(item, "metadata") or {}
            values.extend(str(value) for value in (cls._read_value(metadata, "conflicts") or ()))
        return tuple(dict.fromkeys(values))

    @classmethod
    def _evidence_complete(cls, evidence):
        items = (evidence,) if isinstance(evidence, Mapping) else tuple(evidence or ())
        return bool(items) and all(
            cls._read_value(item, "evidence_complete") is True
            or cls._read_value(item, "complete") is True
            for item in items
        )

    @classmethod
    def _evidence_incomplete(cls, evidence):
        items = (evidence,) if isinstance(evidence, Mapping) else tuple(evidence or ())
        return any(
            cls._read_value(item, "evidence_complete") is False
            or cls._read_value(item, "complete") is False
            or bool(cls._read_value(item, "insufficiencies"))
            or bool(cls._read_value(cls._read_value(item, "metadata") or {}, "insufficiencies"))
            for item in items
        )

    @staticmethod
    def _normalize_source_failures(source_failures):
        aliases = {
            "customer_identity": "identity", "identity_mapping": "identity",
            "customer_commerce_transactions": "transactions", "transaction": "transactions",
            "purchase_intent": "purchase_intents", "purchase_intents": "purchase_intents",
            "customer_entitlements": "entitlements", "entitlement": "entitlements",
            "ownership_intelligence": "ownership",
            "sales_sessions": "sessions", "sales_session": "sessions",
            "messages": "conversations", "conversation": "conversations",
            "conversation_history": "conversations",
            "recommendation_history": "recommendations", "recommendation": "recommendations",
            "commercial_roles": "roles", "commercial_role": "roles",
            "asset_lineage": "lineage",
            "publication": "publications", "commercial_publications": "publications",
            "fulfillments": "fulfillment", "commercial_fulfillment": "fulfillment",
            "deliveries": "delivery",
        }
        normalized = {}
        for key, error in dict(source_failures or {}).items():
            source = re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")
            source = aliases.get(source, source)
            if isinstance(error, BaseException):
                error_class = type(error).__name__
            else:
                candidate = str(error).split(":", 1)[0].strip().split(".")[-1]
                error_class = candidate if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]*(?:Error|Exception|Unavailable)", candidate) else "SourceUnavailable"
            normalized[source] = error_class
        return normalized

    @classmethod
    def _plain_mapping(cls, item):
        if item is None: return {}
        if isinstance(item, Mapping): return dict(item)
        fields = getattr(item, "__dataclass_fields__", {})
        return {name: getattr(item, name) for name in fields}

    @staticmethod
    def _as_datetime(value):
        if isinstance(value, datetime): return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        if value:
            try: return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError: return None
        return None

    @classmethod
    def _profile_payload(cls, profile):
        return {name: getattr(profile, name) for name in profile.__dataclass_fields__}

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


class CustomerIntelligenceService:
    """Canonical immutable Customer Intelligence evidence boundary.

    The public contract is limited to query-time profile composition and
    immutable consumer projections. Historical customer-memory decisions live
    in ``CustomerIntelligenceCompatibilityAdapter``.
    """

    def __init__(
        self,
        customer_service: Any | None = None,
        *,
        profile_composer: CustomerIntelligenceCompatibilityAdapter | None = None,
    ) -> None:
        self.__profile_composer = profile_composer or CustomerIntelligenceCompatibilityAdapter(
            customer_service=customer_service,
        )

    def build_canonical_profile(self, **sources: Any) -> CanonicalCustomerIntelligenceProfile:
        return self.__profile_composer.build_canonical_profile(**sources)

    def project_canonical_profile(
        self, profile: CanonicalCustomerIntelligenceProfile, consumer: str,
    ) -> Mapping[str, Any]:
        return self.__profile_composer.project_canonical_profile(profile, consumer)

    @staticmethod
    def _profile_payload(profile: CanonicalCustomerIntelligenceProfile) -> Mapping[str, Any]:
        return deep_freeze({
            name: getattr(profile, name) for name in profile.__dataclass_fields__
        })
