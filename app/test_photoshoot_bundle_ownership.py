from datetime import datetime, timezone
from types import MappingProxyType, SimpleNamespace
from uuid import uuid4

from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootStatus
from app.models.ownership_intelligence import (
    CanonicalOwnershipAnswer, OwnershipAnswerState, OwnershipEvidence,
    OwnershipIdentity, OwnershipLifecycle, OwnershipSource,
)
from app.services.customer_photoshoot_lifecycle_service import (
    CustomerPhotoshootLifecycleService,
)
from app.services.photoshoot_bundle_ownership_service import (
    PhotoshootBundleOwnershipService,
)


NOW = datetime(2026, 8, 7, tzinfo=timezone.utc)


class ContextRepository:
    def __init__(self, offering_id, teaser_id=99):
        self.offering_id = offering_id
        self.teaser_id = teaser_id

    def context(self, deliverable_id, *, creator_profile_id):
        return {
            "deliverable_id": deliverable_id,
            "photoshoot_session_id": "shoot-1", "selling_mode": "BUNDLE",
            "offering_id": self.offering_id, "price_minor": 2500,
            "currency": "USD", "paid_asset_ids": (11, 12, 13),
            "teaser_asset_id": self.teaser_id,
        }


class Ownership:
    def __init__(self, offering_id, *, purchase=True, assets=(11, 12, 13)):
        evidence = ()
        offerings = ()
        if purchase:
            offerings = (offering_id,)
            evidence = (OwnershipEvidence(
                source=OwnershipSource.OFFERING_PURCHASE,
                lifecycle=OwnershipLifecycle.PURCHASED,
                identity_path="external_fanvue_user_uuid",
                supporting_record_id="intent-1", offering_id=offering_id,
                asset_ids=(11, 12, 13), proves_ownership=True,
                details=MappingProxyType({"purchasedAt": NOW.isoformat()}),
            ),)
        self.answer_value = CanonicalOwnershipAnswer(
            identity=IDENTITY, evidence=evidence,
            owned_offering_ids=offerings, owned_product_ids=(),
            owned_asset_ids=tuple(assets),
            state=(OwnershipAnswerState.CONFIRMED_OWNERSHIP if purchase
                   else OwnershipAnswerState.NO_DEMONSTRATED_OWNERSHIP),
        )

    def answer(self, identity):
        return self.answer_value

    @staticmethod
    def owns_offering(answer, offering_id):
        return offering_id in answer.owned_offering_ids


IDENTITY = OwnershipIdentity(
    creator_profile_id=1, fanvue_account_id=2,
    external_fanvue_user_uuid=uuid4(),
)


def test_one_bundle_purchase_projects_all_originals_and_excludes_teaser():
    offering_id = uuid4()
    result = PhotoshootBundleOwnershipService(
        repository=ContextRepository(offering_id),
        ownership=Ownership(offering_id),
    ).inspect(uuid4(), identity=IDENTITY)

    assert result["purchased"] is True
    assert result["bundleOfferingId"] == str(offering_id)
    assert result["ownedAssetIds"] == [11, 12, 13]
    assert result["totalPaidAssetCount"] == 3
    assert result["ownedPaidAssetCount"] == 3
    assert result["complete"] is True
    assert result["purchasedAt"] == NOW.isoformat()
    assert result["promotionalTeaserAssetId"] == 99
    assert result["promotionalTeaserExcluded"] is True
    assert 99 not in result["ownedAssetIds"]


def test_independent_member_ownership_does_not_fabricate_bundle_purchase():
    offering_id = uuid4()
    result = PhotoshootBundleOwnershipService(
        repository=ContextRepository(offering_id),
        ownership=Ownership(
            offering_id, purchase=False, assets=(11, 12, 13),
        ),
    ).inspect(uuid4(), identity=IDENTITY)

    assert result["paidAssetIds"] == [11, 12, 13]
    assert result["ownedPaidAssetCount"] == 3
    assert result["purchased"] is False
    assert result["complete"] is False
    assert result["purchasedAt"] is None


class LifecycleRepository:
    def __init__(self):
        self.transitions = []
        self.lifecycle = SimpleNamespace(
            lifecycle_id=uuid4(), customer_commerce_profile_id=uuid4(),
            photoshoot_id="shoot-1", status=CustomerPhotoshootStatus.ACTIVE,
        )

    def get_for_purchase_intent(self, intent):
        return self.lifecycle

    def offering_asset_ids(self, offering_id):
        return (11, 12, 13)

    def photoshoot_asset_ids(self, lifecycle_id):
        return (11, 12, 13)

    def offering_selling_mode(self, offering_id):
        return "BUNDLE"

    def transition(self, lifecycle_id, **values):
        self.transitions.append(values)
        self.lifecycle.status = values["status"]
        return self.lifecycle

    def coverage(self, lifecycle_id):
        return {"purchased_asset_ids": (), "sellable_asset_ids": (11, 12, 13)}


def test_bundle_lifecycle_completes_without_per_asset_purchase_events():
    repository = LifecycleRepository()
    intent = SimpleNamespace(
        status="PURCHASED", attribution_result="ATTRIBUTED",
        commercial_offering_id=uuid4(), purchase_intent_id=uuid4(),
        creator_profile_id=1,
    )

    result, coverage = CustomerPhotoshootLifecycleService(
        repository=repository
    ).synchronize_attributed_purchase(
        intent=intent,
        customer_commerce_profile_id=repository.lifecycle.customer_commerce_profile_id,
    )

    assert result.status is CustomerPhotoshootStatus.COMPLETED
    assert len(repository.transitions) == 1
    assert repository.transitions[0]["event_type"] == "BUNDLE_PURCHASED"
    assert "asset_id" not in repository.transitions[0]
    assert coverage["purchased_asset_ids"] == ()
