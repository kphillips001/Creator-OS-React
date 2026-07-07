import unittest

from app.models.business_learning import (
    LearningContext,
    LearningSummary,
    PerformanceMetric,
    PerformanceSnapshot,
)
from app.models.commerce_strategy import (
    CommerceStrategyRecommendation,
    CommerceStrategyResult,
)
from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CustomerExperienceProgress,
    CustomerIdentity,
    CustomerIntelligenceSnapshot,
    CustomerProfile,
    CustomerRelationshipIntelligence,
    CustomerRelationshipStage,
)
from app.models.product_business import (
    ProductBusinessAvailability,
    ProductBusinessHealth,
    ProductBusinessRecommendation,
    ProductBusinessSnapshot,
)
from app.models.telegram_business import TelegramBusinessSnapshot
from app.models.telegram_commerce import (
    TelegramCommerceMemory,
    TelegramCommerceResult,
    TelegramCommerceState,
    TelegramConversationState,
    TelegramCustomerProgress,
    TelegramDeliveryDecision,
    TelegramDeliveryPayload,
    TelegramExperienceProgression,
)
from app.services.telegram_business_service import TelegramBusinessService


class FakeCustomerIntelligenceService:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def build_customer_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return self.snapshot


class FakeProductBusinessService:
    def __init__(self, snapshot):
        self.snapshot = snapshot
        self.calls = []

    def build_snapshot(self, **kwargs):
        self.calls.append(kwargs)
        return self.snapshot


class FakeBusinessLearningService:
    def __init__(self, context):
        self.context = context
        self.calls = []

    def build_customer_learning_context(self, **kwargs):
        self.calls.append(kwargs)
        return self.context

    def record_business_outcome(self, *args, **kwargs):
        raise AssertionError("TelegramBusinessService must not record learning")


class ForbiddenCommerceStrategyService:
    def recommend(self, *args, **kwargs):
        raise AssertionError("TelegramBusinessService must not generate strategy")


class ForbiddenPublishingService:
    def create_publishing_job(self, *args, **kwargs):
        raise AssertionError("TelegramBusinessService must not publish")

    def upload_asset_media_item_for_job(self, *args, **kwargs):
        raise AssertionError("TelegramBusinessService must not publish")


def customer_snapshot():
    return CustomerIntelligenceSnapshot(
        identity=CustomerIdentity(
            canonical_customer_id="customer-1",
            customer_id="telegram-customer-1",
            provider="telegram",
            provider_customer_id="123456789",
            provider_account_id="7",
            telegram_identifier="123456789",
            platform_identifiers={"telegram": "123456789"},
        ),
        profile=CustomerProfile(display_name="Ava Fan"),
        relationship_stage=CustomerRelationshipStage.ENGAGED,
        relationship_intelligence=CustomerRelationshipIntelligence(
            stage=CustomerRelationshipStage.ENGAGED,
            engagement_score=72,
            engagement_level="high",
            commerce_maturity="offer_ready",
            primary_recommendation="Continue premium experience",
            recommendations=("continue_experience",),
        ),
        commerce_memory=CustomerCommerceMemory(
            products_offered=("product-1",),
            products_purchased=("product-owned",),
            free_assets_delivered=("free-1",),
            paid_products_delivered=("product-paid",),
            previous_offers=("offer-1",),
            duplicate_prevention_signals=("offer:offer-1",),
            last_delivery={"delivery_method": "paid_media_link"},
        ),
        experience_progress=CustomerExperienceProgress(
            current_experience_id="experience-1",
            current_product_id="product-1",
            conversation_progress="experience",
            commerce_progress="paid_media_link_delivery",
            current_position="scene-2",
            progress_percentage=45,
        ),
    )


def product_business_snapshot():
    return ProductBusinessSnapshot(
        product_id="product-1",
        product_name="Premium Scene",
        product_type="story_product",
        delivery_type="PAID",
        availability=ProductBusinessAvailability.TELEGRAM_READY,
        product_health=ProductBusinessHealth.HEALTHY,
        next_business_recommendation=ProductBusinessRecommendation(
            label="No Product Business Action",
        ),
    )


def learning_context():
    return LearningContext(
        context_type="customer_learning",
        subject_reference="telegram-customer-1",
        learning_summary=LearningSummary(
            total_insights=1,
            total_recommendations=1,
        ),
        performance_snapshot=PerformanceSnapshot(
            metrics=(
                PerformanceMetric(
                    metric_name="Telegram conversion",
                    metric_type="telegram_business",
                    count=4,
                    success_count=3,
                    success_rate=0.75,
                ),
            ),
        ),
    )


def commerce_strategy_result():
    return CommerceStrategyResult(
        source_type="customer",
        source_id="telegram-customer-1",
        recommendations=(
            CommerceStrategyRecommendation(
                recommendation_type="offer_sequencing",
                source_type="customer",
                source_id="telegram-customer-1",
                recommended_objective="Sequence premium offer.",
                confidence=0.8,
            ),
        ),
        confidence=0.8,
    )


def telegram_commerce_result():
    delivery_decision = TelegramDeliveryDecision(
        offer_authorized=True,
        blocked=False,
        current_product_id="product-1",
        delivery_type="PAID",
        delivery_method="paid_media_link",
        paid_media_link="https://fanvue.example/media/product-1",
        requires_payment=True,
        next_suggested_action="deliver_paid_media_link",
    )
    conversation = TelegramConversationState(
        current_experience_id="experience-1",
        current_product_id="product-1",
        conversation_mode="experience",
        current_offer_id="offer-1",
        current_offer_kind="premium",
        commerce_state="paid_media_link_delivery",
        next_recommended_action="deliver_paid_media_link",
    )
    progression = TelegramExperienceProgression(
        current_experience_id="experience-1",
        experience_state="active",
        current_story_position="scene-2",
        current_product_id="product-1",
        progress_percentage=45,
        next_recommended_experience_action="continue_experience",
    )
    commerce_memory = TelegramCommerceMemory(
        paid_media_links_delivered=("https://fanvue.example/media/product-1",),
        previous_offers=("offer-1",),
        current_commerce_journey="offer_consideration",
        last_delivery={"delivery_method": "paid_media_link"},
    )
    state = TelegramCommerceState(
        current_experience_id="experience-1",
        current_product_id="product-1",
        conversation_state="experience",
        delivery_decision=delivery_decision,
        customer_progress=TelegramCustomerProgress(
            customer_id="telegram-customer-1",
            current_experience_id="experience-1",
            current_product_id="product-1",
            conversation_state="experience",
            commerce_state="paid_media_link_delivery",
        ),
        telegram_conversation_state=conversation,
        experience_progression=progression,
        commerce_memory=commerce_memory,
    )
    return TelegramCommerceResult(
        correlation_id="telegram:123456789:42",
        engine_user_id="7:-123456789",
        response_text="Here you go",
        decision_engine_result=None,
        delivery_decision=delivery_decision,
        customer_progress=state.customer_progress,
        state=state,
        conversation_state=conversation,
        experience_progression=progression,
        commerce_memory=commerce_memory,
        delivery_payload=TelegramDeliveryPayload(
            delivery_type="PAID",
            message_text="Here you go",
            media_link="https://fanvue.example/media/product-1",
            product_reference="product-1",
            experience_reference="experience-1",
            next_suggested_action="deliver_paid_media_link",
            delivery_method="paid_media_link",
        ),
    )


class TelegramBusinessServiceTests(unittest.TestCase):
    def build_service(self):
        learning = learning_context()
        return TelegramBusinessService(
            customer_intelligence_service=FakeCustomerIntelligenceService(
                customer_snapshot()
            ),
            product_business_service=FakeProductBusinessService(
                product_business_snapshot()
            ),
            business_learning_service=FakeBusinessLearningService(learning),
            commerce_strategy_service=ForbiddenCommerceStrategyService(),
            publishing_service=ForbiddenPublishingService(),
        )

    def test_builds_canonical_telegram_business_snapshot(self):
        service = self.build_service()

        snapshot = service.build_snapshot(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            product_business_snapshot=product_business_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            learning_context=learning_context(),
            publishing_status={
                "publishing_status": "PUBLISHING_COMPLETE",
                "media_link_status": "CREATED",
                "provider": "fanvue",
                "telegram_ready": True,
            },
        )

        self.assertIsInstance(snapshot, TelegramBusinessSnapshot)
        self.assertEqual(snapshot.provider, "telegram")
        self.assertEqual(snapshot.relationship_stage, "engaged")
        self.assertEqual(snapshot.conversation_state, "experience")
        self.assertEqual(snapshot.current_experience_id, "experience-1")
        self.assertEqual(snapshot.current_product_ids, ("product-1",))
        self.assertEqual(snapshot.summary.active_offer_ids, ("offer-1",))
        self.assertEqual(snapshot.delivery_history["delivery_count"], 3)
        self.assertEqual(snapshot.business_health, "LEARNING_READY")
        self.assertEqual(snapshot.operation_status, "READY")
        self.assertEqual(
            snapshot.next_recommended_business_action,
            "deliver_paid_media_link",
        )

    def test_aggregates_customer_product_commerce_publishing_and_learning(self):
        service = self.build_service()

        snapshot = service.build_snapshot(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            product_business_snapshot=product_business_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            learning_context=learning_context(),
            publishing_status={"publishing_status": "READY"},
        )

        self.assertEqual(
            snapshot.customer_identity["telegram_identifier"],
            "123456789",
        )
        self.assertEqual(snapshot.relationship["source"], "CustomerIntelligenceService")
        self.assertEqual(snapshot.products[0]["source"], "ProductBusinessService")
        self.assertEqual(
            snapshot.commerce_strategy["recommended_objectives"],
            ("Sequence premium offer.",),
        )
        self.assertEqual(snapshot.publishing["source"], "PublishingService")
        self.assertEqual(snapshot.business_learning["metric_count"], 1)
        self.assertEqual(
            snapshot.telegram_commerce["delivery_method"],
            "paid_media_link",
        )

    def test_can_build_missing_domain_context_without_breaking_compatibility(self):
        service = self.build_service()

        snapshot = service.build_snapshot(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            business_outcomes=({"outcome_type": "PRODUCT_OFFERED"},),
        )

        self.assertEqual(snapshot.customer_id, "telegram-customer-1")
        self.assertEqual(snapshot.current_product_ids, ("product-1",))
        self.assertTrue(snapshot.compatibility["sources_consumed"]["customer_snapshot"])
        self.assertTrue(snapshot.compatibility["sources_consumed"]["learning_context"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])

    def test_preserves_all_ownership_boundaries(self):
        service = self.build_service()

        snapshot = service.build_snapshot(
            customer_id="telegram-customer-1",
            telegram_commerce_result=telegram_commerce_result(),
            product_business_snapshot=product_business_snapshot(),
            commerce_strategy_result=commerce_strategy_result(),
            learning_context=learning_context(),
        )

        compatibility = snapshot.compatibility
        self.assertTrue(compatibility["read_only"])
        self.assertTrue(compatibility["aggregation_only"])
        self.assertFalse(compatibility["executes_telegram"])
        self.assertFalse(compatibility["sends_messages"])
        self.assertFalse(compatibility["publishes_products"])
        self.assertFalse(compatibility["records_business_learning"])
        self.assertFalse(compatibility["modifies_customer_intelligence"])
        self.assertFalse(compatibility["generates_commerce_strategy"])
        self.assertFalse(compatibility["generates_product_strategy"])
        self.assertFalse(compatibility["modifies_products"])
        self.assertEqual(
            compatibility["customer_intelligence_owner"],
            "CustomerIntelligenceService",
        )
        self.assertEqual(
            compatibility["commerce_strategy_owner"],
            "CommerceStrategyService",
        )
        self.assertEqual(
            compatibility["product_business_owner"],
            "ProductBusinessService",
        )
        self.assertEqual(compatibility["publishing_owner"], "PublishingService")
        self.assertEqual(
            compatibility["business_learning_owner"],
            "BusinessLearningService",
        )


if __name__ == "__main__":
    unittest.main()
