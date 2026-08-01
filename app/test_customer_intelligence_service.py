import ast
import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.business_learning import LearningContext, LearningSummary
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
from app.models.telegram_commerce import (
    TelegramCommerceMemory,
    TelegramConversationState,
    TelegramExperienceProgression,
)
from app.services.customer_intelligence_service import (
    CustomerIntelligenceCompatibilityAdapter as CustomerIntelligenceService,
)


class FakeCustomerService:
    def get_customer_summary(self, customer_id=None, **lookup):
        return {
            "customer_id": customer_id or "7:42",
            "display_name": "Test Customer",
            "message_count": 8,
            "current_experience_id": "experience-1",
            "value_tier": "HIGH_VALUE",
            "buyer_tier": "ACTIVE_BUYER",
            "offer_count": 2,
        }

    def get_customer_commerce_summary(self, customer_id=None, **lookup):
        return {
            "customer_id": customer_id or "7:42",
            "products_purchased": ("product-1",),
            "products_owned": ("product-1",),
            "purchase_summary": {
                "purchase_count": 1,
                "total_spend_cents": 1999,
            },
            "telegram_conversation_state": {
                "current_experience": "experience-1",
                "current_product": "product-2",
                "conversation_status": "chat",
                "commerce_progress": "offer_active",
            },
            "commerce_memory": {
                "purchased_products": ("product-1",),
                "free_assets_delivered": ("asset-free-1",),
                "paid_media_links_delivered": ("product-1",),
                "customer_spending_summary": {
                    "purchase_count": 1,
                    "total_spend_cents": 1999,
                },
                "customer_engagement_summary": {
                    "message_count": 8,
                    "offer_count": 2,
                },
            },
        }


class CustomerIntelligenceServiceTests(unittest.TestCase):
    def test_customer_intelligence_models_instantiate(self):
        identity = CustomerIdentity(
            canonical_customer_id="customer-1",
            customer_id="customer-1",
            provider="telegram",
            provider_customer_id="42",
            telegram_identifier="42",
            provider_identities={
                "telegram": {
                    "provider": "telegram",
                    "provider_customer_id": "42",
                }
            },
        )
        profile = CustomerProfile(
            display_name="Customer",
            preferred_name="Cust",
            timezone="America/Chicago",
            language="en",
            interests=("vip",),
            creator_notes=("likes direct messages",),
            tags=("subscriber",),
            customer_segments=("active",),
        )
        memory = CustomerCommerceMemory(products_purchased=("product-1",))
        progress = CustomerExperienceProgress(
            current_experience_id="experience-1",
            progress_percentage=20,
        )
        snapshot = CustomerIntelligenceSnapshot(
            identity=identity,
            profile=profile,
            relationship_stage=CustomerRelationshipStage.ACTIVE,
            commerce_memory=memory,
            experience_progress=progress,
        )

        self.assertEqual(snapshot.identity.provider, "telegram")
        self.assertEqual(snapshot.identity.canonical_customer_id, "customer-1")
        self.assertEqual(snapshot.identity.telegram_identifier, "42")
        self.assertEqual(snapshot.profile.interests, ("vip",))
        self.assertEqual(snapshot.profile.preferred_name, "Cust")
        self.assertEqual(snapshot.profile.tags, ("subscriber",))
        self.assertEqual(snapshot.commerce_memory.products_purchased, ("product-1",))
        self.assertEqual(snapshot.relationship_stage, CustomerRelationshipStage.ACTIVE)

    def test_customer_profile_creation(self):
        profile = CustomerProfile(
            display_name="Riley",
            username="riley_7",
            preferred_name="Ry",
            timezone="America/Chicago",
            language="en",
            interests=("cosplay", "fitness"),
            preferences={"tone": "playful"},
            creator_notes=("prefers short replies",),
            tags=("vip",),
            customer_segments=("returning",),
            metadata={"source": "test"},
        )

        self.assertEqual(profile.display_name, "Riley")
        self.assertEqual(profile.preferred_name, "Ry")
        self.assertEqual(profile.preferences["tone"], "playful")
        self.assertEqual(profile.customer_segments, ("returning",))

    def test_profile_merge_keeps_existing_values_and_applies_updates(self):
        service = CustomerIntelligenceService()
        merged = service.merge_profile(
            CustomerProfile(
                display_name="Riley",
                username="riley_7",
                interests=("cosplay",),
                preferences={"tone": "warm", "budget": "medium"},
                tags=("subscriber",),
            ),
            {
                "preferred_name": "Ry",
                "interests": ("cosplay", "fitness"),
                "preferences": {"budget": "high"},
                "tags": ("vip",),
                "customer_segments": ("active",),
            },
        )

        self.assertEqual(merged.display_name, "Riley")
        self.assertEqual(merged.preferred_name, "Ry")
        self.assertEqual(merged.interests, ("cosplay", "fitness"))
        self.assertEqual(merged.preferences["tone"], "warm")
        self.assertEqual(merged.preferences["budget"], "high")
        self.assertEqual(merged.tags, ("subscriber", "vip"))
        self.assertEqual(merged.customer_segments, ("active",))

    def test_preference_updates_are_merged_without_mutating_profile(self):
        service = CustomerIntelligenceService()
        profile = CustomerProfile(
            preferences={"tone": "warm", "budget": "medium"},
        )

        updated = service.update_preferences(
            profile,
            {"budget": "high", "language_style": "casual"},
        )

        self.assertEqual(profile.preferences["budget"], "medium")
        self.assertEqual(updated.preferences["tone"], "warm")
        self.assertEqual(updated.preferences["budget"], "high")
        self.assertEqual(updated.preferences["language_style"], "casual")

    def test_interest_updates_are_deduplicated(self):
        service = CustomerIntelligenceService()
        updated = service.update_interests(
            CustomerProfile(interests=("cosplay",)),
            ("cosplay", "fitness", "travel"),
        )

        self.assertEqual(updated.interests, ("cosplay", "fitness", "travel"))

    def test_provider_identity_normalization_is_provider_neutral(self):
        identity = CustomerIntelligenceService().normalize_provider_identity(
            provider=" Telegram ",
            provider_customer_id=42,
            provider_account_id=-100,
            provider_username="riley",
            metadata={"source": "context"},
        )

        self.assertEqual(identity["provider"], "telegram")
        self.assertEqual(identity["provider_customer_id"], "42")
        self.assertEqual(identity["provider_account_id"], "-100")
        self.assertEqual(identity["provider_username"], "riley")
        self.assertEqual(identity["metadata"]["source"], "context")

    def test_empty_profile_handling_and_summary_generation(self):
        service = CustomerIntelligenceService()
        profile = service.normalize_customer_profile(None)
        summary = service.summarize_profile(profile)

        self.assertIsInstance(profile, CustomerProfile)
        self.assertEqual(profile.interests, ())
        self.assertEqual(profile.preferences, {})
        self.assertEqual(summary["summary_label"], "Unknown Customer")
        self.assertFalse(summary["has_profile_data"])

    def test_learning_context_is_metadata_only(self):
        snapshot = CustomerIntelligenceService().build_customer_snapshot(
            customer_id="customer-learning",
            learning_context=LearningContext(
                context_type="customer_learning",
                learning_summary=LearningSummary(total_insights=1),
            ),
        )

        self.assertTrue(
            snapshot.compatibility_metadata["learning_context_consumed"]
        )
        self.assertTrue(
            snapshot.compatibility_metadata["learning_context_evidence_only"]
        )
        self.assertEqual(
            snapshot.compatibility_metadata["learning_context_type"],
            "customer_learning",
        )
        self.assertEqual(
            snapshot.identity.canonical_customer_id,
            "customer-learning",
        )

    def test_profile_summary_prefers_preferred_name(self):
        summary = CustomerIntelligenceService().summarize_profile(
            CustomerProfile(
                display_name="Riley",
                username="riley_7",
                preferred_name="Ry",
                interests=("cosplay",),
                tags=("vip",),
            )
        )

        self.assertEqual(summary["summary_label"], "Ry")
        self.assertTrue(summary["has_profile_data"])
        self.assertEqual(summary["tags"], ("vip",))

    def test_offer_recording(self):
        history = CustomerIntelligenceService().record_offer(
            CustomerCommerceMemory(),
            product_id="product-1",
            offer_id="offer-1",
            offered_at="2026-07-05T12:00:00Z",
            outcome="offered",
        )

        self.assertEqual(history.products_offered, ("product-1",))
        self.assertEqual(history.previous_offers, ("offer-1",))
        self.assertEqual(history.offer_timestamps["offer-1"], "2026-07-05T12:00:00Z")
        self.assertEqual(history.offer_outcomes["offer-1"], "offered")
        self.assertEqual(history.offer_events[0]["event_type"], "offer")

    def test_purchase_recording(self):
        history = CustomerIntelligenceService().record_purchase(
            CustomerCommerceMemory(),
            product_id="bundle-1",
            purchase_id="purchase-1",
            purchased_at="2026-07-05T12:05:00Z",
            product_type="bundle",
        )

        self.assertEqual(history.products_purchased, ("bundle-1",))
        self.assertEqual(history.purchased_bundles, ("bundle-1",))
        self.assertEqual(history.previous_purchases, ("purchase-1",))
        self.assertEqual(
            history.purchase_timestamps["purchase-1"],
            "2026-07-05T12:05:00Z",
        )
        self.assertEqual(history.last_purchase["event_id"], "purchase-1")

    def test_delivery_recording(self):
        service = CustomerIntelligenceService()
        free_history = service.record_delivery(
            CustomerCommerceMemory(),
            product_id="product-free-1",
            asset_id="asset-1",
            delivery_id="delivery-1",
            delivery_type="free",
            delivered_at="2026-07-05T12:10:00Z",
        )
        paid_history = service.record_delivery(
            free_history,
            product_id="product-paid-1",
            delivery_id="delivery-2",
            delivery_type="paid",
        )

        self.assertEqual(free_history.free_assets_delivered, ("asset-1",))
        self.assertEqual(free_history.delivered_free_products, ("product-free-1",))
        self.assertEqual(
            free_history.delivery_timestamps["delivery-1"],
            "2026-07-05T12:10:00Z",
        )
        self.assertEqual(paid_history.delivered_paid_products, ("product-paid-1",))
        self.assertEqual(paid_history.paid_products_delivered, ("product-paid-1",))

    def test_completed_experience_recording(self):
        history = CustomerIntelligenceService().record_completed_experience(
            CustomerCommerceMemory(),
            experience_id="experience-1",
            completed_at="2026-07-05T12:15:00Z",
        )

        self.assertEqual(history.completed_experience_ids, ("experience-1",))
        self.assertEqual(
            history.completed_experience_events[0]["event_type"],
            "completed_experience",
        )
        self.assertEqual(
            history.completed_experience_events[0]["timestamp"],
            "2026-07-05T12:15:00Z",
        )

    def test_commerce_duplicate_detection(self):
        service = CustomerIntelligenceService()
        history = service.record_offer(
            CustomerCommerceMemory(),
            product_id="product-1",
            offer_id="offer-1",
        )
        duplicate = service.record_offer(
            history,
            product_id="product-1",
            offer_id="offer-1",
        )

        self.assertEqual(len(duplicate.offer_events), 1)
        self.assertEqual(duplicate.products_offered, ("product-1",))
        self.assertEqual(duplicate.duplicate_prevention_signals, ("offer:offer-1",))

    def test_purchase_lookup(self):
        service = CustomerIntelligenceService()
        history = service.record_purchase(
            CustomerCommerceMemory(),
            product_id="story-1",
            product_type="story",
        )

        self.assertTrue(service.has_purchased_product(history, "story-1"))
        self.assertFalse(service.has_purchased_product(history, "story-2"))

    def test_delivery_lookup(self):
        service = CustomerIntelligenceService()
        history = service.record_delivery(
            CustomerCommerceMemory(),
            product_id="product-paid-1",
            delivery_type="paid",
        )

        self.assertTrue(service.has_delivered_product(history, "product-paid-1"))
        self.assertFalse(service.has_delivered_product(history, "product-paid-2"))

    def test_commerce_history_summary(self):
        service = CustomerIntelligenceService()
        history = service.record_offer(
            CustomerCommerceMemory(),
            product_id="product-1",
            offer_id="offer-1",
        )
        history = service.record_purchase(
            history,
            product_id="product-1",
            purchase_id="purchase-1",
        )
        history = service.record_delivery(
            history,
            product_id="product-1",
            delivery_id="delivery-1",
            delivery_type="paid",
        )
        history = service.record_completed_experience(
            history,
            experience_id="experience-1",
        )

        summary = service.summarize_commerce_history(history)

        self.assertTrue(summary["has_commerce_history"])
        self.assertEqual(summary["offer_count"], 1)
        self.assertEqual(summary["purchase_count"], 1)
        self.assertEqual(summary["delivery_count"], 1)
        self.assertEqual(summary["completed_experience_count"], 1)
        self.assertTrue(summary["metadata"]["canonical_commerce_history"])

    def test_resolves_provider_neutral_identity_from_telegram_context(self):
        identity = CustomerIntelligenceService().resolve_customer_identity(
            telegram_context={
                "engine_user_id": "7:-123456789",
                "telegram_user_id": 42,
                "telegram_chat_id": -123456789,
            }
        )

        self.assertEqual(identity.customer_id, "7:-123456789")
        self.assertEqual(identity.canonical_customer_id, "7:-123456789")
        self.assertEqual(identity.provider, "telegram")
        self.assertEqual(identity.provider_customer_id, "42")
        self.assertEqual(identity.provider_account_id, "-123456789")
        self.assertEqual(identity.telegram_identifier, "42")
        self.assertEqual(identity.platform_identifiers["telegram"], "42")
        self.assertEqual(
            identity.provider_identities["telegram"]["provider_customer_id"],
            "42",
        )

    def test_snapshot_builds_with_empty_default_memory(self):
        snapshot = CustomerIntelligenceService().build_customer_snapshot()

        self.assertEqual(snapshot.relationship_stage, CustomerRelationshipStage.NEW)
        self.assertIsInstance(snapshot.identity, CustomerIdentity)
        self.assertEqual(snapshot.commerce_memory.products_purchased, ())
        self.assertEqual(snapshot.commerce_memory.free_assets_delivered, ())
        self.assertEqual(snapshot.experience_progress.progress_percentage, 0)
        self.assertTrue(snapshot.compatibility_metadata["read_only"])
        self.assertFalse(snapshot.compatibility_metadata["calls_provider_apis"])
        self.assertFalse(snapshot.compatibility_metadata["executes_commerce"])

    def test_snapshot_builds_from_supplied_commerce_memory_context(self):
        commerce_memory = TelegramCommerceMemory(
            purchased_products=("product-1",),
            current_experience_id="experience-1",
            free_assets_delivered=("asset-free-1",),
            paid_media_links_delivered=("https://fanvue.test/media-1",),
            previous_offers=("offer-1",),
            customer_spending_summary={
                "purchase_count": 1,
                "total_spend_cents": 1999,
            },
            customer_engagement_summary={"message_count": 6},
        )
        conversation_state = TelegramConversationState(
            current_experience_id="experience-1",
            current_product_id="product-2",
            current_asset_id="asset-2",
            conversation_mode="experience",
            commerce_state="offer_active",
        )
        progression = TelegramExperienceProgression(
            current_experience_id="experience-1",
            current_story_position="scene-2",
            progress_percentage=40,
        )

        snapshot = CustomerIntelligenceService().build_customer_snapshot(
            customer_id="7:42",
            provider="telegram",
            provider_customer_id="42",
            commerce_memory=commerce_memory,
            conversation_state=conversation_state,
            experience_progression=progression,
        )

        self.assertEqual(snapshot.relationship_stage, CustomerRelationshipStage.PURCHASER)
        self.assertEqual(snapshot.identity.provider, "telegram")
        self.assertEqual(
            snapshot.commerce_memory.products_purchased,
            ("product-1",),
        )
        self.assertEqual(
            snapshot.commerce_memory.free_assets_delivered,
            ("asset-free-1",),
        )
        self.assertEqual(
            snapshot.commerce_memory.paid_products_delivered,
            ("https://fanvue.test/media-1",),
        )
        self.assertEqual(snapshot.experience_progress.current_experience_id, "experience-1")
        self.assertEqual(snapshot.experience_progress.current_product_id, "product-2")
        self.assertEqual(snapshot.experience_progress.current_asset_id, "asset-2")
        self.assertEqual(snapshot.experience_progress.progress_percentage, 40)
        self.assertTrue(
            snapshot.compatibility_metadata[
                "telegram_commerce_memory_compatibility"
            ]
        )

    def test_snapshot_can_reuse_existing_customer_service_summaries(self):
        snapshot = CustomerIntelligenceService(
            customer_service=FakeCustomerService()
        ).build_customer_snapshot(
            "7:42",
            provider="telegram",
            provider_customer_id="42",
        )

        self.assertEqual(snapshot.relationship_stage, CustomerRelationshipStage.PURCHASER)
        self.assertEqual(snapshot.profile.display_name, "Test Customer")
        self.assertEqual(snapshot.profile.preferences["value_tier"], "HIGH_VALUE")
        self.assertEqual(snapshot.commerce_memory.products_purchased, ("product-1",))
        self.assertEqual(
            snapshot.commerce_memory.free_assets_delivered,
            ("asset-free-1",),
        )
        self.assertEqual(snapshot.experience_progress.current_experience_id, "experience-1")
        self.assertEqual(snapshot.experience_progress.current_product_id, "product-2")

    def test_relationship_stage_inference_basic_cases(self):
        service = CustomerIntelligenceService()

        self.assertEqual(
            service.infer_relationship_stage(),
            CustomerRelationshipStage.NEW,
        )
        self.assertEqual(
            service.infer_relationship_stage(
                customer_summary={"message_count": 1},
            ),
            CustomerRelationshipStage.RETURNING,
        )
        self.assertEqual(
            service.infer_relationship_stage(
                customer_summary={"message_count": 5},
            ),
            CustomerRelationshipStage.ACTIVE,
        )
        self.assertEqual(
            service.infer_relationship_stage(
                commerce_memory=CustomerCommerceMemory(
                    products_purchased=("product-1",)
                ),
            ),
            CustomerRelationshipStage.PURCHASER,
        )
        self.assertEqual(
            service.infer_relationship_stage(
                commerce_memory=SimpleNamespace(
                    customer_spending_summary={"purchase_count": 1}
                ),
            ),
            CustomerRelationshipStage.PURCHASER,
        )

    def test_relationship_repeat_purchaser_inference(self):
        stage = CustomerIntelligenceService().infer_relationship_stage(
            commerce_memory=CustomerCommerceMemory(
                purchase_events=(
                    {"event_id": "purchase-1"},
                    {"event_id": "purchase-2"},
                )
            )
        )

        self.assertEqual(stage, CustomerRelationshipStage.REPEAT_PURCHASER)

    def test_relationship_vip_inference(self):
        service = CustomerIntelligenceService()

        self.assertEqual(
            service.infer_relationship_stage(
                commerce_memory=CustomerCommerceMemory(
                    customer_spending_summary={
                        "purchase_count": 5,
                        "total_spend_cents": 12000,
                    }
                )
            ),
            CustomerRelationshipStage.VIP,
        )
        self.assertEqual(
            service.infer_relationship_stage(
                profile=CustomerProfile(tags=("vip",)),
            ),
            CustomerRelationshipStage.VIP,
        )

    def test_relationship_dormant_customer_inference(self):
        stage = CustomerIntelligenceService().infer_relationship_stage(
            customer_summary={"message_count": 12},
            last_interaction_metadata={"days_since_last_interaction": 45},
        )

        self.assertEqual(stage, CustomerRelationshipStage.DORMANT)

    def test_relationship_engagement_calculation(self):
        engagement = CustomerIntelligenceService().calculate_engagement(
            profile=CustomerProfile(interests=("cosplay",), tags=("subscriber",)),
            commerce_memory=CustomerCommerceMemory(
                products_offered=("product-1",),
                delivery_events=({"event_id": "delivery-1"},),
                purchase_events=({"event_id": "purchase-1"},),
            ),
            experience_progress=CustomerExperienceProgress(
                current_experience_id="experience-1"
            ),
            customer_summary={"message_count": 6},
        )

        self.assertGreaterEqual(engagement["score"], 60)
        self.assertEqual(engagement["message_count"], 6)
        self.assertTrue(engagement["experience_active"])

    def test_relationship_commerce_maturity_calculation(self):
        service = CustomerIntelligenceService()

        self.assertEqual(
            service.determine_commerce_maturity(
                commerce_memory=CustomerCommerceMemory(
                    products_offered=("product-1",)
                )
            ),
            "offer_aware",
        )
        self.assertEqual(
            service.determine_commerce_maturity(
                commerce_memory=CustomerCommerceMemory(
                    products_purchased=("product-1",)
                )
            ),
            "buyer",
        )
        self.assertEqual(
            service.determine_commerce_maturity(
                commerce_memory=CustomerCommerceMemory(
                    purchase_events=(
                        {"event_id": "purchase-1"},
                        {"event_id": "purchase-2"},
                    )
                )
            ),
            "repeat_buyer",
        )

    def test_relationship_recommendation_generation(self):
        service = CustomerIntelligenceService()

        self.assertEqual(
            service.recommend_relationship_focus(
                relationship_stage=CustomerRelationshipStage.DORMANT,
            )[0],
            "Re-engage customer",
        )
        self.assertIn(
            "Customer likely ready for bundles",
            service.recommend_relationship_focus(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                commerce_maturity="repeat_buyer",
            ),
        )
        self.assertIn(
            "Continue current Experience",
            service.recommend_relationship_focus(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
                experience_progress=CustomerExperienceProgress(
                    current_experience_id="experience-1"
                ),
            ),
        )

    def test_relationship_summary_generation(self):
        service = CustomerIntelligenceService()
        relationship = service.update_relationship(
            profile=CustomerProfile(tags=("subscriber",)),
            commerce_memory=CustomerCommerceMemory(
                products_offered=("product-1",),
            ),
            customer_summary={"message_count": 3},
        )
        summary = service.summarize_relationship(relationship)

        self.assertIsInstance(relationship, CustomerRelationshipIntelligence)
        self.assertEqual(summary["stage"], CustomerRelationshipStage.RETURNING.value)
        self.assertEqual(summary["commerce_maturity"], "offer_aware")
        self.assertTrue(summary["metadata"]["read_only"])

    def test_runtime_customer_context_generation(self):
        service = CustomerIntelligenceService()
        snapshot = service.build_customer_snapshot(
            customer_id="customer-1",
            customer_profile=CustomerProfile(display_name="Riley"),
            commerce_memory=CustomerCommerceMemory(products_offered=("product-1",)),
        )

        context = service.build_runtime_customer_context(snapshot)

        self.assertEqual(context["type"], "customer_intelligence_snapshot")
        self.assertTrue(context["read_only"])
        self.assertEqual(
            context["snapshot"]["identity"]["customer_id"],
            "customer-1",
        )
        self.assertEqual(
            context["snapshot"]["profile"]["display_name"],
            "Riley",
        )
        self.assertTrue(context["compatibility_metadata"]["runtime_context"])

    def test_decision_customer_context_generation(self):
        service = CustomerIntelligenceService()
        snapshot = service.build_customer_snapshot(
            customer_id="customer-1",
            commerce_memory=CustomerCommerceMemory(
                products_purchased=("product-1",)
            ),
        )

        context = service.build_decision_customer_context(snapshot)

        self.assertEqual(
            context["type"],
            "customer_intelligence_decision_context",
        )
        self.assertFalse(context["generates_decisions"])
        self.assertEqual(
            context["relationship"]["stage"],
            CustomerRelationshipStage.PURCHASER.value,
        )
        self.assertEqual(
            context["commerce_history"]["products_purchased"],
            ("product-1",),
        )

    def test_execution_customer_context_generation(self):
        service = CustomerIntelligenceService()
        snapshot = service.build_customer_snapshot(
            customer_id="customer-1",
            commerce_memory=CustomerCommerceMemory(
                delivered_paid_products=("product-1",)
            ),
            conversation_state=SimpleNamespace(
                current_experience_id="experience-1"
            ),
        )

        context = service.build_execution_customer_context(snapshot)

        self.assertEqual(
            context["type"],
            "customer_intelligence_execution_context",
        )
        self.assertFalse(context["executes_commerce"])
        self.assertEqual(context["execution_owner"], "CommerceExecutionService")
        self.assertEqual(
            context["experience_progress"]["current_experience_id"],
            "experience-1",
        )

    def test_snapshot_enrichment(self):
        service = CustomerIntelligenceService()
        snapshot = service.build_customer_snapshot(customer_id="customer-1")
        enriched = service.enrich_customer_snapshot(
            snapshot,
            customer_profile={
                "preferred_name": "Ry",
                "interests": ("cosplay",),
            },
            commerce_memory=CustomerCommerceMemory(
                purchase_events=(
                    {"event_id": "purchase-1"},
                    {"event_id": "purchase-2"},
                )
            ),
            last_interaction_metadata={"days_since_last_interaction": 2},
        )

        self.assertEqual(enriched.profile.preferred_name, "Ry")
        self.assertEqual(enriched.profile.interests, ("cosplay",))
        self.assertEqual(
            enriched.relationship_stage,
            CustomerRelationshipStage.REPEAT_PURCHASER,
        )
        self.assertEqual(
            enriched.compatibility_metadata["enriched_by"],
            "CustomerIntelligenceCompatibilityAdapter",
        )

    def test_customer_review_generation(self):
        service = CustomerIntelligenceService()
        snapshot = service.build_customer_snapshot(
            customer_id="customer-1",
            customer_profile=CustomerProfile(
                display_name="Riley",
                interests=("cosplay",),
                preferences={"tone": "warm"},
                tags=("vip",),
                customer_segments=("repeat",),
            ),
            commerce_memory=CustomerCommerceMemory(
                products_purchased=("product-1",),
                delivered_paid_products=("product-1",),
                purchase_events=({"event_id": "purchase-1"},),
                delivery_events=({"event_id": "delivery-1"},),
            ),
            conversation_state=SimpleNamespace(
                current_experience_id="experience-1"
            ),
        )

        review = service.build_customer_review(snapshot)

        self.assertIsInstance(review, CustomerIntelligenceReview)
        self.assertEqual(review.customer_id, "customer-1")
        self.assertEqual(review.display_name, "Riley")
        self.assertEqual(review.relationship_stage, CustomerRelationshipStage.VIP.value)
        self.assertEqual(review.interests, ("cosplay",))
        self.assertEqual(review.preferences["tone"], "warm")
        self.assertTrue(review.metadata["presentation_only"])
        self.assertTrue(review.compatibility_metadata["read_only_projection"])

    def test_customer_review_summary_generation(self):
        service = CustomerIntelligenceService()
        purchaser = service.build_customer_snapshot(
            customer_id="customer-1",
            commerce_memory=CustomerCommerceMemory(
                products_purchased=("product-1",)
            ),
        )
        active = service.build_customer_snapshot(
            customer_id="customer-2",
            conversation_state=SimpleNamespace(
                current_experience_id="experience-1"
            ),
        )

        summary = service.build_customer_review_summary(
            snapshots=(purchaser, active)
        )

        self.assertIsInstance(summary, CustomerIntelligenceReviewSummary)
        self.assertEqual(summary.total_customers, 2)
        self.assertEqual(summary.customers_with_purchases, 1)
        self.assertEqual(summary.customers_with_active_experience, 1)
        self.assertEqual(len(summary.items), 2)
        self.assertTrue(summary.metadata["read_only"])

    def test_customer_review_relationship_summary_visibility(self):
        review = CustomerIntelligenceService().build_customer_review(
            CustomerIntelligenceService().build_customer_snapshot(
                commerce_memory=CustomerCommerceMemory(
                    products_purchased=("product-1",)
                )
            )
        )

        self.assertEqual(
            review.relationship["stage"],
            CustomerRelationshipStage.PURCHASER.value,
        )
        self.assertIn("engagement_level", review.relationship)
        self.assertIn("Relationship stage", review.recommendation_rationale[0])

    def test_customer_review_commerce_history_visibility(self):
        review = CustomerIntelligenceService().build_customer_review(
            CustomerIntelligenceService().build_customer_snapshot(
                commerce_memory=CustomerCommerceMemory(
                    products_purchased=("product-1",),
                    delivered_paid_products=("product-1",),
                    purchase_events=({"event_id": "purchase-1"},),
                    delivery_events=({"event_id": "delivery-1"},),
                )
            )
        )

        self.assertEqual(
            review.commerce_history["products_purchased"],
            ("product-1",),
        )
        self.assertEqual(review.purchase_history_summary["purchase_count"], 1)
        self.assertEqual(review.delivery_history_summary["delivery_count"], 1)

    def test_customer_review_experience_visibility(self):
        review = CustomerIntelligenceService().build_customer_review(
            CustomerIntelligenceService().build_customer_snapshot(
                conversation_state=SimpleNamespace(
                    current_experience_id="experience-1",
                    current_product_id="product-1",
                ),
                experience_progression=SimpleNamespace(
                    progress_percentage=35,
                ),
            )
        )

        self.assertEqual(
            review.experience_progress["current_experience_id"],
            "experience-1",
        )
        self.assertEqual(review.experience_progress["progress_percentage"], 35)

    def test_customer_review_recommendation_visibility(self):
        review = CustomerIntelligenceService().build_customer_review(
            CustomerIntelligenceService().build_customer_snapshot(
                commerce_memory=CustomerCommerceMemory(
                    purchase_events=(
                        {"event_id": "purchase-1"},
                        {"event_id": "purchase-2"},
                    )
                )
            )
        )

        self.assertIn("Customer likely ready for bundles", review.recommendations)
        self.assertTrue(review.recommendation_rationale)

    def test_customer_review_empty_customer_handling(self):
        service = CustomerIntelligenceService()
        review = service.build_customer_review(service.build_customer_snapshot())
        summary = service.build_customer_review_summary(reviews=(review,))

        self.assertIsInstance(review, CustomerIntelligenceReview)
        self.assertEqual(review.relationship_stage, CustomerRelationshipStage.NEW.value)
        self.assertEqual(review.purchase_history_summary["purchase_count"], 0)
        self.assertFalse(review.activity_summary["has_visible_activity"])
        self.assertEqual(summary.total_customers, 1)

    def test_service_imports_do_not_cross_ownership_boundaries(self):
        tree = ast.parse(Path("app/services/customer_intelligence_service.py").read_text())
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)

        forbidden_fragments = (
            "telegram",
            "fanvue",
            "decision_engine",
            "publishing",
            "commerce_execution",
            "product_strategy",
            "commerce_strategy",
        )
        for module in imports:
            with self.subTest(module=module):
                self.assertFalse(
                    any(fragment in module for fragment in forbidden_fragments)
                )


if __name__ == "__main__":
    unittest.main()
