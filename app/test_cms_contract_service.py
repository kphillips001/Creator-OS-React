import unittest
from dataclasses import asdict, is_dataclass
from datetime import datetime
from uuid import uuid4

from app.contracts.cms import (
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
from app.models.experience import Experience, ExperienceType
from app.models.product import (
    FulfillmentStrategy,
    Product,
    ProductFulfillmentStatus,
    ProductStatus,
    ProductType,
)
from app.models.product_offer import ProductOffer
from app.services.cms_contract_service import CMSContractService


FORBIDDEN_BOUNDARY_MARKERS = (
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


class FakeExperienceService:
    def __init__(self, experience):
        self.experience = experience
        self.calls = []

    def get_experience(self, product_id, *, creator_profile_id=None):
        self.calls.append((product_id, creator_profile_id))
        return self.experience


class FakeProductRepository:
    def __init__(self, product):
        self.product = product

    def get_by_id(self, product_id):
        return self.product if str(product_id) == str(self.product.id) else None


class FakePublishingService:
    def __init__(self, record):
        self.record = record

    def get_by_product_id(self, product_id):
        return self.record


class CMSContractServiceTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 7, 1, 12, 0, 0)
        self.product = Product(
            id=uuid4(),
            creator_profile_id=7,
            legacy_content_item_id=123,
            internal_name="mirror-set",
            display_name="Mirror Set",
            description="A polished gallery set.",
            product_type=ProductType.PHOTO_SET,
            status=ProductStatus.ACTIVE,
            price_cents=2999,
            base_price_cents=2999,
            min_price_cents=None,
            max_price_cents=None,
            currency="usd",
            media_link="https://example.invalid/legacy-checkout",
            tags=("mirror", "soft"),
            themes=("bedroom",),
            metadata={
                "experience_id": "experience-1",
                "sales_angle": "soft_unlock",
                "provider_output_url": "https://example.invalid/hidden",
                "local_vault_path": "C:/hidden",
            },
            activation_source=None,
            activation_reason=None,
            activated_at=None,
            created_at=self.now,
            updated_at=self.now,
            fulfillment_strategy=FulfillmentStrategy.FANVUE_PAID_CHAT,
            fulfillment_status=ProductFulfillmentStatus.READY,
        )
        self.experience = Experience(
            experience_id="experience-1",
            experience_type=ExperienceType.PHOTOSHOOT,
            title="Mirror shoot",
            description="Three image set.",
            cover_asset_id=11,
            asset_ids=(11, 12, 13),
            asset_order=(13, 11, 12),
            metadata={
                "tags": ("mirror",),
                "themes": ("bedroom",),
                "classification": "VIP",
                "chapter": "after dark",
                "provider_url": "https://example.invalid/hidden",
            },
            created_at=self.now,
            updated_at=self.now,
        )
        self.service = CMSContractService(
            experience_service=FakeExperienceService(self.experience),
            product_repository=FakeProductRepository(self.product),
            publishing_service=FakePublishingService(
                {
                    "provider_status": "ready",
                    "provider_output_url": "https://example.invalid/hidden",
                    "updated_at": self.now,
                }
            ),
        )

    def test_builds_available_product_contract(self):
        contract = self.service.build_available_product(self.product)

        self.assertIsInstance(contract, AvailableProduct)
        self.assertTrue(is_dataclass(contract))
        self.assertEqual(contract.product_id, str(self.product.id))
        self.assertEqual(contract.product_type, "photo_set")
        self.assertEqual(contract.availability, ProductAvailability.AVAILABLE)
        self.assertEqual(contract.delivery_type, ProductDeliveryType.PAID)
        self.assertEqual(contract.price_cents, 2999)
        self.assertEqual(contract.currency, "USD")
        self.assertEqual(contract.offer_metadata, {
            "experience_id": "experience-1",
            "experience_relationship": {
                "product_id": str(self.product.id),
                "experience_id": "experience-1",
                "role": "primary",
                "source": "cms_contract",
                "compatibility_experience_id": False,
            },
            "sales_angle": "soft_unlock",
        })

    def test_labels_compatibility_experience_ids_in_product_contract(self):
        product = Product(
            **{
                **self.product.__dict__,
                "metadata": {
                    **dict(self.product.metadata),
                    "experience_id": f"product:{self.product.id}",
                },
            }
        )

        contract = self.service.build_available_product(product)

        relationship = contract.offer_metadata["experience_relationship"]
        self.assertEqual(relationship["experience_id"], f"product:{self.product.id}")
        self.assertTrue(relationship["compatibility_experience_id"])

    def test_builds_available_experience_contract(self):
        contract = self.service.build_available_experience(self.experience)

        self.assertIsInstance(contract, AvailableExperience)
        self.assertEqual(contract.experience_kind, ExperienceKind.PHOTOSHOOT)
        self.assertEqual(contract.cover_media_ref, "asset:11")
        self.assertEqual(
            contract.ordered_media_refs,
            ("asset:13", "asset:11", "asset:12"),
        )
        self.assertEqual(contract.tags, ("mirror",))
        self.assertEqual(contract.themes, ("bedroom",))
        self.assertEqual(contract.presentation, {
            "classification": "VIP",
            "chapter": "after dark",
        })

    def test_projects_experience_intelligence_when_available(self):
        experience = Experience(
            **{
                **self.experience.__dict__,
                "metadata": {
                    "tags": ("mirror",),
                    "experience_intelligence": {
                        "suggested_themes": ("boudoir",),
                        "suggested_keywords": ("mirror", "studio"),
                        "mood": "soft",
                        "setting": "studio",
                        "visual_continuity": {"setting": "studio"},
                        "story_progression": {"filename_sequence": True},
                        "technical_continuity": {"mime_types": ("image/jpeg",)},
                        "intelligence_provenance": {
                            "source": "experience_intelligence_service",
                            "new_ai_analysis": False,
                        },
                    },
                },
            }
        )

        contract = self.service.build_available_experience(experience)

        self.assertEqual(contract.themes, ("boudoir",))
        self.assertEqual(
            contract.presentation["suggested_keywords"],
            ("mirror", "studio"),
        )
        self.assertEqual(contract.presentation["setting"], "studio")
        self.assertFalse(
            contract.presentation["intelligence_provenance"][
                "new_ai_analysis"
            ]
        )

    def test_retrieves_experience_through_experience_service(self):
        contract = self.service.get_available_experience(
            self.product.id,
            creator_profile_id=7,
        )

        self.assertIsInstance(contract, AvailableExperience)
        self.assertEqual(
            self.service.experience_service.calls,
            [(self.product.id, 7)],
        )

    def test_builds_publishing_status_contract(self):
        contract = self.service.get_publishing_status(self.product.id)

        self.assertIsInstance(contract, PublishingStatus)
        self.assertEqual(contract.subject_id, str(self.product.id))
        self.assertEqual(contract.subject_type, DeliverySubjectType.PRODUCT)
        self.assertEqual(contract.state, PublishingState.PUBLISHED)
        self.assertTrue(contract.is_deliverable)
        self.assertEqual(contract.available_delivery_modes, (DeliveryMode.PAID,))

    def test_builds_publishing_status_modes_from_delivery_type(self):
        contract = self.service.build_publishing_status(
            {
                "provider_status": "ready",
                "provider_output_url": "https://example.invalid/free",
                "delivery_type": "FREE",
            },
            subject_id=self.product.id,
        )

        self.assertTrue(contract.is_deliverable)
        self.assertEqual(
            contract.available_delivery_modes,
            (DeliveryMode.INCLUDED,),
        )

    def test_builds_customer_progress_contract(self):
        contract = self.service.build_customer_progress(
            "customer-1",
            user_memory={
                "seen_offer_ids": ["offer-1"],
                "seen_experience_ids": ["experience-0"],
                "preferred_content_theme": "bedroom",
                "last_offer_type": "vip_offer",
                "offer_count": "3",
                "purchase_count": 1,
                "signals": {
                    "intent_score": 90,
                    "fanvue_user_id": "hidden",
                    "profile_url": "https://example.invalid/hidden",
                },
            },
            owned_product_ids=[self.product.id],
            owned_experience_ids=["experience-owned"],
        )

        self.assertIsInstance(contract, CustomerProgress)
        self.assertEqual(contract.seen_offer_ids, ("offer-1",))
        self.assertEqual(contract.preferred_themes, ("bedroom",))
        self.assertEqual(contract.last_offer_kind, OfferKind.VIP)
        self.assertEqual(contract.offer_count, 3)
        self.assertTrue(contract.owns_product(str(self.product.id)))
        self.assertEqual(contract.signals, {"intent_score": 90})

    def test_builds_delivery_permission_contract(self):
        contract = self.service.build_delivery_permission(
            subject_id=self.product.id,
            product=self.product,
        )

        self.assertIsInstance(contract, DeliveryPermission)
        self.assertEqual(contract.subject_type, DeliverySubjectType.PRODUCT)
        self.assertEqual(contract.delivery_mode, DeliveryMode.PAID)
        self.assertTrue(contract.allowed)
        self.assertTrue(contract.requires_payment)
        self.assertEqual(contract.price_cents, 2999)

    def test_projects_free_delivery_type_from_product_metadata(self):
        free_product = Product(
            **{
                **self.product.__dict__,
                "metadata": {
                    **dict(self.product.metadata),
                    "delivery_type": "FREE",
                },
                "delivery_type": None,
            }
        )

        product_contract = self.service.build_available_product(free_product)
        permission = self.service.build_delivery_permission(
            subject_id=free_product.id,
            product=free_product,
        )

        self.assertEqual(product_contract.delivery_type, ProductDeliveryType.FREE)
        self.assertEqual(permission.delivery_mode, DeliveryMode.INCLUDED)
        self.assertFalse(permission.requires_payment)

    def test_builds_offer_candidate_contract(self):
        offer = ProductOffer(
            product=self.product,
            offer_type="premium",
            reason="theme_match",
            score=78,
            checkout_url="https://example.invalid/hidden-checkout",
            metadata={
                "chapter": "after dark",
                "provider_url": "https://example.invalid/hidden",
            },
        )
        permission = self.service.build_delivery_permission(
            subject_id=self.product.id,
            product=self.product,
        )

        contract = self.service.build_offer_candidate(
            offer,
            experience=self.experience,
            delivery_permission=permission,
        )

        self.assertIsInstance(contract, OfferCandidate)
        self.assertEqual(contract.offer_kind, OfferKind.PREMIUM)
        self.assertEqual(contract.title, "Mirror Set")
        self.assertIsInstance(contract.product, AvailableProduct)
        self.assertIsInstance(contract.experience, AvailableExperience)
        self.assertEqual(contract.score, 78)
        self.assertEqual(contract.reason, "theme_match")
        self.assertEqual(contract.presentation, {"chapter": "after dark"})
        self.assertTrue(contract.is_deliverable)

    def test_builds_customer_identity_and_runtime_context(self):
        identity = self.service.build_customer_identity(
            "customer-1",
            creator_id=7,
            channel="chat",
            display_name="Sam",
        )
        context = self.service.build_runtime_customer_context(
            identity,
            traits={
                "buyer_tier": "warm",
                "profile_url": "https://example.invalid/hidden",
            },
            conversation_state={
                "intent_score": 64,
                "provider_account_id": 99,
            },
        )

        self.assertIsInstance(identity, CustomerIdentity)
        self.assertIsInstance(context, RuntimeCustomerContext)
        self.assertEqual(context.identity.customer_id, "customer-1")
        self.assertEqual(context.traits, {"buyer_tier": "warm"})
        self.assertEqual(context.conversation_state, {"intent_score": 64})

    def test_missing_optional_data_is_safe(self):
        empty_service = CMSContractService(
            experience_service=FakeExperienceService(None),
        )

        self.assertIsNone(empty_service.get_available_product("missing"))
        self.assertIsNone(empty_service.get_available_experience("missing"))
        self.assertEqual(
            empty_service.build_publishing_status(
                None,
                subject_id="product-1",
            ).state,
            PublishingState.NOT_PUBLISHED,
        )
        self.assertFalse(
            empty_service.build_delivery_permission(
                subject_id="product-1",
            ).allowed
        )

    def test_contract_boundary_returns_dataclasses_not_legacy_dicts(self):
        contracts = (
            self.service.build_available_product(self.product),
            self.service.build_available_experience(self.experience),
            self.service.get_publishing_status(self.product.id),
            self.service.build_customer_progress("customer-1"),
            self.service.build_delivery_permission(
                subject_id=self.product.id,
                product=self.product,
            ),
            self.service.build_offer_candidate(product=self.product),
            self.service.build_customer_identity("customer-1"),
            self.service.build_runtime_customer_context("customer-1"),
        )

        for contract in contracts:
            self.assertTrue(is_dataclass(contract), type(contract).__name__)
            self.assertNotIsInstance(contract, dict)

    def test_contract_outputs_do_not_expose_legacy_field_names(self):
        contracts = (
            self.service.build_available_product(self.product),
            self.service.build_available_experience(self.experience),
            self.service.get_publishing_status(self.product.id),
            self.service.build_customer_progress(
                "customer-1",
                user_memory={
                    "signals": {
                        "intent_score": 90,
                        "provider_user_id": "hidden",
                    }
                },
            ),
            self.service.build_delivery_permission(
                subject_id=self.product.id,
                product=self.product,
            ),
            self.service.build_offer_candidate(
                ProductOffer(
                    product=self.product,
                    offer_type="vip",
                    reason="buyer_value_fit",
                    score=88,
                    checkout_url="https://example.invalid/hidden",
                    metadata={"provider_url": "https://example.invalid/hidden"},
                )
            ),
        )

        for contract in contracts:
            flattened = str(asdict(contract)).lower()
            for marker in FORBIDDEN_BOUNDARY_MARKERS:
                self.assertNotIn(
                    marker,
                    flattened,
                    f"{type(contract).__name__} exposes {marker}",
                )


if __name__ == "__main__":
    unittest.main()
