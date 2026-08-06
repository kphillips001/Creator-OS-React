from dataclasses import replace
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.models.customer_photoshoot_lifecycle import CustomerPhotoshootLifecycle, CustomerPhotoshootStatus
from app.services.customer_photoshoot_lifecycle_service import CustomerPhotoshootLifecycleService, InvalidLifecycleTransition
from app.services.customer_sales_brain_service import CustomerSalesBrainService


class MemoryRepository:
    def __init__(self, core=(2, 3), teaser=(1,), video=()):
        self.rows = {}; self.events = []; self.core = tuple(core); self.teaser = tuple(teaser); self.video = tuple(video)

    def resolve(self, **values):
        key = (values["creator_profile_id"], values["customer_commerce_profile_id"], str(values["photoshoot_id"]))
        if key not in self.rows:
            self.rows[key] = CustomerPhotoshootLifecycle(
                uuid4(), key[0], key[1], key[2], CustomerPhotoshootStatus.ACTIVE,
                selected_offering_id=values.get("selected_offering_id"),
                recommendation_reason=values.get("recommendation_reason"),
                expires_at=datetime.now(timezone.utc) + timedelta(days=7),
            )
        return self.rows[key]

    def list_for_customer(self, **values):
        return tuple(row for (creator, customer, _), row in self.rows.items()
                     if creator == values["creator_profile_id"] and customer == values["customer_commerce_profile_id"])

    def get_by_id(self, lifecycle_id):
        return next((row for row in self.rows.values() if row.lifecycle_id == lifecycle_id), None)

    def transition(self, lifecycle_id, **values):
        key, row = next(item for item in self.rows.items() if item[1].lifecycle_id == lifecycle_id)
        metadata = values.get("metadata") or {}
        row = replace(
            row, status=values["status"],
            objection_attempts=row.objection_attempts + int(metadata.get("objection_attempt_delta") or 0),
        )
        self.rows[key] = row
        event = (values["event_type"], values.get("asset_id"), values.get("purchase_outcome_id"))
        if event not in self.events: self.events.append(event)
        return row

    def expire_due(self, **scope): return ()
    def history(self, lifecycle_id): return tuple(self.events)
    def teaser_asset_ids(self, lifecycle_id): return self.teaser
    def finale_video_asset_ids(self, lifecycle_id): return self.video
    def required_core_asset_ids(self, lifecycle_id): return self.core
    def offering_asset_ids(self, offering_id): return self.teaser + self.core + self.video
    def photoshoot_asset_ids(self, lifecycle_id): return self.teaser + self.core + self.video
    def get_for_purchase_intent(self, intent): return next((row for row in self.rows.values() if row.selected_offering_id == intent.commercial_offering_id), None)
    def coverage(self, lifecycle_id):
        presented = tuple(dict.fromkeys(event[1] for event in self.events if event[0] == "PRESENTED"))
        purchased = tuple(dict.fromkeys(event[1] for event in self.events if event[0] == "PURCHASED"))
        sellable = self.core + self.video
        return {"presented_asset_ids": presented, "purchased_asset_ids": purchased,
                "sellable_asset_ids": sellable, "remaining_asset_ids": tuple(value for value in sellable if value not in purchased)}


def recommendation(photoshoot="shoot-a"):
    return SimpleNamespace(photoshoot_id=photoshoot, commercial_offering_id=uuid4(), recommendation_explanation="fit", recommendation_score=.9)


def test_recommendation_opens_one_active_opportunity():
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    first = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    second = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    assert first.lifecycle_id == second.lifecycle_id
    assert first.status is CustomerPhotoshootStatus.ACTIVE


def test_teaser_never_creates_ownership_or_progress():
    repository = MemoryRepository(core=(2,), teaser=(1,)); service = CustomerPhotoshootLifecycleService(repository)
    opportunity, coverage = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=uuid4(), photoshoot_id="a", asset_ids=(1,), purchase_outcome_id=uuid4())
    assert coverage["purchased_asset_ids"] == ()
    assert opportunity.status is CustomerPhotoshootStatus.ACTIVE


def test_attributed_purchase_synchronizes_existing_lifecycle_once():
    repository = MemoryRepository(core=(2,), teaser=(), video=())
    service = CustomerPhotoshootLifecycleService(repository)
    customer, offering, intent_id = uuid4(), uuid4(), uuid4()
    repository.resolve(
        creator_profile_id=1, customer_commerce_profile_id=customer,
        photoshoot_id="shoot-a", selected_offering_id=offering,
    )
    intent = SimpleNamespace(
        status=SimpleNamespace(value="PURCHASED"),
        attribution_result=SimpleNamespace(value="ATTRIBUTED"),
        creator_profile_id=1, commercial_offering_id=offering,
        purchase_intent_id=intent_id,
    )

    service.synchronize_attributed_purchase(
        intent=intent, customer_commerce_profile_id=customer,
    )
    service.synchronize_attributed_purchase(
        intent=intent, customer_commerce_profile_id=customer,
    )

    assert repository.events.count(("PURCHASED", 2, intent_id)) == 1


def test_unattributed_or_unmapped_purchase_never_writes_lifecycle_event():
    repository = MemoryRepository(core=(2,), teaser=(), video=())
    service = CustomerPhotoshootLifecycleService(repository)
    intent = SimpleNamespace(
        status=SimpleNamespace(value="PURCHASED"),
        attribution_result=SimpleNamespace(value="UNKNOWN"),
        creator_profile_id=1, commercial_offering_id=uuid4(),
        purchase_intent_id=uuid4(),
    )

    assert service.synchronize_attributed_purchase(
        intent=intent, customer_commerce_profile_id=uuid4(),
    ) is None
    assert repository.events == []


def test_confirmed_free_teaser_delivery_is_presented_and_idempotent_without_purchase():
    repository = MemoryRepository(core=(2,), teaser=(1,))
    service = CustomerPhotoshootLifecycleService(repository)
    opportunity = repository.resolve(
        creator_profile_id=1, customer_commerce_profile_id=uuid4(), photoshoot_id="a",
    )

    for _ in range(2):
        service.record_free_teaser_delivery(
            lifecycle_id=opportunity.lifecycle_id, asset_id=1, provider="TELEGRAM",
            provider_delivery_id="message-44", metadata={"confirmed": True},
        )

    coverage = repository.coverage(opportunity.lifecycle_id)
    assert coverage["presented_asset_ids"] == (1,)
    assert coverage["purchased_asset_ids"] == ()


def test_free_delivery_rejects_paid_strategy_asset():
    repository = MemoryRepository(core=(2,), teaser=(1,))
    service = CustomerPhotoshootLifecycleService(repository)
    opportunity = repository.resolve(
        creator_profile_id=1, customer_commerce_profile_id=uuid4(), photoshoot_id="a",
    )
    with pytest.raises(ValueError, match="FREE strategy Asset"):
        service.record_free_teaser_delivery(
            lifecycle_id=opportunity.lifecycle_id, asset_id=2, provider="TELEGRAM",
            provider_delivery_id="message-45",
        )


def test_zero_video_completes_after_all_paid_chapters():
    repository = MemoryRepository(core=(2,), video=()); service = CustomerPhotoshootLifecycleService(repository)
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=uuid4(), photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
    assert opportunity.status is CustomerPhotoshootStatus.COMPLETED


def test_optional_finale_keeps_opportunity_active_until_purchased():
    repository = MemoryRepository(core=(2,), video=(9,)); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=customer, photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
    assert opportunity.status is CustomerPhotoshootStatus.ACTIVE
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=customer, photoshoot_id="a", asset_ids=(9,), purchase_outcome_id=uuid4())
    assert opportunity.status is CustomerPhotoshootStatus.COMPLETED


def test_optional_finale_may_be_explicitly_declined_after_core_completion():
    repository = MemoryRepository(core=(2,), video=(9,)); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=customer, photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
    opportunity = service.decline_finale(opportunity)
    assert opportunity.status is CustomerPhotoshootStatus.COMPLETED


def test_declining_presented_finale_resolves_the_opportunity_as_completed():
    repository = MemoryRepository(core=(2,), video=(9,)); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=customer, photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
    intent = SimpleNamespace(commercial_offering_id=opportunity.selected_offering_id, purchase_intent_id=uuid4(), external_fanvue_user_uuid=uuid4())
    repository.offering_asset_ids = lambda offering_id: (9,)
    resolved = service.record_intent_outcome(intent, "DECLINED")
    assert resolved.status is CustomerPhotoshootStatus.COMPLETED


@pytest.mark.parametrize("terminal", [CustomerPhotoshootStatus.CLOSED, CustomerPhotoshootStatus.COMPLETED, CustomerPhotoshootStatus.DECLINED])
def test_terminal_opportunity_never_reactivates(terminal):
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    item = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    item = service.transition(item, terminal)
    same = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    assert same.status is terminal
    with pytest.raises(InvalidLifecycleTransition): service.transition(same, CustomerPhotoshootStatus.ACTIVE)


def test_ownership_survives_opportunity_closure():
    repository = MemoryRepository(core=(2, 3)); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity, _ = service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=customer, photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
    service.transition(opportunity, CustomerPhotoshootStatus.CLOSED)
    coverage = repository.coverage(opportunity.lifecycle_id)
    assert coverage["purchased_asset_ids"] == (2,)


def test_decline_enters_objection_instead_of_terminating_immediately():
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4(); rec = recommendation()
    opportunity = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=rec)
    intent = SimpleNamespace(commercial_offering_id=rec.commercial_offering_id, purchase_intent_id=uuid4(), external_fanvue_user_uuid=uuid4())
    result = service.record_intent_outcome(intent, "DECLINED")
    assert result.status is CustomerPhotoshootStatus.OBJECTION


def test_objection_recovery_returns_to_active_progression():
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    opportunity = service.enter_objection(opportunity, reason="PRICE")
    recovered = service.attempt_recovery(opportunity, recovered=True, recovery_limit=2)
    assert recovered.status is CustomerPhotoshootStatus.ACTIVE
    assert recovered.objection_attempts == 1


def test_recovery_limit_terminates_as_declined():
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    opportunity = service.enter_objection(opportunity)
    opportunity = service.attempt_recovery(opportunity, recovered=False, recovery_limit=2)
    assert opportunity.status is CustomerPhotoshootStatus.OBJECTION
    opportunity = service.attempt_recovery(opportunity, recovered=False, recovery_limit=2)
    assert opportunity.status is CustomerPhotoshootStatus.DECLINED


def test_sales_brain_can_intentionally_close_active_opportunity():
    repository = MemoryRepository(); service = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunity = service.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    closed = service.close_opportunity(opportunity, reason="STRONGER_OPPORTUNITY")
    assert closed.status is CustomerPhotoshootStatus.CLOSED


def test_sales_brain_closes_before_allowing_a_stronger_opportunity():
    repository = MemoryRepository(); opportunities = CustomerPhotoshootLifecycleService(repository); customer = uuid4()
    opportunities.resolve_recommendation(creator_profile_id=1, customer_commerce_profile_id=customer, recommendation=recommendation())
    brain = CustomerSalesBrainService.__new__(CustomerSalesBrainService)
    brain.photoshoot_lifecycles = opportunities
    brain.config = SimpleNamespace(photoshoot_objection_recovery_limit=2)
    profile = SimpleNamespace(customer_commerce_profile_id=customer)
    result = brain._apply_photoshoot_opportunity_policy(
        creator_profile_id=1, customer_profile=profile,
        context={"stronger_opportunity_available": True},
    )
    assert result.status is CustomerPhotoshootStatus.CLOSED


def test_at_most_one_finale_video_is_supported():
    repository = MemoryRepository(core=(2,), video=(9, 10)); service = CustomerPhotoshootLifecycleService(repository)
    with pytest.raises(ValueError, match="at most one"):
        service.synchronize_purchase(creator_profile_id=1, customer_commerce_profile_id=uuid4(), photoshoot_id="a", asset_ids=(2,), purchase_outcome_id=uuid4())
