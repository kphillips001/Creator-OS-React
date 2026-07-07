import unittest
from types import SimpleNamespace

from app.models.experience import ExperienceType
from app.models.product import ProductDeliveryType, ProductType
from app.services.content_intelligence_service import ContentIntelligenceService
from app.services.commerce_intelligence_service import CommerceIntelligenceService


def understanding(
    asset_id,
    *,
    media_type="image",
    classification="VIP",
    confidence=0.91,
    intensity="medium",
    tags=("lace", "vip"),
    themes=("lingerie",),
    summary="Soft mirror set.",
    nudity_level=None,
    is_explicit=False,
    risk_flags=(),
    runtime=True,
    review=False,
):
    return SimpleNamespace(
        identity=SimpleNamespace(
            asset_id=asset_id,
            original_filename=f"asset_{asset_id}.jpg",
            file_name=f"asset_{asset_id}.jpg",
        ),
        media=SimpleNamespace(media_type=media_type),
        visual=SimpleNamespace(
            suggested_tags=tags,
            detected_themes=themes,
            summary=summary,
            setting="bedroom",
            outfit="lace set",
            mood="soft",
            activity="mirror pose",
        ),
        classification=SimpleNamespace(
            final_classification=classification,
            confidence=confidence,
        ),
        safety=SimpleNamespace(
            sexual_intensity=intensity,
            nudity_level=nudity_level,
            is_explicit=is_explicit,
            risk_flags=risk_flags,
        ),
        readiness=SimpleNamespace(
            has_runtime_media=runtime,
            needs_review=review,
        ),
    )


class CommerceIntelligenceServiceTests(unittest.TestCase):
    def test_single_image_recommendation_uses_asset_understanding(self):
        service = CommerceIntelligenceService()

        result = service.recommend(asset_understanding=understanding(1))

        self.assertEqual(result.source_type, "asset")
        self.assertEqual(result.asset_ids, (1,))
        self.assertEqual(result.product_type, ProductType.SINGLE_IMAGE)
        self.assertEqual(result.delivery_type, ProductDeliveryType.PAID)
        self.assertEqual(result.suggested_name, "Asset 1")
        self.assertIn("lace", result.suggested_tags)
        self.assertIn("lingerie", result.suggested_themes)
        self.assertIn("bedroom", result.suggested_keywords)
        self.assertEqual(result.price.suggested_price_cents, 2999)
        self.assertEqual(result.publishing.status, "ready_for_draft")
        self.assertEqual(result.metadata["delivery_type"], "PAID")

    def test_photo_set_uses_experience_recommendation(self):
        service = CommerceIntelligenceService()
        experience = SimpleNamespace(
            experience_type=ExperienceType.PHOTOSHOOT,
            is_collection=True,
            suggested_name="Lace Photo Set",
            suggested_summary="Photoshoot containing two assets.",
            suggested_themes=("canonical-theme",),
            suggested_keywords=("canonical-keyword", "bedroom"),
            mood="soft",
            setting="studio",
            visual_continuity={"setting": "studio"},
            story_progression={"activity_progression": False},
            technical_continuity={"mime_types": ("image/jpeg",)},
            intelligence_metadata={"asset_count": 2},
            intelligence_provenance={
                "source": "experience_intelligence_service",
                "new_ai_analysis": False,
            },
        )

        result = service.recommend(
            asset_understandings=[understanding(1), understanding(2)],
            experience_recommendation=experience,
        )

        self.assertEqual(result.source_type, "experience")
        self.assertEqual(result.asset_ids, (1, 2))
        self.assertEqual(result.product_type, ProductType.PHOTO_SET)
        self.assertEqual(result.suggested_name, "Lace Photo Set")
        self.assertEqual(
            result.suggested_description,
            "Photoshoot containing two assets.",
        )
        self.assertEqual(result.suggested_themes, ("canonical-theme",))
        self.assertEqual(
            result.suggested_keywords,
            ("canonical-keyword", "bedroom"),
        )
        self.assertEqual(
            result.metadata["experience_intelligence"]["setting"],
            "studio",
        )
        self.assertFalse(
            result.metadata["experience_intelligence"][
                "intelligence_provenance"
            ]["new_ai_analysis"]
        )
        self.assertEqual(result.price.suggested_price_cents, 4499)

    def test_safe_teaser_recommends_free_delivery(self):
        service = CommerceIntelligenceService()

        result = service.recommend(
            asset_understanding=understanding(
                3,
                classification="TEASE",
                confidence=0.88,
                intensity="low",
                tags=("teaser", "conversation starter"),
                themes=("preview",),
                summary="Safe preview for relationship building.",
            )
        )

        self.assertEqual(result.product_type, ProductType.SINGLE_IMAGE)
        self.assertEqual(result.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(result.price.suggested_price_cents, 0)
        self.assertEqual(result.price.min_price_cents, 0)
        self.assertEqual(result.price.max_price_cents, 0)
        self.assertEqual(result.metadata["delivery_type"], "FREE")
        self.assertGreaterEqual(
            result.metadata["delivery_type_scores"]["free"],
            result.metadata["delivery_type_scores"]["paid"],
        )
        self.assertIn(
            "delivery_type_recommendation",
            {item.reason for item in result.evidence},
        )

    def test_explicit_premium_recommends_paid_delivery(self):
        service = CommerceIntelligenceService()

        result = service.recommend(
            asset_understandings=[
                understanding(
                    4,
                    classification="PREMIUM",
                    intensity="high",
                    tags=("premium", "exclusive"),
                    themes=("gallery",),
                    nudity_level="explicit_nudity",
                    is_explicit=True,
                    risk_flags=("nsfw",),
                ),
                understanding(
                    5,
                    classification="VIP",
                    intensity="medium",
                    tags=("vip",),
                    themes=("bundle",),
                ),
            ]
        )

        self.assertEqual(result.product_type, ProductType.PHOTO_SET)
        self.assertEqual(result.delivery_type, ProductDeliveryType.PAID)
        self.assertGreater(result.price.suggested_price_cents, 0)
        self.assertGreater(
            result.metadata["delivery_type_scores"]["paid"],
            result.metadata["delivery_type_scores"]["free"],
        )

    def test_missing_runtime_media_requires_attention(self):
        service = CommerceIntelligenceService()

        result = service.recommend(
            asset_understanding=understanding(9, runtime=False)
        )

        self.assertEqual(result.publishing.status, "requires_attention")
        self.assertEqual(result.publishing.action, "resolve_media")

    def test_recommendation_accepts_content_intelligence_read_model(self):
        service = CommerceIntelligenceService()
        content = ContentIntelligenceService().build_from_understanding(
            understanding(12)
        )

        result = service.recommend(asset_understanding=content)

        self.assertEqual(result.asset_ids, (12,))
        self.assertEqual(result.product_type, ProductType.SINGLE_IMAGE)
        self.assertEqual(result.delivery_type, ProductDeliveryType.PAID)
        self.assertIn("lace", result.suggested_tags)
        self.assertIn("bedroom", result.suggested_keywords)


if __name__ == "__main__":
    unittest.main()
