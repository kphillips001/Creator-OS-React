import unittest
from types import SimpleNamespace
from uuid import uuid4

from app.services.ai_import_workflow_service import (
    AIImportAssetResult,
    AIImportBatchResult,
    AutomaticOrganizationResult,
)
from app.services.content_intelligence_service import ContentIntelligenceService
from app.services.commerce_strategy_service import CommerceStrategyService
from app.services.creator_review_service import CreatorReviewService
from app.services.product_strategy_service import ProductStrategyService


def understanding(asset_id=101):
    return SimpleNamespace(
        identity=SimpleNamespace(asset_id=asset_id),
        media=SimpleNamespace(
            media_type="image",
            runtime_exists=True,
            width=1200,
            height=1600,
        ),
        classification=SimpleNamespace(
            final_classification="VIP",
            classification="VIP",
            confidence=0.91,
        ),
        visual=SimpleNamespace(
            summary="Soft mirror-set with a flirty tone.",
            detected_themes=("mirror", "soft"),
            suggested_tags=("vip", "lace"),
            mood="flirty",
            setting="bedroom",
            outfit="lace set",
            activity="posing",
            objects=("mirror",),
            gpt_vision_result={"keywords": ("glam", "mirror")},
        ),
        safety=SimpleNamespace(risk_flags=("manual_review_optional",)),
        metadata=SimpleNamespace(media_metadata={}),
        provenance=SimpleNamespace(source="test"),
        readiness=SimpleNamespace(
            has_runtime_media=True,
            has_visual_summary=True,
            has_classification=True,
            needs_review=False,
        ),
    )


def content_intelligence(asset_id=101):
    return ContentIntelligenceService().build_from_understanding(
        understanding(asset_id)
    )


def product_strategy(exp=None, asset_id=101):
    return ProductStrategyService().recommend(
        content_intelligence=content_intelligence(asset_id),
        experience_context=exp or experience((asset_id,)),
        commerce_recommendation=commerce((asset_id,)),
    )


def commerce_strategy(product_strategy_result, exp=None, asset_id=101):
    return CommerceStrategyService().recommend(
        content_intelligence=content_intelligence(asset_id),
        experience_context=exp or experience((asset_id,)),
        commerce_intelligence=commerce((asset_id,)),
        product_strategy_result=product_strategy_result,
    )


def experience(asset_ids=(101,)):
    return SimpleNamespace(
        experience_type=SimpleNamespace(value="STANDALONE"),
        asset_ids=asset_ids,
        suggested_name="Mirror Set",
        suggested_summary="A concise standalone review summary.",
        suggested_cover_asset_id=asset_ids[0],
        suggested_themes=("mirror", "soft"),
        suggested_keywords=("mirror", "vip"),
        mood="flirty",
        setting="bedroom",
        visual_continuity={"continuity": "single setting"},
        story_progression={"sequence": "tease to reveal"},
        technical_continuity={"lighting": "soft"},
        intelligence_metadata={"source": "experience_intelligence"},
        intelligence_provenance={"asset_understanding": True},
        confidence=0.84,
        evidence=(
            SimpleNamespace(
                reason="import_batch",
                detail="single asset",
                weight=30,
            ),
        ),
    )


def commerce(asset_ids=(101,)):
    return SimpleNamespace(
        source_type="asset" if len(asset_ids) == 1 else "experience",
        source_id="-".join(str(asset_id) for asset_id in asset_ids),
        asset_ids=asset_ids,
        product_type=SimpleNamespace(value="SINGLE_IMAGE"),
        delivery_type=SimpleNamespace(value="PAID"),
        suggested_name="Mirror Set VIP",
        suggested_description="A product-ready description.",
        suggested_tags=("mirror", "vip"),
        suggested_themes=("flirty",),
        suggested_keywords=("mirror", "vip", "paid"),
        price=SimpleNamespace(
            suggested_price_cents=2499,
            min_price_cents=1800,
            max_price_cents=3400,
            currency="USD",
            pricing_rule="VIP_SINGLE_IMAGE",
        ),
        publishing=SimpleNamespace(
            status="ready_for_draft",
            action="generate_product_draft",
            reason="Ready.",
        ),
        confidence=0.88,
        evidence=(
            SimpleNamespace(
                reason="classification",
                detail="VIP",
                weight=20,
            ),
        ),
    )


class FakeExperienceService:
    def __init__(self):
        self.calls = []

    def get_metadata(self, experience):
        self.calls.append(("get_metadata", experience.experience_id))
        return experience.metadata

    def get_ordered_asset_ids(self, experience):
        self.calls.append(("get_ordered_asset_ids", experience.experience_id))
        return experience.ordered_asset_ids

    def get_cover_asset_id(self, experience):
        self.calls.append(("get_cover_asset_id", experience.experience_id))
        return experience.cover_asset_id

    def get_experience_type(self, experience):
        self.calls.append(("get_experience_type", experience.experience_id))
        return experience.experience_type

    def list_asset_relationships(self, asset_id):
        self.calls.append(("list_asset_relationships", asset_id))
        return (
            SimpleNamespace(
                asset_id=asset_id,
                experience_id="experience-review",
                position=0,
                role="member",
                source="experience_service",
                compatibility=False,
            ),
        )

    def list_product_relationships(self, product_id):
        self.calls.append(("list_product_relationships", str(product_id)))
        return (
            SimpleNamespace(
                product_id=str(product_id),
                experience_id="experience-review",
                source="experience_service",
                compatibility=False,
            ),
        )

    def list_experience_product_relationships(self, experience_id):
        self.calls.append(("list_experience_product_relationships", experience_id))
        return ()


class CreatorReviewServiceTests(unittest.TestCase):
    def test_build_review_from_single_import_result(self):
        exp = experience()
        com = commerce()
        product_id = uuid4()
        product_draft = {
            "success": True,
            "created": True,
            "product_id": str(product_id),
            "product_type": "SINGLE_IMAGE",
            "delivery_type": "PAID",
            "status": "ACTIVE",
        }
        strategy = product_strategy(exp)
        organization = AutomaticOrganizationResult(
            asset_ids=(101,),
            organization_type="standalone",
            asset_library_visible=True,
            local_vault_owned=True,
            experience_recommendation=exp,
            product_strategy_result=strategy,
            commerce_strategy_result=commerce_strategy(strategy, exp),
            product_draft_result=product_draft,
            delivery_type="PAID",
            publishing_readiness={
                "status": "ready",
                "detail": "Local asset only",
            },
        )
        workflow_result = AIImportAssetResult(
            success=True,
            media_path="data/uploads/example.jpg",
            upload_intent="ppv_image",
            legacy_result={"success": True, "final_classification": "VIP"},
            content_id=101,
            product_draft_result=product_draft,
            asset=SimpleNamespace(id=101, file_name="example.jpg"),
            content_intelligence=content_intelligence(),
            asset_understanding=understanding(),
            experience_recommendation=exp,
            commerce_recommendation=com,
            product_strategy_result=strategy,
            commerce_strategy_result=commerce_strategy(strategy, exp),
            publishing_readiness={"status": "ready", "detail": "Local asset only"},
            organization_result=organization,
        )
        experiences = FakeExperienceService()

        review = CreatorReviewService(
            experience_service=experiences,
        ).build_review(
            workflow_result,
            manual_overrides={"suggested_name": "Creator Title"},
        )

        self.assertEqual(review.review_type, "standalone")
        self.assertEqual(review.asset_ids, (101,))
        self.assertEqual(review.asset.status, "available")
        self.assertEqual(review.asset_understanding.confidence, 0.91)
        self.assertEqual(review.content_intelligence.status, "available")
        self.assertEqual(
            review.content_intelligence.data["environments"],
            ("bedroom",),
        )
        self.assertEqual(
            review.content_intelligence.data["activities"],
            ("posing",),
        )
        self.assertEqual(
            review.content_intelligence.data["clothing"],
            ("lace set",),
        )
        self.assertIn("mirror", review.content_intelligence.data["themes"])
        self.assertIn("glam", review.content_intelligence.data["keywords"])
        self.assertEqual(
            review.content_intelligence.data["suggested_cover_image"],
            101,
        )
        self.assertGreaterEqual(review.content_intelligence.confidence, 0.65)
        self.assertIn(
            "Asset media type is image.",
            review.content_intelligence.data["recommendation_rationale"],
        )
        self.assertEqual(
            review.experience_recommendation.data["experience_type"],
            "STANDALONE",
        )
        self.assertEqual(review.commerce_recommendation.confidence, 0.88)
        self.assertEqual(review.product_strategy.status, "available")
        self.assertIn(
            "free_preview",
            review.product_strategy.data["recommended_product_types"],
        )
        self.assertIn(
            "single_premium",
            review.product_strategy.data["recommended_product_types"],
        )
        self.assertEqual(
            review.product_strategy.data["catalog_recommendation"][
                "associated_experience_type"
            ],
            "STANDALONE",
        )
        strategy_product = review.product_strategy.data["recommended_products"][0]
        self.assertEqual(strategy_product["asset_ids"], (101,))
        self.assertGreaterEqual(strategy_product["confidence"], 0.0)
        self.assertEqual(
            strategy_product["composition"]["included_asset_ids"],
            (101,),
        )
        self.assertEqual(
            strategy_product["composition"]["asset_order"],
            (101,),
        )
        self.assertEqual(
            strategy_product["composition"]["relationship_type"],
            "experience_asset_product",
        )
        self.assertIn(
            "Content recommendations are available.",
            review.product_strategy.data["recommendation_rationale"],
        )
        self.assertEqual(review.commerce_strategy.status, "available")
        self.assertIn(
            "conversation_objective",
            review.commerce_strategy.data["recommendation_types"],
        )
        self.assertIn(
            "offer_sequencing",
            review.commerce_strategy.data["recommendation_types"],
        )
        self.assertIn(
            "best_teaser",
            review.commerce_strategy.data["recommendation_types"],
        )
        self.assertIn(
            "relationship_building",
            review.commerce_strategy.data["relationship_stages"],
        )
        self.assertTrue(
            review.commerce_strategy.data["customer_journey_recommendations"]
        )
        commerce_strategy_item = (
            review.commerce_strategy.data["commerce_recommendations"][0]
        )
        self.assertIsNotNone(commerce_strategy_item["recommended_objective"])
        self.assertFalse(
            commerce_strategy_item["metadata"]["runtime_action"]
        )
        self.assertFalse(
            commerce_strategy_item["customer_journey"]["metadata"][
                "tracks_customer_state"
            ]
        )
        self.assertEqual(
            review.commerce_strategy.data["ownership"][
                "commerce_strategy_owner"
            ],
            "CommerceStrategyService",
        )
        self.assertEqual(
            review.product_draft.data["product_id"],
            str(product_id),
        )
        self.assertEqual(review.experience.title, "Experience")
        self.assertEqual(
            review.experience.data["experience_name"],
            "Mirror Set",
        )
        self.assertEqual(
            review.experience.data["experience_type"],
            "STANDALONE",
        )
        self.assertEqual(
            review.experience.data["themes"],
            ("mirror", "soft"),
        )
        self.assertEqual(
            review.experience.data["keywords"],
            ("mirror", "vip"),
        )
        self.assertEqual(review.experience.data["mood"], "flirty")
        self.assertEqual(
            review.experience.data["story_progression"],
            {"sequence": "tease to reveal"},
        )
        self.assertEqual(
            review.experience.data["technical_continuity"],
            {"lighting": "soft"},
        )
        self.assertEqual(
            review.experience.data["product_relationships"],
            (str(product_id),),
        )
        self.assertEqual(
            review.experience.data["publishing_readiness"]["status"],
            "ready",
        )
        self.assertIn(
            "experience_name",
            review.experience.data["supported_overrides"],
        )
        self.assertIn(
            ("list_asset_relationships", 101),
            experiences.calls,
        )
        self.assertIn(
            ("list_product_relationships", str(product_id)),
            experiences.calls,
        )
        self.assertEqual(review.product_draft.data["delivery_type"], "PAID")
        self.assertEqual(review.delivery_type.data["delivery_type"], "PAID")
        self.assertEqual(
            review.publishing_readiness.summary,
            "Local asset only",
        )
        self.assertEqual(
            review.organization.data["relationship_chain"],
            (
                "Asset",
                "AssetUnderstanding",
                "ExperienceRecommendation",
                "ProductStrategy",
                "CommerceStrategy",
                "Product Draft",
                "Publishing readiness",
            ),
        )
        self.assertEqual(
            review.manual_overrides,
            {"suggested_name": "Creator Title"},
        )
        self.assertEqual(review.warnings, ())

    def test_build_review_from_batch_result_surfaces_warnings(self):
        exp = experience((201, 202))
        com = commerce((201, 202))
        organization = AutomaticOrganizationResult(
            asset_ids=(201, 202),
            organization_type="photo_set",
            asset_library_visible=True,
            local_vault_owned=True,
            experience_recommendation=exp,
            product_draft_result=None,
            delivery_type="PAID",
            publishing_readiness={
                "status": "partial",
                "asset_count": 2,
                "ready_asset_count": 1,
            },
            notes=("Product Draft unavailable or deferred.",),
        )
        asset_results = (
            AIImportAssetResult(
                success=True,
                media_path="data/uploads/first.jpg",
                upload_intent="teaser_image",
                legacy_result={"success": True},
                content_id=201,
                asset=SimpleNamespace(id=201, file_name="first.jpg"),
                asset_understanding=understanding(201),
            ),
            AIImportAssetResult(
                success=True,
                media_path="data/uploads/second.jpg",
                upload_intent="teaser_image",
                legacy_result={"success": True},
                content_id=202,
                asset=SimpleNamespace(id=202, file_name="second.jpg"),
                asset_understanding=understanding(202),
            ),
        )
        workflow_result = AIImportBatchResult(
            success=True,
            asset_results=asset_results,
            content_ids=(201, 202),
            product_draft_result=None,
            experience_recommendation=exp,
            commerce_recommendation=com,
            publishing_readiness={
                "status": "partial",
                "asset_count": 2,
                "ready_asset_count": 1,
            },
            organization_result=organization,
        )

        experiences = FakeExperienceService()

        review = CreatorReviewService(
            experience_service=experiences,
        ).build_review(workflow_result)

        self.assertEqual(review.review_type, "photo_set")
        self.assertEqual(review.asset_ids, (201, 202))
        self.assertEqual(review.asset.data["asset_count"], 2)
        self.assertEqual(review.experience.status, "available")
        self.assertEqual(
            review.experience.data["asset_ids"],
            (201, 202),
        )
        self.assertEqual(review.product_draft.status, "missing")
        self.assertIn(
            "Product Draft unavailable or deferred.",
            review.warnings,
        )
        self.assertIn("partial", review.warnings)

    def test_build_workspace_review_summary_is_read_only_projection(self):
        asset_summary = SimpleNamespace(
            metrics=(
                SimpleNamespace(label="Needs Classification", value="2"),
                SimpleNamespace(label="Asset Alerts", value="1"),
            )
        )
        experience_cards = (
            SimpleNamespace(
                intelligence_coverage="Partial",
                compatibility=False,
                cover_asset_id=10,
                themes=("theme",),
                keywords=("keyword",),
                story_progression="intro",
            ),
        )
        product_cards = (
            SimpleNamespace(
                review_status="Needs Assets",
                suggested_price="USD 19.99",
            ),
        )
        publishing_cards = (
            SimpleNamespace(
                missing_requirements=("Media Link",),
                provider_error=None,
            ),
        )

        summary = CreatorReviewService().build_workspace_review_summary(
            asset_summary=asset_summary,
            experience_cards=experience_cards,
            product_cards=product_cards,
            publishing_cards=publishing_cards,
        )

        self.assertEqual(summary.total_pending, 6)
        self.assertEqual(summary.assets_awaiting_review, 3)
        self.assertEqual(summary.experiences_awaiting_review, 1)
        self.assertEqual(summary.products_awaiting_review, 1)
        self.assertEqual(summary.publishing_reviews_remaining, 1)
        self.assertEqual(summary.completed_reviews, None)
        self.assertEqual(summary.review_completion_percentage, None)
        titles = {item.title for item in summary.items}
        self.assertIn("Assets awaiting review", titles)
        self.assertIn("Experiences awaiting review", titles)
        self.assertIn("Products awaiting review", titles)
        self.assertIn("Publishing readiness awaiting review", titles)
        product_item = next(
            item for item in summary.items if item.review_type == "products"
        )
        self.assertEqual(product_item.target, "Product Catalog")
        self.assertEqual(product_item.override_proposals, ("price", "delivery_type", "description"))


if __name__ == "__main__":
    unittest.main()
