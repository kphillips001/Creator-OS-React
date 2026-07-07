import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from app.models.content_opportunity import (
    ContentDemandTrend,
    ContentOpportunityHealth,
    ContentOpportunityFollowUpPriority,
    ContentOpportunityFollowUpStatus,
    ContentOpportunityPriority,
    ContentOpportunityRecommendationPriority,
    ContentOpportunityRecommendationType,
    ContentOpportunityResolutionSource,
    ContentOpportunityResolutionStatus,
    ContentOpportunitySource,
    ContentOpportunityStatus,
    ContentRequestMatch,
)
from app.repositories.content_opportunity_repository import ContentOpportunityRepository
from app.services.content_opportunity_runtime_ingestion_service import (
    ContentOpportunityRuntimeIngestionService,
)
from app.services.content_opportunity_service import ContentOpportunityService


class ContentOpportunityServiceTests(unittest.TestCase):
    def test_durable_records_survive_service_recreation(self) -> None:
        with TemporaryDirectory() as directory:
            repository = ContentOpportunityRepository(
                f"{directory}/content_opportunities.json"
            )
            service = ContentOpportunityService(
                content_opportunity_repository=repository
            )
            service.resolve_content_request(
                customer_id="customer-1",
                provider="telegram",
                provider_customer_id="tg-1",
                request_text="Do you have shower videos?",
                normalized_terms=("shower", "video"),
            )
            service.resolve_content_request(
                customer_id="customer-2",
                provider="telegram",
                request_text="Do you have beach photos?",
                normalized_terms=("beach", "photos"),
                product_candidates=(
                    {"id": "product-beach", "name": "Beach Photos", "tags": ("beach", "photos")},
                ),
            )
            resolution = service.resolve_opportunities_for_product(
                {"id": "product-shower", "name": "Shower Videos", "tags": ("shower", "video")}
            )[0]
            service.create_follow_up_opportunities(resolution)

            recreated = ContentOpportunityService(
                content_opportunity_repository=repository
            )
            snapshot = recreated.build_snapshot()

            self.assertEqual(snapshot.total_requests, 2)
            self.assertEqual(snapshot.matched_count, 1)
            self.assertEqual(snapshot.unmatched_count, 1)
            self.assertEqual(snapshot.resolution_ready_count, 1)
            self.assertEqual(snapshot.ready_follow_up_count, 1)
            self.assertTrue(snapshot.compatibility["durable_persistence"])

    def test_runtime_ingestion_records_unmatched_request_with_safe_guidance(self) -> None:
        service = ContentOpportunityService()
        ingestion = ContentOpportunityRuntimeIngestionService(
            content_opportunity_service=service
        )

        result = ingestion.ingest_message(
            customer_id="customer-1",
            provider_customer_id="tg-1",
            message_text="Do you have shower videos?",
        )

        self.assertTrue(result.detected)
        self.assertTrue(result.recorded)
        self.assertEqual(result.opportunity.status, ContentOpportunityStatus.UNMATCHED)
        self.assertIn(
            "I don't currently have that available",
            result.safe_response_guidance["soft_response_suggestion"],
        )
        self.assertTrue(
            result.safe_response_guidance["must_not_promise_future_content"]
        )
        self.assertEqual(service.build_snapshot().unmatched_count, 1)

    def test_runtime_ingestion_records_matched_request_when_existing_product_matches(self) -> None:
        class ProductCatalog:
            def list_workspace_display_models(self, creator_profile_id):
                return (
                    {
                        "id": "product-beach",
                        "name": "Beach Photo Set",
                        "tags": ("beach", "photo"),
                        "publishing": {"status": "READY"},
                    },
                )

        service = ContentOpportunityService(product_catalog_service=ProductCatalog())
        ingestion = ContentOpportunityRuntimeIngestionService(
            content_opportunity_service=service
        )

        result = ingestion.ingest_message(
            customer_id="customer-1",
            message_text="Do you have beach photos?",
            creator_profile_id=7,
        )

        self.assertTrue(result.recorded)
        self.assertEqual(result.opportunity.status, ContentOpportunityStatus.MATCHED)
        self.assertEqual(result.opportunity.product_ids, ("product-beach",))
        self.assertEqual(service.build_snapshot().matched_count, 1)

    def test_new_product_availability_resolves_and_creates_follow_ups(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            provider="telegram",
            provider_customer_id="tg-1",
            request_text="Any gym videos?",
            normalized_terms=("gym", "video"),
        )

        follow_ups = service.record_new_product_available(
            {"id": "product-gym", "name": "Gym Video", "tags": ("gym", "video")}
        )

        self.assertEqual(len(follow_ups), 1)
        self.assertEqual(follow_ups[0].customer_id, "customer-1")
        self.assertTrue(follow_ups[0].safe_guidance["must_not_contact_customer_automatically"])
        self.assertFalse(follow_ups[0].metadata["executes_telegram"])
        self.assertEqual(service.build_snapshot().waiting_customer_count, 2)

    def test_follow_up_opportunities_created_for_waiting_customers(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            provider="telegram",
            provider_customer_id="tg-1",
            request_text="Shower video",
            normalized_terms=("shower", "video"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-shower", "display_name": "Shower video"}
        )[0]

        follow_ups = service.create_follow_up_opportunities(resolution)

        self.assertEqual(len(follow_ups), 1)
        self.assertEqual(follow_ups[0].resolution_id, resolution.resolution_id)
        self.assertEqual(follow_ups[0].customer_id, "customer-1")
        self.assertEqual(follow_ups[0].provider, "telegram")
        self.assertEqual(follow_ups[0].provider_customer_id, "tg-1")
        self.assertEqual(follow_ups[0].matched_product_ids, ("product-shower",))
        self.assertEqual(follow_ups[0].status, ContentOpportunityFollowUpStatus.READY)

    def test_one_follow_up_created_per_waiting_customer(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin pictures",
            normalized_terms=("photos", "cabin"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-cabin", "display_name": "Cabin photos"}
        )[0]

        first = service.create_follow_up_opportunities(resolution)
        second = service.create_follow_up_opportunities(resolution)

        self.assertEqual(len(first), 2)
        self.assertEqual(len(second), 2)
        self.assertEqual(len(service.list_ready_follow_ups()), 2)
        self.assertEqual(
            tuple(item.customer_id for item in service.list_ready_follow_ups()),
            ("customer-1", "customer-2"),
        )

    def test_vip_follow_ups_receive_higher_priority(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Travel story",
            normalized_terms=("travel", "story"),
            is_vip=True,
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Travel story",
            normalized_terms=("story", "travel"),
        )
        resolution = service.resolve_opportunities_for_experience(
            {"experience_id": "experience-travel", "title": "Travel story"}
        )[0]

        follow_ups = service.create_follow_up_opportunities(resolution)
        vip = next(item for item in follow_ups if item.customer_id == "vip-1")
        normal = next(item for item in follow_ups if item.customer_id == "customer-2")

        self.assertEqual(vip.priority, ContentOpportunityFollowUpPriority.CRITICAL)
        self.assertIn(
            normal.priority,
            {
                ContentOpportunityFollowUpPriority.NORMAL,
                ContentOpportunityFollowUpPriority.HIGH,
            },
        )

    def test_pending_and_ready_follow_ups_list_correctly(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-beach", "display_name": "Beach photos"}
        )[0]

        pending = service.create_follow_up_opportunities(
            resolution,
            status=ContentOpportunityFollowUpStatus.PENDING,
        )

        self.assertEqual(service.list_pending_follow_ups(), pending)
        self.assertEqual(service.list_ready_follow_ups(), ())

        ready = service.create_follow_up_for_customer(
            resolution=resolution,
            waiting_customer=resolution.evidence["waiting_customers"][0],
            status=ContentOpportunityFollowUpStatus.READY,
        )

        self.assertEqual(service.list_pending_follow_ups(), ())
        self.assertEqual(service.list_ready_follow_ups(), (ready,))

    def test_follow_up_lifecycle_transitions_work(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
        )
        resolution = service.resolve_opportunities_for_asset(
            {"asset_id": "asset-gym", "keywords": ("gym", "photos")}
        )[0]
        follow_up = service.create_follow_up_opportunities(resolution)[0]

        completed = service.complete_follow_up(follow_up.follow_up_id)

        self.assertEqual(completed.status, ContentOpportunityFollowUpStatus.COMPLETED)
        self.assertIsNotNone(completed.completed_at)
        self.assertEqual(service.list_ready_follow_ups(), ())

    def test_ignored_and_expired_follow_ups_excluded_from_ready_list(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Beach pictures",
            normalized_terms=("photos", "beach"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-beach", "display_name": "Beach photos"}
        )[0]
        first, second = service.create_follow_up_opportunities(resolution)

        ignored = service.ignore_follow_up(first.follow_up_id)
        expired = service.expire_follow_up(second.follow_up_id)

        self.assertEqual(ignored.status, ContentOpportunityFollowUpStatus.IGNORED)
        self.assertEqual(expired.status, ContentOpportunityFollowUpStatus.EXPIRED)
        self.assertEqual(service.list_ready_follow_ups(), ())

    def test_follow_up_guidance_contains_no_promise_language(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Cosplay video",
            normalized_terms=("cosplay", "video"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-cosplay", "display_name": "Cosplay video"}
        )[0]
        follow_up = service.create_follow_up_opportunities(resolution)[0]
        text = " ".join(str(value).lower() for value in follow_up.safe_guidance.values())

        for forbidden in (
            "created specifically",
            "promised",
            "automatic customer notification",
            "guaranteed",
        ):
            self.assertNotIn(forbidden, text)
        self.assertTrue(follow_up.safe_guidance["must_not_contact_customer_automatically"])
        self.assertTrue(follow_up.safe_guidance["must_not_imply_content_was_custom_made"])

    def test_follow_up_does_not_mutate_products_customers_or_runtime(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        product = {"id": "product-beach", "display_name": "Beach photos", "markers": ["original"]}
        customer_intelligence = {"customer_id": "customer-1", "markers": ["original"]}
        service.customer_intelligence_service = SimpleNamespace(customer=customer_intelligence)

        resolution = service.resolve_opportunities_for_product(product)[0]
        follow_up = service.create_follow_up_opportunities(resolution)[0]

        self.assertEqual(product["markers"], ["original"])
        self.assertEqual(customer_intelligence["markers"], ["original"])
        self.assertFalse(follow_up.metadata["modifies_products"])
        self.assertFalse(follow_up.metadata["modifies_customer_intelligence"])
        self.assertFalse(follow_up.metadata["executes_telegram"])
        self.assertFalse(follow_up.metadata["changes_decision_engine_behavior"])

    def test_follow_up_snapshot_counts_are_exposed(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-beach", "display_name": "Beach photos"}
        )[0]
        service.create_follow_up_opportunities(resolution)

        snapshot = service.build_snapshot()

        self.assertEqual(snapshot.ready_follow_up_count, 1)
        self.assertEqual(snapshot.pending_follow_up_count, 0)
        self.assertEqual(len(snapshot.follow_up_opportunities), 1)
        self.assertEqual(snapshot.summary["ready_follow_up_count"], 1)

    def test_newly_matched_product_resolves_previous_unmatched_opportunity(self) -> None:
        service = ContentOpportunityService()
        opportunity = service.resolve_content_request(
            customer_id="customer-1",
            provider_customer_id="telegram-1",
            request_text="Shower video",
            normalized_terms=("shower", "video"),
            requested_format="video",
        )

        resolutions = service.resolve_opportunities_for_product(
            {
                "id": "product-shower-video",
                "display_name": "Shower video",
                "tags": ("shower",),
                "keywords": ("video",),
                "status": "ACTIVE",
            }
        )

        self.assertEqual(len(resolutions), 1)
        resolution = resolutions[0]
        self.assertEqual(resolution.opportunity_id, opportunity.opportunity_id)
        self.assertEqual(resolution.status, ContentOpportunityResolutionStatus.RESOLUTION_READY)
        self.assertEqual(resolution.source, ContentOpportunityResolutionSource.PRODUCT)
        self.assertEqual(resolution.matched_product_ids, ("product-shower-video",))
        self.assertEqual(resolution.waiting_customer_ids, ("customer-1",))
        self.assertEqual(resolution.waiting_provider_customer_ids, ("telegram-1",))
        self.assertGreaterEqual(resolution.confidence, 0.5)

    def test_newly_matched_experience_resolves_previous_unmatched_opportunity(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach story",
            normalized_terms=("beach", "story"),
        )

        resolutions = service.resolve_opportunities_for_experience(
            {
                "experience_id": "experience-beach-story",
                "title": "Beach Story",
                "themes": ("beach",),
                "keywords": ("story",),
                "experience_type": "STORY",
            }
        )

        self.assertEqual(len(resolutions), 1)
        self.assertEqual(
            resolutions[0].matched_experience_ids,
            ("experience-beach-story",),
        )
        self.assertEqual(resolutions[0].source, ContentOpportunityResolutionSource.EXPERIENCE)

    def test_newly_matched_asset_resolves_previous_unmatched_opportunity(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Gym workout photos",
            normalized_terms=("gym", "workout"),
        )

        resolutions = service.resolve_opportunities_for_asset(
            {
                "asset_id": "asset-gym",
                "keywords": ("gym", "workout"),
                "environment": "gym studio",
            }
        )

        self.assertEqual(len(resolutions), 1)
        self.assertEqual(resolutions[0].matched_asset_ids, ("asset-gym",))
        self.assertEqual(resolutions[0].source, ContentOpportunityResolutionSource.ASSET)

    def test_waiting_customers_and_vip_counts_are_identified(self) -> None:
        service = ContentOpportunityService()
        opportunity = service.resolve_content_request(
            customer_id="vip-1",
            provider="telegram",
            provider_customer_id="tg-vip",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
            is_vip=True,
        )
        service.resolve_content_request(
            customer_id="customer-2",
            provider="telegram",
            provider_customer_id="tg-2",
            request_text="Cabin pictures",
            normalized_terms=("photos", "cabin"),
        )

        waiting = service.find_waiting_customers(opportunity)
        resolution = service.resolve_opportunities_for_product(
            {"id": "product-cabin", "display_name": "Cabin photos"}
        )[0]

        self.assertEqual(len(waiting), 2)
        self.assertEqual(resolution.request_count, 2)
        self.assertEqual(resolution.customer_count, 2)
        self.assertEqual(resolution.vip_customer_count, 1)
        self.assertEqual(resolution.waiting_customer_ids, ("vip-1", "customer-2"))
        self.assertEqual(resolution.waiting_provider_customer_ids, ("tg-vip", "tg-2"))

    def test_resolution_evidence_is_preserved(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Travel video",
            normalized_terms=("travel", "video"),
        )

        resolution = service.resolve_opportunities_for_product(
            {
                "id": "product-travel",
                "display_name": "Travel video",
                "publishing_readiness": {"status": "ready"},
            }
        )[0]

        self.assertEqual(resolution.evidence["source"], "content_opportunity_resolution")
        self.assertEqual(resolution.evidence["resolution_source"], "PRODUCT")
        self.assertEqual(resolution.evidence["candidate_match"]["id"], "product-travel")
        self.assertEqual(
            resolution.evidence["resolution_guidance"]["intent"],
            "CONTENT_OPPORTUNITY_RESOLUTION_READY",
        )

    def test_resolution_does_not_message_or_mutate_upstream_objects(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        product = {
            "id": "product-beach",
            "display_name": "Beach photos",
            "markers": ["original"],
        }
        experience = {"experience_id": "experience-1", "markers": ["original"]}
        publishing = {"status": "ready", "markers": ["original"]}
        customer_intelligence = {"customer_id": "customer-1", "markers": ["original"]}
        business_learning = {"outcomes": ["original"]}
        service.product_catalog_service = SimpleNamespace(product=product)
        service.experience_service = SimpleNamespace(experience=experience)
        service.product_business_service = SimpleNamespace(publishing=publishing)
        service.customer_intelligence_service = SimpleNamespace(customer=customer_intelligence)
        service.business_learning_service = SimpleNamespace(learning=business_learning)

        resolution = service.resolve_opportunities_for_product(product)[0]

        self.assertEqual(product["markers"], ["original"])
        self.assertEqual(experience["markers"], ["original"])
        self.assertEqual(publishing["markers"], ["original"])
        self.assertEqual(customer_intelligence["markers"], ["original"])
        self.assertEqual(business_learning["outcomes"], ["original"])
        self.assertFalse(resolution.metadata["contacts_customers"])
        self.assertFalse(resolution.metadata["executes_offers"])
        self.assertFalse(resolution.metadata["modifies_customer_intelligence"])
        self.assertFalse(resolution.metadata["modifies_business_learning"])

    def test_resolution_safe_guidance_contains_no_promise_language(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Cosplay video",
            normalized_terms=("cosplay", "video"),
        )

        resolution = service.resolve_opportunities_for_product(
            {"id": "product-cosplay", "display_name": "Cosplay video"}
        )[0]
        text = " ".join(str(value).lower() for value in resolution.safe_guidance.values())

        for forbidden in ("made specifically", "promised", "guaranteed", "will be sent", "sent immediately"):
            self.assertNotIn(forbidden, text)
        self.assertTrue(resolution.safe_guidance["must_not_contact_customers"])
        self.assertTrue(resolution.safe_guidance["must_not_promise_delivery"])

    def test_unresolved_opportunities_remain_when_confidence_is_too_low(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Shower video",
            normalized_terms=("shower", "video"),
        )

        resolutions = service.resolve_opportunities_for_product(
            {"id": "product-shower", "display_name": "Shower"},
            confidence_threshold=0.9,
        )

        self.assertEqual(resolutions, ())
        self.assertEqual(service.list_resolution_ready_opportunities(), ())
        self.assertEqual(service.build_snapshot().resolution_ready_count, 0)

    def test_list_resolution_ready_opportunities_returns_only_ready_records(self) -> None:
        service = ContentOpportunityService()
        opportunity = service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
        )
        ready = service.resolve_opportunities_for_product(
            {"id": "product-beach", "display_name": "Beach photos"}
        )[0]
        ignored = service.build_resolution_record(
            opportunity=opportunity,
            matched_product_ids=("ignored-product",),
            confidence=0.9,
            source=ContentOpportunityResolutionSource.PRODUCT,
            status=ContentOpportunityResolutionStatus.IGNORED,
        )
        service._resolutions.append(ignored)

        ready_records = service.list_resolution_ready_opportunities()

        self.assertEqual(ready_records, (ready,))
        self.assertEqual(service.build_snapshot().resolution_ready_count, 1)

    def test_repeated_unmatched_demand_creates_creator_recommendation(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
            requested_content_type="photoshoot",
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin pictures",
            normalized_terms=("photos", "cabin"),
            requested_content_type="photoshoot",
        )

        recommendations = service.generate_creator_recommendations()
        recommendation = recommendations[0]

        self.assertEqual(
            recommendation.recommendation_type,
            ContentOpportunityRecommendationType.CREATE_NEW_EXPERIENCE,
        )
        self.assertEqual(recommendation.request_count, 2)
        self.assertEqual(recommendation.customer_count, 2)
        self.assertEqual(recommendation.unmatched_request_count, 2)
        self.assertIn("consider", recommendation.title.lower())
        self.assertTrue(recommendation.metadata["read_only"])
        self.assertTrue(recommendation.metadata["advisory_only"])

    def test_vip_demand_increases_recommendation_priority(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Travel story",
            normalized_terms=("travel", "story"),
            requested_format="story",
            is_vip=True,
        )

        recommendation = service.generate_creator_recommendations()[0]

        self.assertEqual(
            recommendation.priority,
            ContentOpportunityRecommendationPriority.CRITICAL,
        )
        self.assertEqual(recommendation.vip_customer_count, 1)
        self.assertEqual(
            recommendation.recommendation_type,
            ContentOpportunityRecommendationType.CREATE_STORY,
        )

    def test_matched_demand_recommends_reusing_or_promoting_existing_product(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=(
                {"id": "product-beach", "display_name": "Beach photos", "tags": ("beach",)},
            ),
        )

        recommendations = service.generate_creator_recommendations()
        recommendation_types = {item.recommendation_type for item in recommendations}
        promote = next(
            item
            for item in recommendations
            if item.recommendation_type
            == ContentOpportunityRecommendationType.PROMOTE_EXISTING_PRODUCT_WITH_DEMAND
        )

        self.assertIn(
            ContentOpportunityRecommendationType.PROMOTE_EXISTING_PRODUCT_WITH_DEMAND,
            recommendation_types,
        )
        self.assertEqual(promote.related_product_ids, ("product-beach",))
        self.assertEqual(promote.matched_request_count, 1)
        self.assertEqual(promote.unmatched_request_count, 0)

    def test_video_format_demand_creates_format_specific_recommendation(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Gym video",
            normalized_terms=("gym", "video"),
            requested_format="video",
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Workout video",
            normalized_terms=("gym", "video"),
            requested_format="video",
        )

        recommendations = service.generate_creator_recommendations()
        video = [
            item
            for item in recommendations
            if item.recommendation_type == ContentOpportunityRecommendationType.CREATE_VIDEO
        ]

        self.assertTrue(video)
        self.assertEqual(video[0].requested_format, "video")
        self.assertEqual(video[0].evidence.requested_formats["video"], 2)

    def test_recommendations_group_similar_demand(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Gym pictures",
            normalized_terms=("photos", "gym"),
        )

        recommendations = service.generate_creator_recommendations()
        grouped = [
            item
            for item in recommendations
            if item.evidence.topic_key == "gym|photos"
            and item.recommendation_type
            == ContentOpportunityRecommendationType.CREATE_NEW_PRODUCT
        ]

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0].request_count, 2)
        self.assertEqual(grouped[0].customer_count, 2)

    def test_recommendations_never_contain_promise_language(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Cosplay video",
            normalized_terms=("cosplay", "video"),
            requested_format="video",
            is_vip=True,
        )

        forbidden = ("promised", "guaranteed", "coming soon", "will create")
        for recommendation in service.generate_creator_recommendations():
            text = " ".join(
                (
                    recommendation.title,
                    recommendation.summary,
                    recommendation.safe_creator_note,
                )
            ).lower()
            for phrase in forbidden:
                self.assertNotIn(phrase, text)

    def test_recommendation_evidence_includes_request_customer_vip_and_match_counts(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Travel photos",
            normalized_terms=("travel", "photos"),
            is_vip=True,
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Travel pictures",
            normalized_terms=("photos", "travel"),
            product_candidates=(
                {"id": "product-travel", "display_name": "Travel photos"},
            ),
        )

        recommendation = service.generate_creator_recommendations()[0]
        evidence = recommendation.evidence

        self.assertEqual(evidence.request_count, 2)
        self.assertEqual(evidence.customer_count, 2)
        self.assertEqual(evidence.vip_customer_count, 1)
        self.assertEqual(evidence.matched_request_count, 1)
        self.assertEqual(evidence.unmatched_request_count, 1)
        self.assertEqual(evidence.matched_percentage, 50.0)
        self.assertEqual(evidence.unmet_percentage, 50.0)
        self.assertTrue(evidence.metadata["business_learning_ready"])

    def test_recommendations_are_deterministic_read_only_and_on_snapshot(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=({"id": "product-1", "display_name": "Beach photos"},),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
        )

        first = service.generate_creator_recommendations()
        second = service.generate_creator_recommendations()
        snapshot = service.build_snapshot()

        self.assertEqual(first, second)
        self.assertEqual(snapshot.creator_recommendations, first)
        self.assertEqual(snapshot.recommendation_count, len(first))
        for recommendation in first:
            self.assertFalse(recommendation.metadata["creates_products"])
            self.assertFalse(recommendation.metadata["creates_experiences"])
            self.assertFalse(recommendation.metadata["modifies_publishing"])
            self.assertFalse(recommendation.metadata["executes_offers"])

    def test_demand_summary_calculates_matched_and_unmatched_percentages(self) -> None:
        service = ContentOpportunityService()
        product = {"id": "product-beach", "display_name": "Beach photos"}
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            requested_content_type="photoshoot",
            requested_format="photo",
            product_candidates=(product,),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
            requested_content_type="photoshoot",
            requested_format="photo",
        )

        summary = service.summarize_demand()
        snapshot = service.build_snapshot()

        self.assertEqual(summary.total_requests, 2)
        self.assertEqual(summary.matched_requests, 1)
        self.assertEqual(summary.unmatched_requests, 1)
        self.assertEqual(summary.matched_percentage, 50.0)
        self.assertEqual(summary.unmet_percentage, 50.0)
        self.assertEqual(snapshot.total_requests, 2)
        self.assertEqual(snapshot.matched_percentage, 50.0)
        self.assertEqual(snapshot.unmet_percentage, 50.0)
        self.assertEqual(snapshot.demand_by_content_type["photoshoot"], 2)
        self.assertEqual(snapshot.demand_by_format["photo"], 2)

    def test_repeat_and_vip_demand_are_aggregated(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
            is_vip=True,
            source_metadata={"customer_segments": ("vip", "fitness")},
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Gym pictures",
            normalized_terms=("photos", "gym"),
            source_metadata={"customer_segment": "fitness"},
        )

        summary = service.summarize_demand()
        repeat = service.summarize_repeat_demand()
        vip = service.summarize_vip_demand()
        snapshot = service.build_snapshot()

        self.assertEqual(summary.repeat_request_count, 1)
        self.assertEqual(summary.vip_request_count, 1)
        self.assertEqual(summary.unique_customers, 2)
        self.assertEqual(repeat["repeat_demand_terms"]["gym|photos"], 2)
        self.assertEqual(vip["vip_topics"], ("gym|photos",))
        self.assertEqual(snapshot.vip_request_count, 1)
        self.assertEqual(snapshot.repeat_request_count, 1)
        self.assertEqual(snapshot.demand_by_customer_segment["fitness"], 2)
        self.assertEqual(snapshot.opportunity_health, ContentOpportunityHealth.NEEDS_ATTENTION)

    def test_top_requested_and_growing_topics_are_detected(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=({"id": "product-1", "display_name": "Beach photos"},),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
        )
        service.resolve_content_request(
            customer_id="customer-3",
            request_text="Gym pictures",
            normalized_terms=("photos", "gym"),
        )

        snapshot = service.build_snapshot()
        top_keys = tuple(topic.topic_key for topic in snapshot.top_requested_topics)
        growing_keys = tuple(topic.topic_key for topic in snapshot.growing_topics)
        trending = service.summarize_trending_topics()

        self.assertEqual(top_keys[0], "gym|photos")
        self.assertIn("gym|photos", growing_keys)
        self.assertEqual(trending[0].request_count, 2)
        self.assertEqual(
            service.summarize_topic(("gym", "photos")).trend,
            ContentDemandTrend.UNSATISFIED,
        )

    def test_satisfied_and_unsatisfied_demand_are_summarized(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=({"id": "product-1", "display_name": "Beach photos"},),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
        )
        service.resolve_content_request(
            customer_id="customer-3",
            request_text="Cabin pictures",
            normalized_terms=("photos", "cabin"),
        )

        matched = service.summarize_matched_demand()
        unmatched = service.summarize_unmatched_demand()
        snapshot = service.build_snapshot()

        self.assertIn("beach|photos", matched["matched_topics"])
        self.assertIn("cabin|photos", unmatched["unsatisfied_topics"])
        self.assertEqual(snapshot.satisfied_topics[0].topic_key, "beach|photos")
        self.assertEqual(snapshot.unsatisfied_topics[0].topic_key, "cabin|photos")
        self.assertEqual(
            service.summarize_topic(("beach", "photos")).trend,
            ContentDemandTrend.SATISFIED,
        )
        self.assertEqual(
            service.summarize_topic(("cabin", "photos")).trend,
            ContentDemandTrend.UNSATISFIED,
        )

    def test_customer_segment_summary_aggregates_multiple_customers(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Travel photos",
            normalized_terms=("travel", "photos"),
            source_metadata={"customer_segments": ("vip", "travel")},
            is_vip=True,
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Travel pictures",
            normalized_terms=("travel", "photos"),
            metadata={"customer_segment": "travel"},
            product_candidates=({"id": "product-travel", "display_name": "Travel photos"},),
        )

        travel = service.summarize_customer_segment("travel")
        vip = service.summarize_customer_segment("vip")

        self.assertEqual(travel["request_count"], 2)
        self.assertEqual(travel["unique_customers"], 2)
        self.assertEqual(travel["matched_requests"], 1)
        self.assertEqual(travel["unmatched_requests"], 1)
        self.assertEqual(vip["request_count"], 1)

    def test_highest_priority_opportunities_surface_vip_and_repeat_unmatched(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="vip-1",
            request_text="Cabin photos",
            normalized_terms=("cabin", "photos"),
            is_vip=True,
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Cabin pictures",
            normalized_terms=("photos", "cabin"),
        )

        snapshot = service.build_snapshot()

        self.assertEqual(
            snapshot.highest_priority_opportunities[0].normalized_terms,
            ("photos", "cabin"),
        )
        self.assertTrue(snapshot.highest_priority_opportunities[0].vip_demand)
        self.assertEqual(
            service.summarize_topic(("cabin", "photos")).priority,
            ContentOpportunityPriority.CRITICAL,
        )

    def test_demand_intelligence_is_deterministic_and_read_only(self) -> None:
        service = ContentOpportunityService()
        service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=({"id": "product-1", "display_name": "Beach photos"},),
        )
        service.resolve_content_request(
            customer_id="customer-2",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
        )

        first = service.build_snapshot()
        second = service.build_opportunity_snapshot()

        self.assertEqual(first.summary, second.summary)
        self.assertEqual(first.top_requested_topics, second.top_requested_topics)
        self.assertTrue(first.compatibility["read_only"])
        self.assertTrue(first.demand_summary.evidence["business_learning_ready"])
        self.assertFalse(first.demand_summary.evidence["recommendations_generated"])
        self.assertFalse(first.compatibility["changes_decision_engine_behavior"])

    def test_product_matches_are_detected_from_catalog_metadata(self) -> None:
        product = SimpleNamespace(
            id="product-beach",
            display_name="Beach photo set",
            description="Sunny beach photos",
            tags=("beach", "sunny"),
            themes=("summer",),
            keywords=("ocean",),
            product_type="PHOTOSHOOT",
            delivery_type="PAID",
        )
        catalog = SimpleNamespace(
            list_workspace_display_models=lambda **kwargs: (
                SimpleNamespace(
                    product=product,
                    publishing={"status": "ready"},
                ),
            )
        )
        service = ContentOpportunityService(product_catalog_service=catalog)

        matches = service.find_matching_products(
            request_text="Do you have beach photos?",
            normalized_terms=("beach", "photos"),
            creator_profile_id=1,
        )

        self.assertEqual(matches[0]["id"], "product-beach")
        self.assertGreater(matches[0]["confidence"], 0.5)
        self.assertIn("tags", matches[0]["field_hits"])
        self.assertEqual(matches[0]["source"], "ProductCatalogService")
        self.assertEqual(
            matches[0]["supporting_evidence"]["publishing_readiness"]["status"],
            "ready",
        )

    def test_experience_matches_are_detected_from_experience_metadata(self) -> None:
        experience = SimpleNamespace(
            experience_id="experience-story",
            title="Beach Story",
            summary="A soft ocean story",
            themes=("beach",),
            keywords=("story", "ocean"),
            experience_type="STORY",
        )
        experience_service = SimpleNamespace(
            list_experiences=lambda **kwargs: (experience,)
        )
        service = ContentOpportunityService(experience_service=experience_service)

        matches = service.find_matching_experiences(
            request_text="I want a beach story",
            normalized_terms=("beach", "story"),
            creator_profile_id=1,
        )

        self.assertEqual(matches[0]["id"], "experience-story")
        self.assertGreater(matches[0]["confidence"], 0.5)
        self.assertIn("themes", matches[0]["field_hits"])
        self.assertEqual(matches[0]["source"], "ExperienceService")

    def test_asset_matches_are_detected_from_content_intelligence(self) -> None:
        asset = SimpleNamespace(
            asset_id="asset-gym",
            themes=("fitness",),
            keywords=("gym", "workout"),
            activities=("posing",),
            environment="gym studio",
            mood="confident",
            clothing="athletic set",
            classification="photo",
        )
        content_intelligence = SimpleNamespace(
            get_asset_intelligence=lambda asset_id: asset if str(asset_id) == "asset-gym" else None
        )
        service = ContentOpportunityService(
            content_intelligence_service=content_intelligence
        )

        matches = service.find_matching_assets(
            request_text="Do you have gym workout photos?",
            normalized_terms=("gym", "workout"),
            asset_ids=("asset-gym",),
        )

        self.assertEqual(matches[0]["id"], "asset-gym")
        self.assertGreater(matches[0]["confidence"], 0.5)
        self.assertIn("keywords", matches[0]["field_hits"])
        self.assertEqual(matches[0]["source"], "ContentIntelligenceService")

    def test_combined_evidence_increases_confidence(self) -> None:
        product = SimpleNamespace(
            id="product-1",
            display_name="Beach photos",
            tags=("beach",),
            themes=("ocean",),
        )
        experience = SimpleNamespace(
            experience_id="experience-1",
            title="Beach Story",
            themes=("beach",),
        )
        asset = SimpleNamespace(
            asset_id="asset-1",
            keywords=("beach", "photos"),
        )
        service = ContentOpportunityService(
            product_catalog_service=SimpleNamespace(
                list_workspace_display_models=lambda **kwargs: (
                    SimpleNamespace(product=product, publishing={"status": "ready"}),
                )
            ),
            experience_service=SimpleNamespace(
                list_experiences=lambda **kwargs: (experience,)
            ),
            content_intelligence_service=SimpleNamespace(
                get_asset_intelligence=lambda asset_id: asset
            ),
        )

        product_confidence = service.find_matching_products(
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            creator_profile_id=1,
        )[0]["confidence"]
        opportunity = service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            creator_profile_id=1,
            asset_ids=("asset-1",),
        )

        self.assertEqual(opportunity.status, ContentOpportunityStatus.MATCHED)
        self.assertEqual(opportunity.product_ids, ("product-1",))
        self.assertEqual(opportunity.experience_ids, ("experience-1",))
        self.assertEqual(opportunity.asset_ids, ("asset-1",))
        self.assertGreater(opportunity.confidence, product_confidence)
        evidence = opportunity.match.match_evidence
        self.assertEqual(evidence["domain_agreement_count"], 3)
        self.assertEqual(evidence["product_matches"][0]["id"], "product-1")
        self.assertEqual(evidence["experience_matches"][0]["id"], "experience-1")
        self.assertEqual(evidence["asset_matches"][0]["id"], "asset-1")

    def test_request_without_detected_matches_becomes_opportunity(self) -> None:
        service = ContentOpportunityService(
            product_catalog_service=SimpleNamespace(
                list_workspace_display_models=lambda **kwargs: (
                    SimpleNamespace(
                        product=SimpleNamespace(id="product-1", tags=("beach",)),
                        publishing={"status": "ready"},
                    ),
                )
            ),
            experience_service=SimpleNamespace(list_experiences=lambda **kwargs: ()),
            content_intelligence_service=SimpleNamespace(
                get_asset_intelligence=lambda asset_id: None
            ),
        )

        opportunity = service.resolve_content_request(
            customer_id="customer-1",
            request_text="Do you have winter cabin photos?",
            normalized_terms=("winter", "cabin"),
            creator_profile_id=1,
            asset_ids=("asset-missing",),
        )

        self.assertEqual(opportunity.status, ContentOpportunityStatus.UNMATCHED)
        self.assertEqual(opportunity.product_ids, ())
        self.assertTrue(
            opportunity.safe_response_guidance["must_not_promise_future_content"]
        )

    def test_match_detection_preserves_read_only_ownership(self) -> None:
        product = {
            "id": "product-1",
            "display_name": "Beach photos",
            "tags": ["beach"],
            "markers": ["original"],
        }
        experience = {
            "experience_id": "experience-1",
            "title": "Beach story",
            "themes": ["beach"],
            "markers": ["original"],
        }
        asset = {
            "asset_id": "asset-1",
            "keywords": ["beach"],
            "markers": ["original"],
        }
        publishing = {"status": "ready", "markers": ["original"]}
        service = ContentOpportunityService()

        opportunity = service.resolve_content_request(
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=(
                SimpleNamespace(product=product, publishing=publishing),
            ),
            experience_candidates=(experience,),
            asset_candidates=(asset,),
        )

        self.assertEqual(opportunity.status, ContentOpportunityStatus.MATCHED)
        self.assertEqual(product["markers"], ["original"])
        self.assertEqual(experience["markers"], ["original"])
        self.assertEqual(asset["markers"], ["original"])
        self.assertEqual(publishing["markers"], ["original"])
        self.assertFalse(opportunity.metadata["modifies_products"])
        self.assertFalse(opportunity.metadata["modifies_experiences"])
        self.assertFalse(opportunity.metadata["modifies_publishing"])

    def test_match_evidence_is_preserved(self) -> None:
        service = ContentOpportunityService()

        opportunity = service.resolve_content_request(
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=(
                {"id": "product-1", "display_name": "Beach photos", "tags": ("beach",)},
            ),
        )

        evidence = opportunity.match.match_evidence
        self.assertEqual(evidence["source"], "content_opportunity_match_detection")
        self.assertEqual(evidence["product_owner"], "ProductCatalogService/ProductBusinessService")
        self.assertEqual(evidence["product_matches"][0]["matched_terms"], ("beach", "photos"))
        self.assertTrue(
            evidence["product_matches"][0]["supporting_evidence"]["read_only"]
        )

    def test_repeat_requests_continue_accumulating_with_match_detection(self) -> None:
        service = ContentOpportunityService()

        first = service.resolve_content_request(
            customer_id="customer-1",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            product_candidates=(
                {"id": "product-1", "display_name": "Beach photos", "tags": ("beach",)},
            ),
        )
        second = service.resolve_content_request(
            customer_id="customer-2",
            request_text="Beach photos please",
            normalized_terms=("photos", "beach"),
            product_candidates=(
                {"id": "product-1", "display_name": "Beach photos", "tags": ("beach",)},
            ),
        )

        self.assertEqual(first.demand_count, 1)
        self.assertEqual(second.demand_count, 2)
        self.assertTrue(second.repeat_demand)
        self.assertEqual(service.build_snapshot().repeat_demand_terms["beach|photos"], 2)

    def test_unmatched_content_request_creates_durable_opportunity(self) -> None:
        service = ContentOpportunityService()

        opportunity = service.record_content_request(
            customer_id="customer-1",
            provider="telegram",
            provider_customer_id="telegram-1",
            request_text="Do you have beach photos?",
            source=ContentOpportunitySource.TELEGRAM,
            conversation_id="chat-1",
            message_id="message-1",
        )

        self.assertEqual(opportunity.status, ContentOpportunityStatus.UNMATCHED)
        self.assertEqual(opportunity.demand_signal.customer_id, "customer-1")
        self.assertEqual(opportunity.demand_signal.provider, "telegram")
        self.assertIn("beach", opportunity.normalized_terms)
        self.assertTrue(
            opportunity.safe_response_guidance["must_not_promise_future_content"]
        )
        self.assertEqual(
            opportunity.safe_response_guidance["final_response_owner"],
            "DecisionEngine",
        )

        snapshot = service.build_snapshot()
        self.assertEqual(snapshot.unmatched_count, 1)
        self.assertEqual(snapshot.matched_count, 0)
        self.assertEqual(len(snapshot.unmatched_opportunities), 1)

    def test_matched_content_request_records_product_experience_and_asset_ids(self) -> None:
        service = ContentOpportunityService()

        opportunity = service.record_content_request(
            customer_id="customer-2",
            request_text="I want a beach story",
            match_candidates=[
                {
                    "product_id": "product-1",
                    "experience_id": "experience-1",
                    "asset_ids": ("asset-1", "asset-2"),
                    "confidence": 0.88,
                }
            ],
            normalized_terms=("beach", "story"),
        )

        self.assertEqual(opportunity.status, ContentOpportunityStatus.MATCHED)
        self.assertEqual(opportunity.product_ids, ("product-1",))
        self.assertEqual(opportunity.experience_ids, ("experience-1",))
        self.assertEqual(opportunity.asset_ids, ("asset-1", "asset-2"))
        self.assertTrue(opportunity.match.can_offer_existing_content)
        self.assertEqual(opportunity.match.confidence, 0.88)
        self.assertEqual(
            opportunity.safe_response_guidance["intent"],
            "MATCHED_CONTENT_REQUEST_EXISTING_CONTENT_AVAILABLE",
        )

        snapshot = service.build_snapshot()
        self.assertEqual(snapshot.matched_count, 1)
        self.assertIsInstance(snapshot.matched_requests[0], ContentRequestMatch)
        self.assertEqual(snapshot.unmatched_count, 0)

    def test_safe_guidance_never_promises_future_content(self) -> None:
        service = ContentOpportunityService()

        opportunity = service.record_content_request(
            request_text="Can you make a custom cosplay set?",
        )
        guidance = " ".join(
            str(value).lower()
            for value in opportunity.safe_response_guidance.values()
        )

        self.assertIn("without promising future content", guidance)
        self.assertNotIn("will make", guidance)
        self.assertNotIn("promise", guidance.replace("without promising", ""))
        self.assertTrue(
            opportunity.safe_response_guidance["must_not_promise_future_content"]
        )

    def test_repeated_similar_requests_increase_demand_count(self) -> None:
        service = ContentOpportunityService()

        first = service.record_content_request(
            customer_id="customer-1",
            request_text="Do you have gym photos?",
            normalized_terms=("gym", "photos"),
        )
        second = service.record_content_request(
            customer_id="customer-2",
            request_text="Any gym pics?",
            normalized_terms=("photos", "gym"),
        )

        self.assertEqual(first.demand_count, 1)
        self.assertEqual(second.demand_count, 2)
        self.assertTrue(second.repeat_demand)

        snapshot = service.build_snapshot()
        self.assertEqual(snapshot.repeat_demand_terms["gym|photos"], 2)
        self.assertEqual(snapshot.repeat_demand_count, 1)

    def test_vip_request_is_surfaced_as_higher_priority(self) -> None:
        service = ContentOpportunityService()

        normal = service.record_content_request(
            customer_id="normal",
            request_text="Do you have car photos?",
            normalized_terms=("car", "photos"),
        )
        vip = service.record_content_request(
            customer_id="vip",
            request_text="Do you have travel photos?",
            normalized_terms=("travel", "photos"),
            is_vip=True,
        )

        self.assertEqual(normal.priority, ContentOpportunityPriority.NORMAL)
        self.assertEqual(vip.priority, ContentOpportunityPriority.HIGH)
        self.assertEqual(vip.next_recommended_action, "Review VIP unmet content demand")

        snapshot = service.build_snapshot()
        self.assertEqual(snapshot.vip_demand_count, 1)
        self.assertEqual(snapshot.vip_opportunities[0].demand_signal.customer_id, "vip")

    def test_service_does_not_mutate_upstream_domain_objects(self) -> None:
        product = {"id": "product-1", "markers": ["original"]}
        experience = {"id": "experience-1", "markers": ["original"]}
        publishing = {"status": "ready", "markers": ["original"]}
        customer_intelligence = {"customer_id": "customer-1", "markers": ["original"]}
        business_learning = {"outcomes": ["original"]}

        service = ContentOpportunityService(
            product_catalog_service=SimpleNamespace(product=product),
            experience_service=SimpleNamespace(experience=experience),
            customer_intelligence_service=SimpleNamespace(
                customer_intelligence=customer_intelligence
            ),
            business_learning_service=SimpleNamespace(
                business_learning=business_learning
            ),
            product_business_service=SimpleNamespace(publishing=publishing),
        )

        service.record_content_request(
            request_text="Do you have beach photos?",
            match_candidates={"product_id": "product-1", "confidence": 0.7},
        )

        self.assertEqual(product, {"id": "product-1", "markers": ["original"]})
        self.assertEqual(experience, {"id": "experience-1", "markers": ["original"]})
        self.assertEqual(publishing, {"status": "ready", "markers": ["original"]})
        self.assertEqual(
            customer_intelligence,
            {"customer_id": "customer-1", "markers": ["original"]},
        )
        self.assertEqual(business_learning, {"outcomes": ["original"]})

        snapshot = service.build_snapshot()
        self.assertFalse(snapshot.compatibility["modifies_products"])
        self.assertFalse(snapshot.compatibility["modifies_experiences"])
        self.assertFalse(snapshot.compatibility["modifies_publishing"])
        self.assertFalse(snapshot.compatibility["modifies_customer_intelligence"])
        self.assertFalse(snapshot.compatibility["modifies_business_learning"])

    def test_snapshot_exposes_content_opportunity_read_model(self) -> None:
        service = ContentOpportunityService()
        service.record_content_request(
            customer_id="matched",
            request_text="Beach photos",
            normalized_terms=("beach", "photos"),
            match_candidates={"product_id": "product-1", "asset_id": "asset-1"},
        )
        service.record_content_request(
            customer_id="unmatched-1",
            request_text="Gym photos",
            normalized_terms=("gym", "photos"),
        )
        service.record_content_request(
            customer_id="unmatched-2",
            request_text="Gym pictures",
            normalized_terms=("gym", "photos"),
            is_vip=True,
        )

        snapshot = service.build_snapshot()

        self.assertEqual(snapshot.matched_count, 1)
        self.assertEqual(snapshot.unmatched_count, 1)
        self.assertEqual(snapshot.repeat_demand_terms["gym|photos"], 2)
        self.assertEqual(snapshot.vip_demand_count, 1)
        self.assertIn(
            "Review VIP unmet content demand",
            snapshot.next_recommended_actions,
        )
        self.assertTrue(snapshot.compatibility["read_only"])
        self.assertTrue(snapshot.compatibility["provider_neutral"])
        self.assertFalse(snapshot.compatibility["executes_telegram"])
        self.assertFalse(snapshot.compatibility["changes_decision_engine_behavior"])


if __name__ == "__main__":
    unittest.main()
