import unittest
from dataclasses import fields, is_dataclass
from pathlib import Path

from app.contracts import (
    AvailableExperience,
    AvailableProduct,
    CustomerIdentity,
    CustomerProgress,
    DeliveryMode,
    DeliveryPermission,
    DeliverySubjectType,
    ExperienceKind,
    OfferCandidate,
    OfferKind,
    ProductAvailability,
    ProductDeliveryType,
    PublishingState,
    PublishingStatus,
    RuntimeCustomerContext,
)
import app.contracts.cms as cms_contracts


CONTRACT_CLASSES = (
    AvailableExperience,
    AvailableProduct,
    CustomerIdentity,
    CustomerProgress,
    DeliveryPermission,
    OfferCandidate,
    PublishingStatus,
    RuntimeCustomerContext,
)

FORBIDDEN_FIELD_MARKERS = (
    "content_item",
    "fanvue",
    "local_vault",
    "media_link",
    "product_asset",
    "provider",
    "repository",
    "runtime_media",
    "sql",
    "url",
)


class CmsContractTests(unittest.TestCase):
    def test_every_contract_can_be_instantiated(self):
        identity = CustomerIdentity(
            customer_id="customer-1",
            creator_id="creator-1",
            channel="chat",
        )
        runtime_context = RuntimeCustomerContext(
            identity=identity,
            traits={"buyer_tier": "warm"},
            conversation_state={"intent_score": 42},
        )
        experience = AvailableExperience(
            experience_id="experience-1",
            experience_kind=ExperienceKind.PHOTOSHOOT,
            title="Soft mirror set",
            ordered_media_refs=("media-2", "media-1"),
            tags=("soft", "mirror"),
        )
        product = AvailableProduct(
            product_id="product-1",
            title="VIP set",
            product_type="photo_set",
            availability=ProductAvailability.AVAILABLE,
            experience_id=experience.experience_id,
            price_cents=2999,
        )
        publishing_status = PublishingStatus(
            subject_id=product.product_id,
            subject_type=DeliverySubjectType.PRODUCT,
            state=PublishingState.PUBLISHED,
            is_deliverable=True,
            available_delivery_modes=(DeliveryMode.PAID,),
        )
        permission = DeliveryPermission(
            subject_id=product.product_id,
            subject_type=DeliverySubjectType.PRODUCT,
            delivery_mode=DeliveryMode.PAID,
            allowed=True,
            requires_payment=True,
            price_cents=2999,
        )
        progress = CustomerProgress(
            customer_id=identity.customer_id,
            seen_experience_ids=("experience-0",),
            owned_product_ids=("product-0",),
            last_offer_kind=OfferKind.VIP,
        )
        offer = OfferCandidate(
            offer_id="offer-1",
            offer_kind=OfferKind.VIP,
            title="Unlock the VIP set",
            product=product,
            experience=experience,
            delivery_permission=permission,
            publishing_status=publishing_status,
            price_cents=2999,
            score=88,
        )

        self.assertEqual(runtime_context.identity.customer_id, "customer-1")
        self.assertEqual(experience.ordered_media_refs, ("media-2", "media-1"))
        self.assertEqual(product.currency, "USD")
        self.assertEqual(product.delivery_type, ProductDeliveryType.PAID)
        self.assertTrue(publishing_status.is_deliverable)
        self.assertTrue(permission.allowed)
        self.assertTrue(progress.has_seen_experience("experience-0"))
        self.assertTrue(progress.owns_product("product-0"))
        self.assertTrue(offer.is_deliverable)

    def test_contracts_are_dataclasses(self):
        for contract in CONTRACT_CLASSES:
            self.assertTrue(is_dataclass(contract), contract.__name__)

    def test_string_inputs_are_coerced_to_stable_enums_and_tuples(self):
        experience = AvailableExperience(
            experience_id="experience-2",
            experience_kind="story",
            title="Story",
            ordered_media_refs="media-1",
            tags=["story"],
        )
        product = AvailableProduct(
            product_id="product-2",
            title="Single",
            product_type="single_image",
            availability="available",
            delivery_type="FREE",
            currency="usd",
        )
        permission = DeliveryPermission(
            subject_id="product-2",
            subject_type="product",
            delivery_mode="preview",
            allowed=False,
        )

        self.assertEqual(experience.experience_kind, ExperienceKind.STORY)
        self.assertEqual(experience.ordered_media_refs, ("media-1",))
        self.assertEqual(experience.tags, ("story",))
        self.assertEqual(product.availability, ProductAvailability.AVAILABLE)
        self.assertEqual(product.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(product.currency, "USD")
        self.assertEqual(permission.delivery_mode, DeliveryMode.PREVIEW)

    def test_optional_fields_have_safe_defaults(self):
        progress = CustomerProgress(customer_id="customer-2")
        offer = OfferCandidate(
            offer_id="offer-2",
            offer_kind=OfferKind.TEASE,
            title="Preview",
        )
        experience = AvailableExperience(
            experience_id="experience-3",
            experience_kind=ExperienceKind.STANDALONE,
            title="Preview asset",
        )

        self.assertEqual(progress.seen_offer_ids, ())
        self.assertEqual(progress.signals, {})
        self.assertFalse(offer.is_deliverable)
        self.assertEqual(offer.presentation, {})
        self.assertIsNone(experience.cover_media_ref)
        self.assertEqual(experience.presentation, {})

    def test_contract_field_names_are_provider_neutral(self):
        for contract in CONTRACT_CLASSES:
            field_names = {field.name for field in fields(contract)}
            lowered = " ".join(sorted(field_names)).lower()
            for marker in FORBIDDEN_FIELD_MARKERS:
                self.assertNotIn(
                    marker,
                    lowered,
                    f"{contract.__name__} exposes forbidden marker {marker}",
                )

    def test_contract_module_does_not_import_cms_implementation_layers(self):
        source = Path(cms_contracts.__file__).read_text(encoding="utf-8")

        forbidden_imports = (
            "app.models",
            "app.repositories",
            "app.services",
            "RuntimeMediaResolver",
            "ProductAsset",
            "content_items",
        )
        for forbidden in forbidden_imports:
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
