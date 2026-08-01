import unittest
import sys
import types
from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, timezone
from uuid import uuid4

from app.models.product import (
    FulfillmentStrategy,
    Product,
    ProductFulfillmentStatus,
    ProductStatus,
    ProductType,
)
from app.models.product_offer import ProductOffer
from app.contracts.cms import DeliveryMode, OfferCandidate, ProductDeliveryType


@contextmanager
def _unused_db_connection():
    raise AssertionError("Unit tests should use fake repositories.")


fake_database = types.ModuleType("app.database")
fake_database.get_db_connection = _unused_db_connection
sys.modules.setdefault("app.database", fake_database)

from app.services.product_recommendation_service import ProductRecommendationService


def product(
    *,
    status=ProductStatus.ACTIVE,
    price_cents=2500,
    creator_profile_id=7,
    themes=(),
    product_type=ProductType.SINGLE_IMAGE,
    media_link="https://example.test/product",
    delivery_type=None,
):
    now = datetime.now(timezone.utc)
    metadata = {"source": "unit"}
    if delivery_type is not None:
        metadata["delivery_type"] = delivery_type
    return Product(
        id=uuid4(),
        creator_profile_id=creator_profile_id,
        legacy_content_item_id=None,
        internal_name="test-product",
        display_name="Test Product",
        description="Runtime bridge product",
        product_type=product_type,
        status=status,
        price_cents=price_cents,
        base_price_cents=price_cents,
        min_price_cents=price_cents,
        max_price_cents=price_cents,
        currency="USD",
        media_link=media_link,
        tags=("test",),
        themes=themes,
        metadata=metadata,
        activation_source="unit",
        activation_reason="unit test",
        activated_at=now,
        created_at=now,
        updated_at=now,
    )


class FakeProductRepository:
    def __init__(self, products):
        self.products = products
        self.calls = []

    def list_products(self, **kwargs):
        self.calls.append(kwargs)
        return [
            value for value in self.products
            if value.creator_profile_id == kwargs["creator_profile_id"]
            and value.status == kwargs["status"]
        ]


class FakeEntitlementRepository:
    def __init__(self, entitled_product_ids=()):
        self.entitled_product_ids = {str(value) for value in entitled_product_ids}

    def has_active_entitlement_for_legacy_user(self, **kwargs):
        return str(kwargs["product_id"]) in self.entitled_product_ids


class FakeOwnershipIntelligence:
    def __init__(self, entitled_product_ids=()):
        self.entitled_product_ids = {
            str(value) for value in entitled_product_ids
        }

    def answer(self, identity):
        return types.SimpleNamespace(
            identity=identity, evidence_sufficient=True,
            owned_product_ids=tuple(self.entitled_product_ids),
        )

    def owns_product(self, answer, product_id):
        return str(product_id) in {
            str(value) for value in answer.owned_product_ids
        }


class FakeContentService:
    def __init__(self):
        self.called = False

    def get_content(self, offer_type, persona, user_memory):
        self.called = True
        return {
            "tag": "cms_fallback",
            "type": offer_type,
            "persona": persona,
            "source": "cms",
        }


class ProductRecommendationServiceTests(unittest.TestCase):
    def test_product_ownership_uses_canonical_intelligence_only(self):
        source = Path(
            "app/services/product_recommendation_service.py"
        ).read_text(encoding="utf-8")
        self.assertIn("OwnershipIntelligenceService", source)
        self.assertNotIn("has_active_entitlement_for_legacy_user", source)
        self.assertNotIn("CustomerEntitlementRepository", source)

    def test_active_product_returns_legacy_compatible_payload(self):
        selected = product(themes=("GFE",))
        fallback = FakeContentService()
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([selected]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=fallback,
        )

        payload = service.get_content(
            "vip",
            "ava",
            {
                "creator_profile_id": 7,
                "fanvue_account_id": 1,
                "fanvue_user_id": "22",
                "preferred_content_theme": "GFE",
            },
        )

        self.assertFalse(fallback.called)
        self.assertEqual(payload["source"], "product")
        self.assertEqual(payload["product_id"], str(selected.id))
        self.assertEqual(payload["tag"], f"product_{selected.id}")
        self.assertEqual(payload["content_item_id"], None)
        self.assertEqual(payload["price"], 25)
        self.assertEqual(payload["checkout_url"], selected.media_link)
        self.assertEqual(payload["fanvue_link"], selected.media_link)
        self.assertEqual(
            payload["fulfillment_strategy"],
            FulfillmentStrategy.FANVUE_PAID_CHAT.value,
        )
        self.assertEqual(
            payload["recommended_fulfillment_strategy"],
            FulfillmentStrategy.FANVUE_PAID_CHAT.value,
        )
        self.assertEqual(
            payload["fulfillment_status"],
            ProductFulfillmentStatus.READY.value,
        )
        self.assertEqual(payload["delivery_type"], ProductDeliveryType.PAID.value)
        self.assertEqual(payload["delivery_permission_mode"], DeliveryMode.PAID.value)
        self.assertTrue(payload["delivery_requires_payment"])
        self.assertTrue(payload["delivery_allowed"])
        self.assertIn("theme_match", payload["recommendation_reason"])
        self.assertIsInstance(
            service.last_offer_candidate_contract,
            OfferCandidate,
        )
        self.assertEqual(
            service.last_offer_candidate_contract.product.product_id,
            str(selected.id),
        )
        self.assertEqual(
            service.last_offer_candidate_contract.product.delivery_type,
            ProductDeliveryType.PAID,
        )
        self.assertTrue(
            service.last_offer_candidate_contract.delivery_permission.allowed
        )

    def test_free_delivery_type_flows_through_contract_permission(self):
        selected = product(
            price_cents=0,
            delivery_type=ProductDeliveryType.FREE.value,
        )
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([selected]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=FakeContentService(),
        )

        payload = service.get_content(
            "tease",
            "ava",
            {"creator_profile_id": 7},
        )
        contract = service.last_offer_candidate_contract

        self.assertEqual(payload["delivery_type"], ProductDeliveryType.FREE.value)
        self.assertEqual(
            payload["delivery_permission_mode"],
            DeliveryMode.INCLUDED.value,
        )
        self.assertFalse(payload["delivery_requires_payment"])
        self.assertTrue(payload["delivery_allowed"])
        self.assertEqual(contract.product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(
            contract.delivery_permission.delivery_mode,
            DeliveryMode.INCLUDED,
        )
        self.assertFalse(contract.delivery_permission.requires_payment)

    def test_offer_candidate_contract_preserves_recommendation_decision(self):
        selected = product(themes=("GFE",))
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([selected]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=FakeContentService(),
        )

        contract = service.get_offer_candidate(
            offer_type="vip",
            persona="ava",
            user_memory={
                "creator_profile_id": 7,
                "preferred_content_theme": "GFE",
            },
        )

        self.assertIsInstance(contract, OfferCandidate)
        self.assertEqual(contract.product.product_id, str(selected.id))
        self.assertEqual(contract.product.delivery_type, ProductDeliveryType.PAID)
        self.assertEqual(contract.offer_kind.value, "vip")
        self.assertIn("theme_match", contract.reason)
        self.assertTrue(contract.is_deliverable)

    def test_legacy_content_payload_adapter_remains_available(self):
        selected = product(themes=("GFE",))
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([selected]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=FakeContentService(),
        )
        offer, contract = service.recommend_contract(
            offer_type="vip",
            persona="ava",
            user_memory={"creator_profile_id": 7},
        )

        payload = service.build_legacy_content_payload(
            contract,
            "ava",
            source_offer=offer,
        )
        alias_payload = service.offer_candidate_to_legacy_payload(
            contract,
            "ava",
            source_offer=offer,
        )

        self.assertEqual(payload, alias_payload)
        self.assertEqual(payload["fanvue_link"], selected.media_link)
        self.assertEqual(payload["delivery_type"], ProductDeliveryType.PAID.value)
        self.assertEqual(payload["product_id"], str(selected.id))

    def test_recommendation_returns_default_fulfillment_strategy_by_product_type(self):
        cases = {
            ProductType.SINGLE_IMAGE: FulfillmentStrategy.FANVUE_PAID_CHAT,
            ProductType.SINGLE_VIDEO: FulfillmentStrategy.FANVUE_PAID_CHAT,
            ProductType.PHOTO_SET: FulfillmentStrategy.FANVUE_PAID_CHAT,
            ProductType.VIDEO_SET: FulfillmentStrategy.FANVUE_PAID_CHAT,
            ProductType.STORY: FulfillmentStrategy.FANVUE_PAID_POST,
            ProductType.SESSION: FulfillmentStrategy.FANVUE_PAID_CHAT,
            ProductType.BUNDLE: FulfillmentStrategy.MANUAL_FUTURE,
        }

        for product_type, strategy in cases.items():
            with self.subTest(product_type=product_type):
                selected = product(product_type=product_type)
                service = ProductRecommendationService(
                    product_repository=FakeProductRepository([selected]),
                    ownership_intelligence=FakeOwnershipIntelligence(),
                    content_service=FakeContentService(),
                )

                recommendation = service.recommend(
                    offer_type="vip",
                    persona="ava",
                    user_memory={"creator_profile_id": 7},
                )

                self.assertIsNotNone(recommendation)
                self.assertIsInstance(recommendation, ProductOffer)
                self.assertEqual(recommendation.fulfillment_strategy, strategy)
                self.assertEqual(
                    recommendation.to_legacy_payload("ava")[
                        "recommended_fulfillment_strategy"
                    ],
                    strategy.value,
                )
                self.assertEqual(
                    recommendation.to_legacy_payload("ava")["delivery_type"],
                    ProductDeliveryType.PAID.value,
                )

    def test_entitled_and_recent_products_fall_back_to_content_service(self):
        entitled = product()
        recent = product()
        fallback = FakeContentService()
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([entitled, recent]),
            ownership_intelligence=FakeOwnershipIntelligence([entitled.id]),
            content_service=fallback,
        )

        payload = service.get_content(
            "vip",
            "ava",
            {
                "creator_profile_id": 7,
                "fanvue_account_id": 1,
                "fanvue_user_id": "22",
                "last_offer_content_tag": f"product_{recent.id}",
            },
        )

        self.assertTrue(fallback.called)
        self.assertEqual(payload["source"], "cms")
        self.assertEqual(payload["tag"], "cms_fallback")

    def test_active_product_without_media_link_is_not_recommended(self):
        not_ready = product(media_link=None)
        fallback = FakeContentService()
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([not_ready]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=fallback,
        )

        payload = service.get_content(
            "vip",
            "ava",
            {"creator_profile_id": 7},
        )

        self.assertEqual(not_ready.fulfillment_status, ProductFulfillmentStatus.NOT_READY)
        self.assertTrue(fallback.called)
        self.assertEqual(payload["source"], "cms")

    def test_missing_creator_profile_falls_back(self):
        fallback = FakeContentService()
        service = ProductRecommendationService(
            product_repository=FakeProductRepository([product()]),
            ownership_intelligence=FakeOwnershipIntelligence(),
            content_service=fallback,
        )

        payload = service.get_content("vip", "ava", {})

        self.assertTrue(fallback.called)
        self.assertEqual(payload["source"], "cms")


if __name__ == "__main__":
    unittest.main()
