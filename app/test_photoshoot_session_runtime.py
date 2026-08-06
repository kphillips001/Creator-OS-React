import inspect
from dataclasses import replace
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

from app.models.customer_photoshoot_lifecycle import (
    CustomerPhotoshootLifecycle,
    CustomerPhotoshootStatus,
)
from app.models.ownership_intelligence import CanonicalOwnershipAnswer, OwnershipAnswerState
from app.models.photoshoot_session_sales_strategy import SessionShotSalesRecommendation
from app.services.customer_sales_brain_service import CustomerSalesBrainService
from app.services.photoshoot_session_runtime_service import PhotoshootSessionRuntimeService


def shot(asset_id, position, role, next_id):
    return SessionShotSalesRecommendation(
        asset_id=asset_id, shot_order=position, sales_position=position,
        sales_role=role, teaser_recommended=role == "FREE_TEASER",
        access_recommendation="FREE" if role == "FREE_TEASER" else "PAID",
        recommended_progression=f"Step {position}", suggested_next_asset_id=next_id,
        customer_journey_purpose=f"Purpose {position}", escalation_role=f"Escalation {position}",
        psychological_objective=f"Objective {position}", conversation_goal=f"Goal {position}",
    )


class Customers:
    profile_id = uuid4()
    def get_by_id(self, profile_id, *, creator_profile_id):
        if profile_id != self.profile_id or creator_profile_id != 7: return None
        return SimpleNamespace(
            customer_commerce_profile_id=profile_id, fanvue_account_id=8,
            external_fanvue_user_uuid=uuid4(), telegram_user_id=99,
        )


class LifecycleRepository:
    def __init__(self, lifecycle): self.lifecycle=lifecycle; self.purchased=set(); self.presented=set()
    def get(self, **_scope): return self.lifecycle
    def coverage(self, _lifecycle_id):
        return {"purchased_asset_ids":tuple(self.purchased),"presented_asset_ids":tuple(self.presented)}


class Lifecycles:
    def __init__(self, lifecycle): self.repository=LifecycleRepository(lifecycle); self.transitions=[]
    def transition(self, lifecycle, status, **values):
        self.transitions.append((status,values))
        self.repository.lifecycle=replace(lifecycle,status=status,completed_at=datetime.now(timezone.utc))
        return self.repository.lifecycle


class Ownership:
    def __init__(self): self.owned=set(); self.calls=[]
    def answer(self, identity):
        self.calls.append(identity)
        return CanonicalOwnershipAnswer(
            identity=identity,evidence=(),owned_offering_ids=(),owned_product_ids=(),
            owned_asset_ids=tuple(sorted(self.owned)),state=(
                OwnershipAnswerState.CONFIRMED_OWNERSHIP if self.owned
                else OwnershipAnswerState.NO_DEMONSTRATED_OWNERSHIP
            ),
        )


class Strategies:
    def latest(self, session_id):
        return SimpleNamespace(
            photoshoot_session_id=session_id,strategy_version="v1",
            shots=(shot(131,1,"FREE_TEASER",132),shot(132,2,"FIRST_UNLOCK",133),shot(133,3,"FINALE",None)),
            customer_engagement_strategy="Respond to engagement.",
            escalation_pacing="Gradual.",session_completion_strategy="Close after the finale.",
        )


def lifecycle(status=CustomerPhotoshootStatus.ACTIVE):
    return CustomerPhotoshootLifecycle(
        lifecycle_id=uuid4(),creator_profile_id=7,
        customer_commerce_profile_id=Customers.profile_id,photoshoot_id="session-1",status=status,
    )


def runtime(lifecycle_value=None):
    ownership=Ownership(); lifecycles=Lifecycles(lifecycle_value)
    service=PhotoshootSessionRuntimeService(
        customers=Customers(),lifecycles=lifecycles,ownership=ownership,strategies=Strategies(),
    )
    return service,ownership,lifecycles


def test_no_ownership_starts_at_free_teaser_and_exposes_persisted_guidance():
    service,_,_=runtime(lifecycle())
    state=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert state.status.value == "ACTIVE"
    assert (state.current_asset_id,state.current_sales_role)==(131,"FREE_TEASER")
    assert (state.next_asset_id,state.next_sales_role)==(132,"FIRST_UNLOCK")
    assert state.conversation_goal == "Goal 1"
    assert state.psychological_objective == "Objective 1"
    assert state.customer_engagement_strategy == "Respond to engagement."
    assert state.escalation_pacing == "Gradual."


def test_presented_advances_only_the_free_strategy_step():
    service,ownership,lifecycles=runtime(lifecycle())
    lifecycles.repository.presented.add(131)
    advanced=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert (advanced.current_asset_id,advanced.current_sales_role)==(132,"FIRST_UNLOCK")
    assert advanced.current_position == 2
    lifecycles.repository.presented.add(132)
    paid_unchanged=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert (paid_unchanged.current_asset_id,paid_unchanged.current_sales_role)==(132,"FIRST_UNLOCK")
    ownership.owned.add(132)
    paid_advanced=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert paid_advanced.current_asset_id == 133


def test_purchase_history_is_authoritative_and_final_ownership_completes_lifecycle_once():
    active=lifecycle(); service,ownership,lifecycles=runtime(active)
    lifecycles.repository.purchased.update({131,132})
    ownership.owned.add(133)
    completed=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert completed.status.value == "COMPLETED"
    assert completed.current_asset_id == 133 and completed.next_asset_id is None
    assert lifecycles.transitions[0][1]["event_type"] == "SESSION_RUNTIME_COMPLETED"
    again=service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert again.to_context() == completed.to_context()
    assert len(lifecycles.transitions) == 1


def test_not_started_and_abandoned_reuse_lifecycle_semantics():
    not_started,_,_=runtime(None)
    state=not_started.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1")
    assert state.status.value == "NOT_STARTED" and state.current_asset_id == 131
    abandoned,_,_=runtime(lifecycle(CustomerPhotoshootStatus.CLOSED))
    assert abandoned.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1").status.value == "ABANDONED"


def test_runtime_is_restart_safe_deterministic_and_contains_no_ai_paths():
    shared_lifecycle=lifecycle(); shared_ownership=Ownership(); shared_lifecycles=Lifecycles(shared_lifecycle)
    values=[]
    for _ in range(2):
        service=PhotoshootSessionRuntimeService(customers=Customers(),lifecycles=shared_lifecycles,ownership=shared_ownership,strategies=Strategies())
        values.append(service.evaluate(creator_profile_id=7,customer_commerce_profile_id=Customers.profile_id,photoshoot_session_id="session-1").to_context())
    assert values[0] == values[1]
    source=inspect.getsource(PhotoshootSessionRuntimeService)
    assert "OpenAI" not in source and "input_image" not in source and "vision" not in source.lower()
    brain=inspect.getsource(CustomerSalesBrainService)
    assert "session_runtime_state.to_context()" in brain
