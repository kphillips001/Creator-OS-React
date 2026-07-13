import unittest
import sys
import types
from importlib.util import find_spec

fake_psycopg = types.ModuleType("psycopg")
fake_psycopg_types = types.ModuleType("psycopg.types")
fake_psycopg_json = types.ModuleType("psycopg.types.json")
fake_psycopg_rows = types.ModuleType("psycopg.rows")
fake_psycopg.connect = lambda *args, **kwargs: None
fake_psycopg_json.Jsonb = lambda value: value
fake_psycopg_rows.dict_row = object()
sys.modules.setdefault("psycopg", fake_psycopg)
sys.modules.setdefault("psycopg.types", fake_psycopg_types)
sys.modules.setdefault("psycopg.types.json", fake_psycopg_json)
sys.modules.setdefault("psycopg.rows", fake_psycopg_rows)

from app.contracts.cms import (
    AvailableProduct,
    CustomerProgress,
    DeliveryMode,
    DeliveryPermission,
    DeliverySubjectType,
    OfferCandidate,
    OfferKind,
    ProductAvailability,
    ProductDeliveryType,
)
from app.engine.decision_engine import DecisionEngine
from app.services.cms_contract_service import CMSContractService


class FakeLogger:
    def __init__(self):
        self.messages = []

    def info(self, message):
        self.messages.append(message)


class FakeSettings:
    DEFAULT_PERSONA = "ava"


class FakeProductRecommendationService:
    def __init__(self):
        self.last_offer_candidate_contract = OfferCandidate(
            offer_id="offer-product-1",
            offer_kind=OfferKind.VIP,
            title="VIP Set",
            product=AvailableProduct(
                product_id="product-1",
                title="VIP Set",
                product_type="photo_set",
                availability=ProductAvailability.AVAILABLE,
                price_cents=2500,
            ),
            delivery_permission=DeliveryPermission(
                subject_id="product-1",
                subject_type=DeliverySubjectType.PRODUCT,
                delivery_mode=DeliveryMode.PAID,
                allowed=True,
                price_cents=2500,
            ),
            score=42,
            reason="active_product",
        )
        self.calls = []

    def get_content(self, offer_type, persona, working_memory):
        self.calls.append((offer_type, persona, working_memory))
        return {
            "source": "product",
            "product_id": "product-1",
            "tag": "product_product-1",
            "type": offer_type,
            "persona": persona,
        }


class DecisionEngineCMSContractAdoptionTests(unittest.TestCase):
    def test_select_cms_content_receives_contract_and_keeps_legacy_payload(self):
        engine = object.__new__(DecisionEngine)
        engine.logger = FakeLogger()
        engine.settings = FakeSettings()
        engine.cms_contract_service = CMSContractService()
        engine.product_recommendation_service = (
            FakeProductRecommendationService()
        )
        engine.last_cms_offer_candidate_contract = None
        working_memory = {"creator_profile_id": 7}

        payload = engine._select_cms_content("vip_offer", working_memory)

        self.assertIsInstance(
            engine.last_cms_offer_candidate_contract,
            OfferCandidate,
        )
        self.assertEqual(
            engine.last_cms_offer_candidate_contract.product.product_id,
            "product-1",
        )
        self.assertEqual(payload["source"], "product")
        self.assertEqual(payload["product_id"], "product-1")
        self.assertEqual(
            engine.product_recommendation_service.calls,
            [("vip", "ava", working_memory)],
        )
        self.assertIsInstance(
            engine.last_cms_customer_progress_contract,
            CustomerProgress,
        )

    def test_decision_engine_content_reads_prefer_cms_contract(self):
        engine = object.__new__(DecisionEngine)
        engine.last_cms_offer_candidate_contract = OfferCandidate(
            offer_id="offer-product-2",
            offer_kind=OfferKind.PREMIUM,
            title="Contract Title",
            product=AvailableProduct(
                product_id="product-2",
                title="Contract Product",
                product_type="photo_set",
                availability=ProductAvailability.AVAILABLE,
                delivery_type=ProductDeliveryType.FREE,
                description="Contract caption",
                price_cents=4500,
            ),
            price_cents=4500,
            delivery_permission=DeliveryPermission(
                subject_id="product-2",
                subject_type=DeliverySubjectType.PRODUCT,
                delivery_mode=DeliveryMode.INCLUDED,
                allowed=True,
                requires_payment=False,
                price_cents=0,
            ),
            score=90,
            reason="contract_read",
        )
        legacy_payload = {
            "product_id": "legacy-product",
            "tag": "legacy_tag",
            "type": "tease",
            "tier": "low",
            "price": 1,
            "caption": "Legacy caption",
            "fanvue_link": "https://example.invalid/compat",
            "delivery_type": "PAID",
            "delivery_permission_mode": "paid",
            "delivery_requires_payment": True,
        }

        self.assertEqual(
            engine._cms_content_product_id(legacy_payload),
            "product-2",
        )
        self.assertEqual(
            engine._cms_content_tag(legacy_payload),
            "product_product-2",
        )
        self.assertEqual(engine._cms_content_offer_type(legacy_payload), "premium")
        self.assertEqual(engine._cms_content_price(legacy_payload), 45)
        self.assertEqual(engine._cms_content_tier(legacy_payload), "premium")
        self.assertEqual(engine._cms_content_delivery_type(legacy_payload), "FREE")
        self.assertEqual(
            engine._cms_content_delivery_mode(legacy_payload),
            "included",
        )
        self.assertFalse(engine._cms_content_requires_payment(legacy_payload))
        self.assertEqual(
            engine._cms_content_caption(legacy_payload),
            "Contract caption",
        )
        self.assertTrue(engine._cms_content_deliverable(legacy_payload))
        self.assertEqual(
            engine._compat_content_link(legacy_payload),
            "https://example.invalid/compat",
        )

        legacy_payload["fanvue_link"] = "https://example.invalid/changed"
        legacy_payload["price"] = 1
        legacy_payload["delivery_type"] = "PAID"
        legacy_payload["delivery_permission_mode"] = "paid"
        legacy_payload["delivery_requires_payment"] = True
        self.assertEqual(engine._cms_content_price(legacy_payload), 45)
        self.assertEqual(engine._cms_content_delivery_type(legacy_payload), "FREE")
        self.assertEqual(
            engine._cms_content_delivery_mode(legacy_payload),
            "included",
        )
        self.assertFalse(engine._cms_content_requires_payment(legacy_payload))
        self.assertTrue(engine._cms_content_deliverable(legacy_payload))
        self.assertEqual(
            engine._compat_content_link(legacy_payload),
            "https://example.invalid/changed",
        )

    def test_obsolete_product_recommendation_wrapper_is_removed(self):
        self.assertIsNone(find_spec("app.models.product_recommendation"))


if __name__ == "__main__":
    unittest.main()
