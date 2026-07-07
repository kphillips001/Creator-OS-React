import unittest
from pathlib import Path
from types import SimpleNamespace

from app.models.creator_intent import CreatorContentType, CreatorIntent
from app.services.ai_import_workflow_service import AIImportWorkflowService


class FakeAssets:
    def get_by_id(self, asset_id):
        return SimpleNamespace(id=asset_id, fanvue_upload_status="not_requested")


class FakeProductDrafting:
    def __init__(self):
        self.photo_set_calls = []
        self.single_asset_calls = []

    def create_draft_result_for_asset(
        self,
        asset_id,
        *,
        creator_profile_id,
        commerce_recommendation=None,
    ):
        self.single_asset_calls.append(
            {
                "asset_id": asset_id,
                "creator_profile_id": creator_profile_id,
                "commerce_recommendation": commerce_recommendation,
            }
        )
        return {
            "success": True,
            "created": True,
            "product_id": f"product-{asset_id}",
        }

    def create_photo_set_for_assets(
        self,
        asset_ids,
        *,
        creator_profile_id,
        commerce_recommendation=None,
    ):
        self.photo_set_calls.append(
            {
                "asset_ids": list(asset_ids),
                "creator_profile_id": creator_profile_id,
                "commerce_recommendation": commerce_recommendation,
            }
        )
        return SimpleNamespace(
            product=SimpleNamespace(
                id="product-1",
                product_type=SimpleNamespace(value="PHOTO_SET"),
                status=SimpleNamespace(value="ACTIVE"),
                price_cents=4499,
                base_price_cents=4499,
                min_price_cents=3300,
                max_price_cents=6100,
            ),
            activated=True,
        )


class FakePublishing:
    def project_legacy_asset_record(self, asset):
        return {
            "asset_id": asset.id,
            "provider_status": "not_requested",
        }

    def get_provider_status_display(self, record, **kwargs):
        return "Not uploaded to Fanvue", "Local asset only"


class FakeAssetUnderstanding:
    def build_from_asset(self, asset):
        return SimpleNamespace(
            asset_id=asset.id,
            source="asset",
            media=SimpleNamespace(local_vault_path=f"vault/{asset.id}.jpg"),
            readiness=SimpleNamespace(has_local_vault_media=True),
        )

    def get_understanding(self, asset_id):
        return SimpleNamespace(
            asset_id=asset_id,
            source="repository",
            media=SimpleNamespace(local_vault_path=f"vault/{asset_id}.jpg"),
            readiness=SimpleNamespace(has_local_vault_media=True),
        )


class FakeContentIntelligence:
    def __init__(self, understanding_service):
        self.understanding_service = understanding_service
        self.build_calls = []
        self.get_calls = []

    def build_from_asset(self, asset):
        self.build_calls.append(asset)
        return SimpleNamespace(
            asset_understanding=self.understanding_service.build_from_asset(asset)
        )

    def get_asset_intelligence(self, asset_id):
        self.get_calls.append(asset_id)
        return SimpleNamespace(
            asset_understanding=(
                self.understanding_service.get_understanding(asset_id)
            )
        )


class FakeProductStrategy:
    def __init__(self):
        self.calls = []

    def recommend(
        self,
        *,
        creator_intent=None,
        content_intelligences=(),
        experience_context=None,
        commerce_recommendation=None,
    ):
        values = tuple(content_intelligences or ())
        self.calls.append(
            {
                "asset_ids": tuple(item.asset_id for item in values),
                "creator_intent": creator_intent,
                "experience_context": experience_context,
                "commerce_recommendation": commerce_recommendation,
            }
        )
        return SimpleNamespace(
            source_type="experience" if experience_context else "content",
            recommendations=(
                SimpleNamespace(recommendation_type="free_preview"),
            ),
            catalog_recommendation=SimpleNamespace(
                recommended_products=(
                    SimpleNamespace(recommendation_type="free_preview"),
                )
            ),
        )


class FakeCommerceStrategy:
    def __init__(self):
        self.calls = []

    def recommend(
        self,
        *,
        content_intelligences=(),
        experience_context=None,
        commerce_intelligence=None,
        product_strategy_result=None,
    ):
        values = tuple(content_intelligences or ())
        self.calls.append(
            {
                "asset_ids": tuple(
                    getattr(
                        getattr(item, "asset_understanding", item),
                        "asset_id",
                        None,
                    )
                    for item in values
                ),
                "experience_context": experience_context,
                "commerce_intelligence": commerce_intelligence,
                "product_strategy_result": product_strategy_result,
            }
        )
        return SimpleNamespace(
            source_type="experience" if experience_context else "content",
            recommendations=(
                SimpleNamespace(
                    recommendation_type="conversation_objective",
                    recommended_objective="Prepare long-term guidance.",
                ),
            ),
        )


class FakeExperienceIntelligence:
    def __init__(self):
        self.calls = []

    def recommend_for_understandings(
        self,
        understandings,
        *,
        package_type=None,
        import_session_id=None,
    ):
        self.calls.append(
            {
                "asset_ids": tuple(item.asset_id for item in understandings),
                "package_type": package_type,
                "import_session_id": import_session_id,
            }
        )
        return SimpleNamespace(
            asset_ids=tuple(item.asset_id for item in understandings),
            package_type=package_type,
            import_session_id=import_session_id,
        )


class FakeCommerceIntelligence:
    def recommend(
        self,
        *,
        asset_understanding=None,
        asset_understandings=None,
        experience_recommendation=None,
    ):
        values = tuple(asset_understandings or ())
        if asset_understanding is not None:
            values = (asset_understanding,) + values
        return SimpleNamespace(
            asset_ids=tuple(item.asset_id for item in values),
            experience_asset_ids=(
                experience_recommendation.asset_ids
                if experience_recommendation
                else ()
            ),
            delivery_type=SimpleNamespace(value="PAID"),
            publishing=SimpleNamespace(
                status="ready_for_review",
                action="review_product_draft",
                reason="Commerce recommendation is ready for draft review.",
            ),
        )


class AIImportWorkflowServiceTests(unittest.TestCase):
    def test_import_asset_delegates_to_existing_classifier(self):
        calls = []

        def classifier(**kwargs):
            calls.append(kwargs)
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "TEASE",
                "db_save_result": {
                    "content_id": 101,
                    "product_draft_result": {
                        "success": True,
                        "product_id": "product-101",
                    },
                },
            }

        product_drafting = FakeProductDrafting()
        experience_intelligence = FakeExperienceIntelligence()
        product_strategy = FakeProductStrategy()
        commerce_strategy = FakeCommerceStrategy()
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=product_drafting,
            publishing_service=FakePublishing(),
            asset_understanding_service=FakeAssetUnderstanding(),
            experience_intelligence_service=experience_intelligence,
            commerce_intelligence_service=FakeCommerceIntelligence(),
            product_strategy_service=product_strategy,
            commerce_strategy_service=commerce_strategy,
        )

        result = service.import_asset(
            media_path=Path("data/uploads/example.jpg"),
            upload_intent="teaser_image",
            creator_profile_id=2,
            original_filename="example.jpg",
            fanvue_account_id=1,
            content_tier="VIP",
            distribution_type="both",
            mass_ppv_price=14.99,
            provider_upload_enabled=False,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.content_id, 101)
        self.assertEqual(result.final_classification, "TEASE")
        self.assertEqual(result.product_draft_result["product_id"], "product-101")
        self.assertEqual(len(product_drafting.single_asset_calls), 1)
        self.assertIs(
            product_drafting.single_asset_calls[0]["commerce_recommendation"],
            result.commerce_recommendation,
        )
        self.assertEqual(result.asset_understanding.asset_id, 101)
        self.assertEqual(result.asset_understanding.source, "asset")
        self.assertEqual(result.experience_recommendation.asset_ids, (101,))
        self.assertEqual(
            result.experience_recommendation.package_type,
            "standalone",
        )
        self.assertEqual(
            result.experience_recommendation.import_session_id,
            "asset:101",
        )
        self.assertEqual(result.commerce_recommendation.asset_ids, (101,))
        self.assertIsNotNone(result.product_strategy_result)
        self.assertIs(
            result.organization_result.product_strategy_result,
            result.product_strategy_result,
        )
        self.assertIsNotNone(result.commerce_strategy_result)
        self.assertIs(
            result.organization_result.commerce_strategy_result,
            result.commerce_strategy_result,
        )
        self.assertEqual(len(product_strategy.calls), 1)
        self.assertEqual(product_strategy.calls[0]["asset_ids"], (101,))
        self.assertIs(
            product_strategy.calls[0]["experience_context"],
            result.experience_recommendation,
        )
        self.assertIs(
            product_strategy.calls[0]["commerce_recommendation"],
            result.commerce_recommendation,
        )
        self.assertEqual(len(commerce_strategy.calls), 1)
        self.assertEqual(commerce_strategy.calls[0]["asset_ids"], (101,))
        self.assertIs(
            commerce_strategy.calls[0]["experience_context"],
            result.experience_recommendation,
        )
        self.assertIs(
            commerce_strategy.calls[0]["commerce_intelligence"],
            result.commerce_recommendation,
        )
        self.assertIs(
            commerce_strategy.calls[0]["product_strategy_result"],
            result.product_strategy_result,
        )
        self.assertEqual(
            result.commerce_recommendation.experience_asset_ids,
            (101,),
        )
        self.assertEqual(result.publishing_readiness["detail"], "Local asset only")
        self.assertIsNotNone(result.organization_result)
        self.assertEqual(result.organization_result.asset_ids, (101,))
        self.assertEqual(result.organization_result.organization_type, "standalone")
        self.assertTrue(result.organization_result.asset_library_visible)
        self.assertTrue(result.organization_result.local_vault_owned)
        self.assertIs(
            result.organization_result.experience_recommendation,
            result.experience_recommendation,
        )
        self.assertIs(
            result.organization_result.product_draft_result,
            result.product_draft_result,
        )
        self.assertEqual(result.organization_result.delivery_type, "PAID")
        self.assertEqual(
            result.organization_result.publishing_readiness["detail"],
            "Local asset only",
        )
        self.assertIn(
            "CommerceStrategy",
            result.organization_result.relationship_chain,
        )
        self.assertEqual(calls[0]["image_path"], Path("data/uploads/example.jpg"))
        self.assertTrue(calls[0]["save_to_db"])
        self.assertEqual(calls[0]["upload_intent"], "teaser_image")
        self.assertEqual(
            result.creator_intent.content_type,
            CreatorContentType.SINGLE_ASSET,
        )
        self.assertEqual(
            result.creator_intent.legacy_upload_intent,
            "teaser_image",
        )
        self.assertEqual(calls[0]["creator_profile_id"], 2)
        self.assertEqual(calls[0]["original_filename"], "example.jpg")
        self.assertFalse(calls[0]["create_product_draft"])
        self.assertEqual(
            experience_intelligence.calls[0]["import_session_id"],
            "asset:101",
        )

    def test_import_asset_batch_creates_photo_set_from_imported_assets(self):
        next_id = 200

        def classifier(**kwargs):
            nonlocal next_id
            next_id += 1
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "TEASE",
                "gpt_vision_raw": {"confidence": 0.91},
                "db_save_result": {"content_id": next_id},
            }

        product_drafting = FakeProductDrafting()
        experience_intelligence = FakeExperienceIntelligence()
        product_strategy = FakeProductStrategy()
        commerce_strategy = FakeCommerceStrategy()
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=product_drafting,
            publishing_service=FakePublishing(),
            asset_understanding_service=FakeAssetUnderstanding(),
            experience_intelligence_service=experience_intelligence,
            commerce_intelligence_service=FakeCommerceIntelligence(),
            product_strategy_service=product_strategy,
            commerce_strategy_service=commerce_strategy,
        )

        result = service.import_asset_batch(
            media_items=[
                {
                    "media_path": Path("data/uploads/first.jpg"),
                    "original_filename": "first.jpg",
                },
                {
                    "media_path": Path("data/uploads/second.jpg"),
                    "original_filename": "second.jpg",
                },
            ],
            upload_intent="teaser_image",
            creator_profile_id=2,
            package_type="photo_set",
        )

        self.assertTrue(result.success)
        self.assertEqual(result.content_ids, (201, 202))
        self.assertEqual(
            result.creator_intent.content_type,
            CreatorContentType.PHOTOSHOOT,
        )
        self.assertIsNotNone(result.product_draft_result)
        self.assertEqual(result.experience_recommendation.asset_ids, (201, 202))
        self.assertEqual(result.experience_recommendation.package_type, "photo_set")
        self.assertEqual(
            result.experience_recommendation.import_session_id,
            "batch:201-202",
        )
        self.assertEqual(result.commerce_recommendation.asset_ids, (201, 202))
        self.assertIsNotNone(result.product_strategy_result)
        self.assertIs(
            result.organization_result.product_strategy_result,
            result.product_strategy_result,
        )
        self.assertIsNotNone(result.commerce_strategy_result)
        self.assertIs(
            result.organization_result.commerce_strategy_result,
            result.commerce_strategy_result,
        )
        self.assertEqual(len(product_strategy.calls), 3)
        self.assertEqual(product_strategy.calls[-1]["asset_ids"], (201, 202))
        self.assertIs(
            product_strategy.calls[-1]["experience_context"],
            result.experience_recommendation,
        )
        self.assertIs(
            product_strategy.calls[-1]["commerce_recommendation"],
            result.commerce_recommendation,
        )
        self.assertEqual(len(commerce_strategy.calls), 3)
        self.assertEqual(commerce_strategy.calls[-1]["asset_ids"], (201, 202))
        self.assertIs(
            commerce_strategy.calls[-1]["experience_context"],
            result.experience_recommendation,
        )
        self.assertIs(
            commerce_strategy.calls[-1]["commerce_intelligence"],
            result.commerce_recommendation,
        )
        self.assertIs(
            commerce_strategy.calls[-1]["product_strategy_result"],
            result.product_strategy_result,
        )
        self.assertEqual(
            result.commerce_recommendation.experience_asset_ids,
            (201, 202),
        )
        self.assertEqual(
            product_drafting.photo_set_calls,
            [
                {
                    "asset_ids": [201, 202],
                    "creator_profile_id": 2,
                    "commerce_recommendation": result.commerce_recommendation,
                }
            ],
        )
        self.assertEqual(result.publishing_readiness["asset_count"], 2)
        self.assertEqual(result.publishing_readiness["ready_asset_count"], 2)
        self.assertIsNotNone(result.organization_result)
        self.assertEqual(result.organization_result.asset_ids, (201, 202))
        self.assertEqual(result.organization_result.organization_type, "photo_set")
        self.assertTrue(result.organization_result.asset_library_visible)
        self.assertTrue(result.organization_result.local_vault_owned)
        self.assertIs(
            result.organization_result.experience_recommendation,
            result.experience_recommendation,
        )
        self.assertIs(
            result.organization_result.product_draft_result,
            result.product_draft_result,
        )
        self.assertEqual(result.organization_result.delivery_type, "PAID")
        self.assertEqual(len(result.legacy_results), 2)
        self.assertEqual(
            experience_intelligence.calls[-1]["import_session_id"],
            "batch:201-202",
        )

    def test_import_asset_consumes_creator_intent_contract(self):
        calls = []

        def classifier(**kwargs):
            calls.append(kwargs)
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "TEASE",
                "db_save_result": {"content_id": 250},
            }

        product_strategy = FakeProductStrategy()
        creator_intent = CreatorIntent.create(
            "SINGLE_ASSET",
            legacy_upload_intent="ppv_image",
            notes="Creator chose this as a single paid asset.",
        )
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=FakeProductDrafting(),
            publishing_service=FakePublishing(),
            asset_understanding_service=FakeAssetUnderstanding(),
            experience_intelligence_service=FakeExperienceIntelligence(),
            commerce_intelligence_service=FakeCommerceIntelligence(),
            product_strategy_service=product_strategy,
        )

        result = service.import_asset(
            media_path=Path("data/uploads/intent.jpg"),
            upload_intent="teaser_image",
            creator_intent=creator_intent,
            creator_profile_id=2,
        )

        self.assertTrue(result.success)
        self.assertIs(result.creator_intent, creator_intent)
        self.assertEqual(calls[0]["upload_intent"], "ppv_image")
        self.assertEqual(
            product_strategy.calls[0]["creator_intent"]["content_type"],
            "SINGLE_ASSET",
        )
        self.assertEqual(
            product_strategy.calls[0]["creator_intent"]["notes"],
            "Creator chose this as a single paid asset.",
        )

    def test_creator_intent_overrides_batch_package_type(self):
        next_id = 500

        def classifier(**kwargs):
            nonlocal next_id
            next_id += 1
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "TEASE",
                "db_save_result": {"content_id": next_id},
            }

        experience_intelligence = FakeExperienceIntelligence()
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=FakeProductDrafting(),
            publishing_service=FakePublishing(),
            asset_understanding_service=FakeAssetUnderstanding(),
            experience_intelligence_service=experience_intelligence,
            commerce_intelligence_service=FakeCommerceIntelligence(),
        )

        result = service.import_asset_batch(
            media_items=[
                {"media_path": Path("data/uploads/one.jpg")},
                {"media_path": Path("data/uploads/two.jpg")},
            ],
            upload_intent="teaser_image",
            creator_intent=CreatorIntent.create("STORY"),
            creator_profile_id=2,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.creator_intent.content_type, CreatorContentType.STORY)
        self.assertEqual(result.experience_recommendation.package_type, "story")
        self.assertEqual(
            experience_intelligence.calls[-1]["package_type"],
            "story",
        )

    def test_import_asset_creates_missing_product_draft_from_commerce(self):
        def classifier(**kwargs):
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "PREMIUM",
                "db_save_result": {"content_id": 303},
            }

        product_drafting = FakeProductDrafting()
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=product_drafting,
            publishing_service=FakePublishing(),
            asset_understanding_service=FakeAssetUnderstanding(),
            experience_intelligence_service=FakeExperienceIntelligence(),
            commerce_intelligence_service=FakeCommerceIntelligence(),
        )

        result = service.import_asset(
            media_path=Path("data/uploads/ppv.jpg"),
            upload_intent="ppv_image",
            creator_profile_id=2,
            provider_upload_enabled=False,
        )

        self.assertEqual(result.product_draft_result["product_id"], "product-303")
        self.assertEqual(len(product_drafting.single_asset_calls), 1)
        self.assertEqual(product_drafting.single_asset_calls[0]["asset_id"], 303)
        self.assertIs(
            product_drafting.single_asset_calls[0]["commerce_recommendation"],
            result.commerce_recommendation,
        )
        self.assertIs(
            result.organization_result.product_draft_result,
            result.product_draft_result,
        )

    def test_import_asset_uses_content_intelligence_for_understanding(self):
        def classifier(**kwargs):
            return {
                "success": True,
                "upload_intent": kwargs["upload_intent"],
                "final_classification": "TEASE",
                "db_save_result": {"content_id": 404},
            }

        asset_understanding = FakeAssetUnderstanding()
        content_intelligence = FakeContentIntelligence(asset_understanding)
        service = AIImportWorkflowService(
            classifier=classifier,
            asset_repository=FakeAssets(),
            product_drafting_service=FakeProductDrafting(),
            publishing_service=FakePublishing(),
            asset_understanding_service=asset_understanding,
            content_intelligence_service=content_intelligence,
            experience_intelligence_service=FakeExperienceIntelligence(),
            commerce_intelligence_service=FakeCommerceIntelligence(),
        )

        result = service.import_asset(
            media_path=Path("data/uploads/tease.jpg"),
            upload_intent="teaser_image",
            creator_profile_id=2,
            provider_upload_enabled=False,
        )

        self.assertEqual(len(content_intelligence.build_calls), 1)
        self.assertEqual(content_intelligence.get_calls, [])
        self.assertIsNotNone(result.content_intelligence)
        self.assertIs(
            result.content_intelligence.asset_understanding,
            result.asset_understanding,
        )
        self.assertEqual(result.asset_understanding.asset_id, 404)
        self.assertEqual(result.asset_understanding.source, "asset")


if __name__ == "__main__":
    unittest.main()
