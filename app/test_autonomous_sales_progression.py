from datetime import datetime, timezone
from uuid import uuid4

import pytest

from app.models.autonomous_sales_progression import (
    BuyingMomentumEvidence, BuyingMomentumState, NextSalesActionType,
    ProgressionAssetRole, SellableProgressionAsset,
)
from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootLifecycle, CustomerPhotoshootStatus
from app.services.autonomous_sales_progression_service import AutonomousSalesProgressionService, BuyingMomentumService

NOW = datetime(2026, 8, 4, tzinfo=timezone.utc)
CUSTOMER = uuid4(); OFFER = uuid4(); PUBLICATION = uuid4()


def asset(asset_id, position, role=ProgressionAssetRole.CORE_SESSION, **changes):
    return SellableProgressionAsset(
        asset_id, position, role,
        offering_id=changes.pop("offering_id", OFFER),
        publication_id=changes.pop("publication_id", PUBLICATION),
        delivery_url=changes.pop("delivery_url", "https://delivery"),
        **changes,
    )


def opportunity(status=CustomerPhotoshootStatus.ACTIVE, photoshoot="shoot-a"):
    return CustomerPhotoshootLifecycle(uuid4(), 1, CUSTOMER, photoshoot, status)


def engine():
    return AutonomousSalesProgressionService(clock=lambda: NOW)


def momentum(**changes):
    return BuyingMomentumEvidence(**changes)


def test_teaser_is_free_and_never_selected_as_a_paid_chapter():
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(),
        assets=(asset(1, 1, ProgressionAssetRole.DISCOVERY, offering_id=None), asset(2, 2)),
        momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.OFFER_NEXT_IMAGE
    assert result.selected_asset_id == 2


def test_presented_unpaid_chapter_remains_current_and_cannot_skip():
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(),
        assets=(asset(1, 1, presented=True), asset(2, 2)),
        momentum_evidence=momentum(explicit_more=True),
    )
    assert result.selected_asset_id == 1


def test_owned_chapter_is_not_replayed():
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(),
        assets=(asset(1, 1, owned=True), asset(2, 2)),
        momentum_evidence=momentum(explicit_more=True),
    )
    assert result.selected_asset_id == 2


@pytest.mark.parametrize("status", [
    CustomerPhotoshootStatus.CLOSED,
    CustomerPhotoshootStatus.COMPLETED,
    CustomerPhotoshootStatus.DECLINED,
])
def test_terminal_opportunity_never_resumes(status):
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(status),
        assets=(asset(1, 1),), momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.CHAT_ONLY
    assert result.selected_asset_id is None


def test_objection_pauses_chapter_sales_for_recovery():
    result = engine().decide(
        customer_profile_id=CUSTOMER,
        lifecycle=opportunity(CustomerPhotoshootStatus.OBJECTION),
        assets=(asset(1, 1),), momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.HANDLE_OBJECTION
    assert result.selected_offering_id is None


def test_zero_video_photoshoot_completes_after_paid_images():
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(),
        assets=(asset(1, 1, owned=True),), momentum_evidence=momentum(),
    )
    assert result.action is NextSalesActionType.COMPLETE_PHOTOSHOOT


def test_optional_vip_finale_is_offered_only_after_images():
    assets = (
        asset(1, 1, owned=True),
        asset(9, 2, ProgressionAssetRole.FINALE_VIDEO),
    )
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(), assets=assets,
        momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.OFFER_FINALE_VIDEO
    assert result.selected_asset_id == 9


def test_video_never_skips_an_unpaid_image():
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(),
        assets=(asset(1, 1), asset(9, 2, ProgressionAssetRole.FINALE_VIDEO)),
        momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.OFFER_NEXT_IMAGE
    assert result.selected_asset_id == 1


def test_active_intent_is_reused_before_new_chapter():
    intent = uuid4()
    result = engine().decide(
        customer_profile_id=CUSTOMER, lifecycle=opportunity(), assets=(asset(1, 1),),
        active_purchase_intent_id=intent, momentum_evidence=momentum(explicit_more=True),
    )
    assert result.action is NextSalesActionType.REUSE_ACTIVE_INTENT
    assert result.purchase_intent_id == intent


@pytest.mark.parametrize("evidence,state", [
    ({"explicit_more": True}, BuyingMomentumState.MODERATE),
    ({"runtime_suppressed": True}, BuyingMomentumState.STOPPED),
    ({"cooldown": True}, BuyingMomentumState.COOLDOWN),
])
def test_authoritative_controls_remain_effective(evidence, state):
    assert BuyingMomentumService().assess(momentum(**evidence)).state is state
