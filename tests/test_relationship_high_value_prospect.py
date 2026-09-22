from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.models.ava_availability_session import AvaAvailabilityState
from app.services.ava_human_availability_service import AvaHumanAvailabilityService
from app.services.relationship_value_override_service import RelationshipValueOverrideService


class SessionRepository:
    def __init__(self, state, now, seconds):
        self.session = SimpleNamespace(session_id="session", state=state,
            started_at=now-timedelta(minutes=1), transition_at=now+timedelta(seconds=seconds))
    def current_or_transition(self, **_): return self.session


@pytest.mark.parametrize("state,normal,hvp", [
    (AvaAvailabilityState.ACTIVE, 200, 100),
    (AvaAvailabilityState.BUSY, 1000, 350),
    (AvaAvailabilityState.AWAY, 1000, 350),
    (AvaAvailabilityState.SLEEPING, 1000, 1000),
])
def test_hvp_has_bounded_availability_effect_without_bypassing_sleep(state, normal, hvp):
    now=datetime(2026,9,13,20,tzinfo=timezone.utc)
    service=AvaHumanAvailabilityService(now=lambda:now,uniform=lambda *_:200,
        repository=SessionRepository(state,now,1000))
    assert service.calculate().delay_seconds == normal
    decision=service.calculate(high_value_prospect=True)
    assert decision.delay_seconds == hvp
    assert decision.diagnostics()["messagePriorityAffectsAvailability"] is True


class Repository:
    def __init__(self): self.active_row=None;self.advances=[];self.removed=False;self.version=0;self.history=[]
    def active(self,**_): return self.active_row
    def set_high_value(self,**scope):
        if self.active_row: return self.active_row,False
        self.version += 1
        self.active_row={**scope,"classification":"HIGH_VALUE_PROSPECT","version":self.version}
        self.history.append(self.active_row)
        return self.active_row,True
    def advance_eligible(self,**values): self.advances.append(values);return {"operation_id":"op","next_retry_at":values["available_at"]}
    def remove(self,**values):
        self.removed=True;prior=self.active_row;self.active_row=None
        if prior: prior.update(removed_by=values["removed_by"],removed_at="now")
        return prior


class Effective:
    def __init__(self, allowed=True): self.allowed=allowed
    def read(self,**_): return {"effective":{"chatAllowed":self.allowed}}


class Availability:
    def __init__(self): self.calls=[]
    def calculate(self,**values): self.calls.append(values);return SimpleNamespace(available_at=datetime(2026,9,13,21,tzinfo=timezone.utc))


def scope(): return dict(creator_profile_id=1,fanvue_account_id=2,telegram_user_id=3,telegram_chat_id=3)


def test_set_is_closed_audited_and_advances_only_through_hvp_policy():
    repo=Repository();availability=Availability()
    service=RelationshipValueOverrideService(repository=repo,availability=availability,effective_permissions=Effective())
    with pytest.raises(ValueError): service.set(classification="VIP",changed_by="operator",**scope())
    result=service.set(classification="HIGH_VALUE_PROSPECT",changed_by="operator",**scope())
    assert result["scheduleAdvanced"] is True
    assert availability.calls == [{"high_value_prospect":True}]
    assert repo.active_row["changed_by"] == "operator"


def test_manual_or_global_denial_prevents_advancement_and_remove_never_delays():
    repo=Repository();availability=Availability()
    service=RelationshipValueOverrideService(repository=repo,availability=availability,effective_permissions=Effective(False))
    assert service.set(classification="HIGH_VALUE_PROSPECT",changed_by="operator",**scope())["scheduleAdvanced"] is False
    assert not repo.advances
    result=service.remove(removed_by="operator",**scope())
    assert result["scheduleAdvanced"] is False
    assert not repo.advances


def test_remove_is_idempotent_audited_persistent_and_can_be_reassigned():
    repo=Repository();service=RelationshipValueOverrideService(
        repository=repo,availability=Availability(),effective_permissions=Effective(False))
    service.set(classification="HIGH_VALUE_PROSPECT",changed_by="operator",**scope())
    removed=service.remove(removed_by="operator",**scope())["override"]
    assert removed["removed_by"] == "operator"
    assert service.active(**scope()) is None
    assert service.remove(removed_by="operator",**scope())["override"] is None
    reassigned=service.set(classification="HIGH_VALUE_PROSPECT",changed_by="operator",**scope())["override"]
    assert reassigned["version"] == 2
    assert len(repo.history) == 2
