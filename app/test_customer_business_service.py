import unittest
from dataclasses import replace
from types import SimpleNamespace

from app.models.customer_business import (
    CustomerBusinessHealth,
    CustomerBusinessLifecycleStage,
    CustomerBusinessPriority,
    CustomerBusinessSnapshot,
    CustomerGrowthStage,
    CustomerRetentionRisk,
    CustomerValueTier,
    CustomerValueTrend,
    CustomerJourneyStage,
    CustomerJourneySummary,
)
from app.models.customer_intelligence import (
    CustomerCommerceMemory,
    CustomerExperienceProgress,
    CustomerIdentity,
    CustomerIntelligenceSnapshot,
    CustomerProfile,
    CustomerRelationshipStage,
)
from app.services.customer_business_service import CustomerBusinessService


class CustomerBusinessServiceTests(unittest.TestCase):
    def test_snapshot_can_be_created_with_minimal_customer_data(self):
        snapshot = CustomerBusinessService().build_snapshot(customer_id="7:42")

        self.assertIsInstance(snapshot, CustomerBusinessSnapshot)
        self.assertEqual(snapshot.customer_id, "7:42")
        self.assertEqual(snapshot.provider, "provider_neutral")
        self.assertEqual(snapshot.summary.customer_id, "7:42")
        self.assertIsInstance(snapshot.current_journey, CustomerJourneySummary)
        self.assertEqual(snapshot.journey_stage, CustomerJourneyStage.NEW_CUSTOMER)
        self.assertEqual(snapshot.value_tier, CustomerValueTier.NEW)
        self.assertEqual(snapshot.retention_summary.risk, CustomerRetentionRisk.MONITOR)
        self.assertEqual(snapshot.growth_stage, CustomerGrowthStage.EARLY_RELATIONSHIP)
        self.assertEqual(snapshot.next_recommended_action, "Continue relationship")
        self.assertTrue(snapshot.compatibility["read_only"])
        self.assertTrue(snapshot.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])

    def test_customer_health_is_derived_deterministically(self):
        service = CustomerBusinessService()
        base = service.build_snapshot(
            customer_id="vip-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.VIP,
                purchases=3,
            ),
        )
        dormant = service.build_snapshot(
            customer_id="dormant-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.DORMANT,
            ),
        )

        self.assertEqual(base.customer_health, CustomerBusinessHealth.VIP)
        self.assertEqual(dormant.customer_health, CustomerBusinessHealth.DORMANT)
        self.assertEqual(base.customer_health, service.build_snapshot(
            customer_id="vip-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.VIP,
                purchases=3,
            ),
        ).customer_health)

    def test_lifecycle_stage_is_derived_without_owning_customer_intelligence(self):
        customer_snapshot = self._customer_snapshot(
            relationship_stage=CustomerRelationshipStage.PURCHASER,
            purchases=1,
        )

        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="buyer-1",
            customer_snapshot=customer_snapshot,
        )

        self.assertEqual(
            snapshot.lifecycle_stage,
            CustomerBusinessLifecycleStage.CUSTOMER,
        )
        self.assertTrue(snapshot.compatibility["modifies_customer_intelligence"] is False)
        self.assertEqual(
            customer_snapshot.relationship_stage,
            CustomerRelationshipStage.PURCHASER,
        )

    def test_opportunities_are_generated_from_sales_delivery_and_relationship_signals(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="opportunity-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            sales_management=SimpleNamespace(
                active_offer_ids=("offer-1",),
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_BUNDLE",
                    priority="HIGH",
                    confidence=0.82,
                    recommended_next_action="Offer Bundle",
                ),
            ),
            delivery_management=SimpleNamespace(
                delivery_history={"delivery_count": 1},
                recommendation=SimpleNamespace(
                    recommendation_type="SEND_MEDIA_LINK",
                    priority="NORMAL",
                    confidence=0.7,
                    recommended_next_action="Send Media Link",
                ),
            ),
            relationship_management=SimpleNamespace(
                relationship_health="HEALTHY",
                recommendation=SimpleNamespace(
                    recommendation_type="CONTINUE_RELATIONSHIP",
                    priority="NORMAL",
                    confidence=0.62,
                    recommended_next_action="Continue Relationship",
                ),
            ),
        )

        opportunity_types = {item.opportunity_type for item in snapshot.opportunities}

        self.assertIn("sales", opportunity_types)
        self.assertIn("delivery", opportunity_types)
        self.assertIn("relationship", opportunity_types)
        self.assertEqual(snapshot.opportunities[0].source, "CustomerBusinessService")

    def test_recommendations_are_advisory_only(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="sales-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            sales_management=SimpleNamespace(
                active_offer_ids=("offer-1",),
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_PREMIUM_PRODUCT",
                    priority="HIGH",
                    confidence=0.76,
                    recommended_next_action="Offer Premium Product",
                ),
            ),
        )

        recommendation = snapshot.recommendations[0]

        self.assertEqual(recommendation.recommendation_type, "SALES")
        self.assertEqual(recommendation.priority, CustomerBusinessPriority.HIGH)
        self.assertEqual(
            recommendation.recommended_next_action,
            "Offer Premium Product",
        )
        self.assertTrue(recommendation.metadata["advisory_only"])
        self.assertTrue(recommendation.metadata["read_only"])

    def test_missing_upstream_services_do_not_break_snapshot_generation(self):
        snapshot = CustomerBusinessService(
            customer_service=None,
            telegram_business_service=None,
            product_business_service=None,
            commerce_strategy_service=None,
            business_learning_service=None,
            relationship_management_service=None,
            sales_management_service=None,
            delivery_management_service=None,
        ).build_snapshot()

        self.assertIsInstance(snapshot, CustomerBusinessSnapshot)
        self.assertEqual(snapshot.lifecycle_stage, CustomerBusinessLifecycleStage.NEW)
        self.assertEqual(snapshot.summary.next_recommended_action, "Continue relationship")
        self.assertFalse(snapshot.compatibility["sources_consumed"]["telegram_business_snapshot"])

    def test_customer_business_does_not_mutate_upstream_domain_objects(self):
        customer_snapshot = self._customer_snapshot(
            relationship_stage=CustomerRelationshipStage.ACTIVE,
            purchases=0,
        )
        original = replace(customer_snapshot)
        sales_management = SimpleNamespace(
            active_offer_ids=["offer-1"],
            recommendation=SimpleNamespace(
                recommendation_type="OFFER_FREE_PRODUCT",
                priority="NORMAL",
                confidence=0.61,
                recommended_next_action="Offer FREE Product",
            ),
        )
        original_offer_ids = list(sales_management.active_offer_ids)

        CustomerBusinessService().build_snapshot(
            customer_id="stable-1",
            customer_snapshot=customer_snapshot,
            sales_management=sales_management,
        )

        self.assertEqual(customer_snapshot, original)
        self.assertEqual(sales_management.active_offer_ids, original_offer_ids)

    def test_existing_architecture_remains_provider_neutral(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="telegram-1",
            provider="telegram",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            telegram_business_snapshot=SimpleNamespace(
                provider="telegram",
                business_health="HEALTHY",
                summary={
                    "relationship_stage": "active",
                    "current_product_ids": ("product-1",),
                    "active_offer_ids": ("offer-1",),
                    "next_recommended_action": "Continue Conversation",
                },
            ),
        )

        self.assertEqual(snapshot.provider, "provider_neutral")
        self.assertEqual(snapshot.summary.provider, "provider_neutral")
        self.assertEqual(snapshot.telegram_business["provider"], "telegram")
        self.assertEqual(
            snapshot.compatibility["telegram_business_owner"],
            "TelegramBusinessService",
        )
        self.assertTrue(snapshot.customer_value.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])

    def test_business_learning_evidence_is_consumed_without_recording(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="learning-1",
            business_learning_context=SimpleNamespace(
                context_type="customer_learning",
            ),
            business_learning_snapshot=SimpleNamespace(
                summary={
                    "total_outcomes": 2,
                    "total_recommendations": 1,
                },
            ),
        )

        self.assertTrue(snapshot.business_learning_evidence["available"])
        self.assertEqual(
            snapshot.business_learning_evidence["context_type"],
            "customer_learning",
        )
        self.assertFalse(snapshot.compatibility["records_business_learning"])

    def test_customer_value_generation_with_minimal_data(self):
        snapshot = CustomerBusinessService().build_snapshot(customer_id="value-1")

        self.assertEqual(snapshot.customer_value.tier, CustomerValueTier.NEW)
        self.assertEqual(snapshot.value_trend, CustomerValueTrend.NEW)
        self.assertTrue(snapshot.value_signals)
        self.assertEqual(snapshot.purchase_potential, "unknown")
        self.assertFalse(snapshot.vip_potential)
        self.assertEqual(snapshot.retention_risk, "low")
        self.assertEqual(
            snapshot.customer_value.recommendations[0].recommended_next_action,
            "Build relationship",
        )

    def test_value_tier_derivation(self):
        buyer = CustomerBusinessService().build_snapshot(
            customer_id="buyer-value-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.PURCHASER,
                purchases=1,
            ),
        )
        repeat = CustomerBusinessService().build_snapshot(
            customer_id="repeat-value-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                purchases=2,
            ),
        )

        self.assertEqual(buyer.value_tier, CustomerValueTier.BUYER)
        self.assertEqual(repeat.value_tier, CustomerValueTier.REPEAT_BUYER)
        self.assertEqual(repeat.purchase_potential, "high")

    def test_vip_potential_detection(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="vip-potential-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                purchases=3,
            ),
            relationship_management=SimpleNamespace(
                relationship_health="VIP_OPPORTUNITY",
                recommendation=SimpleNamespace(
                    recommendation_type="VIP_OPPORTUNITY",
                    priority="HIGH",
                    confidence=0.77,
                    recommended_next_action="VIP Opportunity",
                ),
            ),
            business_learning_context=SimpleNamespace(
                context_type="customer_learning",
            ),
        )

        self.assertTrue(snapshot.vip_potential)
        self.assertIn(
            snapshot.value_tier,
            {CustomerValueTier.VIP_POTENTIAL, CustomerValueTier.VIP},
        )
        self.assertEqual(
            snapshot.customer_value.recommendations[0].recommendation_type,
            "NURTURE_VIP_POTENTIAL",
        )

    def test_retention_risk_detection(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="risk-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.DORMANT,
            ),
        )

        self.assertEqual(snapshot.value_tier, CustomerValueTier.DORMANT)
        self.assertEqual(snapshot.value_trend, CustomerValueTrend.DORMANT)
        self.assertEqual(snapshot.retention_risk, "high")
        self.assertEqual(
            snapshot.customer_value.recommendations[0].recommended_next_action,
            "Re-engage dormant customer",
        )

    def test_growth_opportunity_generation(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="growth-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            telegram_business_snapshot=SimpleNamespace(
                summary={
                    "current_product_ids": ("product-1",),
                    "active_offer_ids": ("offer-1",),
                },
                business_health="HEALTHY",
            ),
            sales_management=SimpleNamespace(
                active_offer_ids=("offer-1",),
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_BUNDLE",
                    priority="HIGH",
                    confidence=0.82,
                    recommended_next_action="Recommend bundle",
                ),
            ),
        )

        self.assertIn("purchase_growth", snapshot.customer_value.growth_opportunities)
        self.assertIn("sales_follow_up", snapshot.customer_value.growth_opportunities)
        self.assertIn("product_discovery", snapshot.customer_value.growth_opportunities)
        self.assertIn("offer_conversion", snapshot.customer_value.growth_opportunities)

    def test_value_recommendations_follow_aggregated_signals(self):
        bundle = CustomerBusinessService().build_snapshot(
            customer_id="bundle-value-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            sales_management=SimpleNamespace(
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_BUNDLE",
                    priority="HIGH",
                    confidence=0.79,
                    recommended_next_action="Recommend bundle",
                ),
            ),
        )
        preview = CustomerBusinessService().build_snapshot(
            customer_id="preview-value-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            telegram_business_snapshot=SimpleNamespace(
                summary={"current_product_ids": ("product-1",)},
            ),
        )

        self.assertEqual(
            bundle.customer_value.recommendations[0].recommendation_type,
            "RECOMMEND_BUNDLE",
        )
        self.assertEqual(
            preview.customer_value.recommendations[0].recommendation_type,
            "OFFER_FREE_PREVIEW",
        )

    def test_customer_value_handles_missing_upstream_services(self):
        snapshot = CustomerBusinessService(
            customer_service=None,
            telegram_business_service=None,
            product_business_service=None,
            commerce_strategy_service=None,
            business_learning_service=None,
        ).build_snapshot(customer_id="missing-value")

        self.assertEqual(snapshot.value_tier, CustomerValueTier.NEW)
        self.assertEqual(snapshot.customer_value.recommendations[0].source, "CustomerBusinessService")
        self.assertTrue(snapshot.customer_value.compatibility["aggregation_only"])

    def test_retention_summary_generation(self):
        snapshot = CustomerBusinessService().build_snapshot(customer_id="retention-1")

        self.assertEqual(snapshot.retention_summary.risk, CustomerRetentionRisk.MONITOR)
        self.assertTrue(snapshot.retention_signals)
        self.assertTrue(snapshot.retention_opportunities)
        self.assertEqual(
            snapshot.recommended_follow_up,
            "Continue relationship building",
        )
        self.assertGreaterEqual(snapshot.retention_confidence, 0.0)

    def test_retention_risk_derivation(self):
        dormant = CustomerBusinessService().build_snapshot(
            customer_id="retention-dormant-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.DORMANT,
            ),
        )
        at_risk = CustomerBusinessService().build_snapshot(
            customer_id="retention-risk-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            relationship_management=SimpleNamespace(
                relationship_health="AT_RISK",
                recommendation=SimpleNamespace(
                    recommendation_type="FOLLOW_UP",
                    priority="HIGH",
                    confidence=0.67,
                    recommended_next_action="Recommend follow-up",
                ),
            ),
        )

        self.assertEqual(dormant.retention_summary.risk, CustomerRetentionRisk.DORMANT)
        self.assertEqual(at_risk.retention_summary.risk, CustomerRetentionRisk.AT_RISK)

    def test_re_engagement_readiness(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="reengage-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.DORMANT,
            ),
        )

        self.assertEqual(snapshot.re_engagement_readiness, "ready")
        self.assertEqual(
            snapshot.retention_summary.recommendations[0].recommendation_type,
            "RE_ENGAGE_CUSTOMER",
        )

    def test_follow_up_recommendation_generation(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="follow-up-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            relationship_management=SimpleNamespace(
                relationship_health="DISENGAGED",
                recommendation=SimpleNamespace(
                    recommendation_type="FOLLOW_UP",
                    priority="HIGH",
                    confidence=0.7,
                    recommended_next_action="Recommend follow-up",
                ),
            ),
        )

        self.assertEqual(
            snapshot.retention_summary.recommended_follow_up,
            "Recommend follow-up",
        )
        self.assertEqual(
            snapshot.retention_summary.recommendations[0].recommendation_type,
            "RECOMMEND_FOLLOW_UP",
        )

    def test_retention_opportunity_generation(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="retention-opportunity-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
                current_experience_id="experience-1",
            ),
            sales_management=SimpleNamespace(
                recommendation=SimpleNamespace(
                    recommendation_type="DELAY_SELLING",
                    priority="NORMAL",
                    confidence=0.6,
                    recommended_next_action="Delay Selling",
                ),
            ),
        )

        opportunity_types = {
            opportunity.opportunity_type
            for opportunity in snapshot.retention_opportunities
        }

        self.assertIn("cooling_off", opportunity_types)
        self.assertIn("experience_resume", opportunity_types)
        self.assertEqual(snapshot.retention_summary.risk, CustomerRetentionRisk.COOLING_OFF)

    def test_retention_handles_missing_upstream_services(self):
        snapshot = CustomerBusinessService(
            customer_service=None,
            telegram_business_service=None,
            business_learning_service=None,
        ).build_snapshot(customer_id="missing-retention")

        self.assertEqual(snapshot.retention_summary.risk, CustomerRetentionRisk.MONITOR)
        self.assertTrue(snapshot.retention_summary.compatibility["provider_neutral"])
        self.assertTrue(snapshot.retention_summary.compatibility["aggregation_only"])

    def test_retention_preserves_provider_neutrality(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="telegram-retention-1",
            provider="telegram",
            telegram_business_snapshot=SimpleNamespace(
                provider="telegram",
                business_health="HEALTHY",
                operation_status="ACTIVE",
            ),
        )

        self.assertEqual(snapshot.provider, "provider_neutral")
        self.assertTrue(snapshot.retention_summary.compatibility["provider_neutral"])
        self.assertEqual(
            snapshot.retention_summary.compatibility["telegram_business_owner"],
            "TelegramBusinessService",
        )

    def test_growth_summary_generation(self):
        snapshot = CustomerBusinessService().build_snapshot(customer_id="growth-summary-1")

        self.assertEqual(snapshot.growth_summary.stage, CustomerGrowthStage.EARLY_RELATIONSHIP)
        self.assertTrue(snapshot.growth_signals)
        self.assertTrue(snapshot.growth_opportunities)
        self.assertEqual(snapshot.recommended_growth_action, "Introduce next Experience")
        self.assertGreaterEqual(snapshot.growth_confidence, 0.0)

    def test_growth_stage_derivation(self):
        repeat = CustomerBusinessService().build_snapshot(
            customer_id="growth-repeat-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                purchases=2,
            ),
        )
        vip = CustomerBusinessService().build_snapshot(
            customer_id="growth-vip-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.VIP,
                purchases=4,
            ),
        )

        self.assertEqual(repeat.growth_stage, CustomerGrowthStage.REPEAT_BUYER)
        self.assertEqual(vip.growth_stage, CustomerGrowthStage.MATURE_CUSTOMER)

    def test_upsell_readiness(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="growth-upsell-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.PURCHASER,
                purchases=1,
            ),
            sales_management=SimpleNamespace(
                recommendation=SimpleNamespace(
                    recommendation_type="UPSELL",
                    priority="HIGH",
                    confidence=0.8,
                    recommended_next_action="Upsell premium offering",
                ),
            ),
        )

        self.assertEqual(snapshot.upsell_readiness, "ready")
        self.assertEqual(
            snapshot.growth_summary.recommendations[0].recommendation_type,
            "UPSELL_PREMIUM_OFFERING",
        )

    def test_cross_sell_readiness(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="growth-cross-sell-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            product_business_snapshots=(
                SimpleNamespace(product_id="product-1"),
                SimpleNamespace(product_id="product-2"),
            ),
            telegram_business_snapshot=SimpleNamespace(
                summary={"current_product_ids": ("product-1", "product-2")},
            ),
            sales_management=SimpleNamespace(
                recommendation=SimpleNamespace(
                    recommendation_type="CROSS_SELL",
                    priority="HIGH",
                    confidence=0.74,
                    recommended_next_action="Cross-sell related Products",
                ),
            ),
        )

        self.assertEqual(snapshot.cross_sell_readiness, "ready")
        self.assertEqual(
            snapshot.growth_summary.recommendations[0].recommendation_type,
            "CROSS_SELL_RELATED_PRODUCTS",
        )

    def test_vip_growth_readiness(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="growth-vip-ready-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                purchases=3,
            ),
            relationship_management=SimpleNamespace(
                relationship_health="VIP_OPPORTUNITY",
                recommendation=SimpleNamespace(
                    recommendation_type="VIP_OPPORTUNITY",
                    priority="HIGH",
                    confidence=0.8,
                    recommended_next_action="Develop VIP relationship",
                ),
            ),
        )

        self.assertEqual(snapshot.vip_growth_readiness, "ready")
        self.assertEqual(snapshot.growth_stage, CustomerGrowthStage.MATURE_CUSTOMER)
        self.assertEqual(
            snapshot.growth_summary.recommendations[0].recommended_next_action,
            "Develop VIP relationship",
        )

    def test_growth_recommendation_generation_for_bundle(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="growth-bundle-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            sales_management=SimpleNamespace(
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_BUNDLE",
                    priority="HIGH",
                    confidence=0.82,
                    recommended_next_action="Recommend bundle",
                ),
            ),
        )

        self.assertEqual(
            snapshot.growth_summary.recommendations[0].recommendation_type,
            "RECOMMEND_BUNDLE",
        )

    def test_growth_handles_missing_upstream_services(self):
        snapshot = CustomerBusinessService(
            customer_service=None,
            product_business_service=None,
            commerce_strategy_service=None,
            business_learning_service=None,
        ).build_snapshot(customer_id="missing-growth")

        self.assertEqual(snapshot.growth_stage, CustomerGrowthStage.EARLY_RELATIONSHIP)
        self.assertTrue(snapshot.growth_summary.compatibility["aggregation_only"])
        self.assertEqual(snapshot.expansion_readiness, "not_ready")

    def test_growth_preserves_provider_neutrality(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="telegram-growth-1",
            provider="telegram",
            telegram_business_snapshot=SimpleNamespace(
                provider="telegram",
                business_health="HEALTHY",
            ),
        )

        self.assertEqual(snapshot.provider, "provider_neutral")
        self.assertTrue(snapshot.growth_summary.compatibility["provider_neutral"])
        self.assertEqual(
            snapshot.growth_summary.compatibility["product_business_owner"],
            "ProductBusinessService",
        )

    def test_journey_generation_with_minimal_data(self):
        snapshot = CustomerBusinessService().build_snapshot(customer_id="journey-1")

        self.assertEqual(snapshot.current_journey.stage, CustomerJourneyStage.NEW_CUSTOMER)
        self.assertEqual(snapshot.current_journey.progress.total_count, 8)
        self.assertGreaterEqual(snapshot.current_journey.confidence, 0.0)
        self.assertEqual(
            snapshot.current_journey.recommendations[0].recommended_next_action,
            "Continue relationship",
        )

    def test_journey_stage_derivation_for_repeat_buyer_and_vip_growth(self):
        repeat = CustomerBusinessService().build_snapshot(
            customer_id="repeat-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.REPEAT_PURCHASER,
                purchases=2,
            ),
        )
        vip = CustomerBusinessService().build_snapshot(
            customer_id="vip-journey-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.VIP,
                purchases=3,
            ),
        )

        self.assertEqual(repeat.journey_stage, CustomerJourneyStage.REPEAT_BUYER)
        self.assertEqual(vip.journey_stage, CustomerJourneyStage.VIP_GROWTH)

    def test_journey_milestone_progression(self):
        snapshot = CustomerBusinessService().build_snapshot(
            customer_id="milestone-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            telegram_business_snapshot=SimpleNamespace(
                summary={
                    "current_product_ids": ("product-1",),
                    "active_offer_ids": ("offer-1",),
                },
            ),
        )

        completed_ids = {
            milestone.milestone_id
            for milestone in snapshot.completed_milestones
        }

        self.assertIn("identity_known", completed_ids)
        self.assertIn("relationship_started", completed_ids)
        self.assertIn("product_discovered", completed_ids)
        self.assertIn("offer_presented", completed_ids)
        self.assertEqual(snapshot.next_milestone.milestone_id, "experience_started")

    def test_journey_recommendations_are_derived_from_sales_and_experience(self):
        sales_snapshot = CustomerBusinessService().build_snapshot(
            customer_id="journey-sales-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
            ),
            sales_management=SimpleNamespace(
                active_offer_ids=("offer-1",),
                recommendation=SimpleNamespace(
                    recommendation_type="OFFER_FREE_PRODUCT",
                    priority="NORMAL",
                    confidence=0.71,
                    recommended_next_action="Recommend FREE preview",
                ),
            ),
        )
        experience_snapshot = CustomerBusinessService().build_snapshot(
            customer_id="journey-experience-1",
            customer_snapshot=self._customer_snapshot(
                relationship_stage=CustomerRelationshipStage.ACTIVE,
                current_experience_id="experience-1",
                next_experience_action="Continue current Experience",
            ),
        )

        self.assertEqual(
            sales_snapshot.current_journey.recommendations[0].recommendation_type,
            "RECOMMEND_FREE_PREVIEW",
        )
        self.assertEqual(
            experience_snapshot.current_journey.recommendations[0].recommendation_type,
            "CONTINUE_CURRENT_EXPERIENCE",
        )
        self.assertEqual(
            experience_snapshot.recommended_next_experience,
            "Continue current Experience",
        )

    def test_journey_handles_missing_upstream_services_gracefully(self):
        snapshot = CustomerBusinessService(
            customer_service=None,
            telegram_business_service=None,
            product_business_service=None,
            commerce_strategy_service=None,
            business_learning_service=None,
        ).build_snapshot(customer_id="missing-journey")

        self.assertEqual(snapshot.journey_stage, CustomerJourneyStage.NEW_CUSTOMER)
        self.assertEqual(
            snapshot.current_journey.recommendations[0].recommendation_type,
            "CONTINUE_RELATIONSHIP",
        )
        self.assertTrue(snapshot.current_journey.compatibility["aggregation_only"])

    @staticmethod
    def _customer_snapshot(
        *,
        relationship_stage: CustomerRelationshipStage,
        purchases: int = 0,
        current_experience_id: str | None = None,
        next_experience_action: str | None = None,
    ) -> CustomerIntelligenceSnapshot:
        products = tuple(f"product-{index}" for index in range(purchases))
        return CustomerIntelligenceSnapshot(
            identity=CustomerIdentity(
                canonical_customer_id="customer-1",
                customer_id="customer-1",
                provider="telegram",
                provider_customer_id="42",
            ),
            profile=CustomerProfile(display_name="Customer One"),
            relationship_stage=relationship_stage,
            commerce_memory=CustomerCommerceMemory(
                products_purchased=products,
                customer_spending_summary={
                    "purchase_count": purchases,
                    "total_spend_cents": purchases * 1999,
                },
            ),
            experience_progress=CustomerExperienceProgress(
                current_experience_id=current_experience_id,
                metadata={"next_recommended_experience_action": next_experience_action}
                if next_experience_action
                else {},
            ),
        )


if __name__ == "__main__":
    unittest.main()
