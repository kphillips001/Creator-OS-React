from datetime import datetime,timezone
from types import SimpleNamespace

import pytest

from app.models.ava_availability_session import AvaAvailabilityState
from app.services.ava_human_availability_service import AvaHumanAvailabilityService
from app.services.peak_engagement_policy import PeakEngagementPolicy


def utc(year,month,day,hour,minute=0,second=0):
    return datetime(year,month,day,hour,minute,second,tzinfo=timezone.utc)


@pytest.mark.parametrize("at,active",[(utc(2026,7,2,23,59,59),False),(utc(2026,7,3,0),True),
    (utc(2026,7,3,4,59,59),True),(utc(2026,7,3,5),False)])
def test_cdt_window_boundaries(at,active):
    assert PeakEngagementPolicy().evaluate(now=at,availability_state="ACTIVE").active is active


def test_midnight_continuation_is_conversation_specific():
    now=utc(2026,7,3,5,5);prior=utc(2026,7,3,4,55)
    continued=PeakEngagementPolicy().evaluate(now=now,availability_state="ACTIVE",confirmed_exchange_at=prior)
    fresh=PeakEngagementPolicy().evaluate(now=now,availability_state="ACTIVE")
    assert continued.active and continued.continuation_grace and continued.pacing_eligible
    assert not fresh.active and fresh.suppressed_by=="OUTSIDE_PEAK_WINDOW"


@pytest.mark.parametrize("at,offset",[(utc(2026,1,16,2,30),"-06:00"),(utc(2026,7,16,1,30),"-05:00"),
    (utc(2026,3,9,0,30),"-05:00"),(utc(2026,11,2,1,30),"-06:00")])
def test_iana_timezone_handles_standard_daylight_and_transitions(at,offset):
    decision=PeakEngagementPolicy().evaluate(now=at,availability_state="ACTIVE")
    assert decision.local_time.isoformat().endswith(offset) and decision.active


@pytest.mark.parametrize("flag,reason",[("commercial_authority","COMMERCIAL_AUTHORITY"),
    ("verified_buyer","BUYER_AUTHORITY"),("reduced_investment","REDUCED_INVESTMENT"),
    ("human_takeover","HUMAN_TAKEOVER"),("ignored","RELATIONSHIP_IGNORED"),
    ("sleeping","SLEEPING"),("send_uncertain","SEND_UNCERTAIN")])
def test_stronger_authorities_suppress_adjustment(flag,reason):
    decision=PeakEngagementPolicy().evaluate(now=utc(2026,7,3,1,30),availability_state="ACTIVE",**{flag:True})
    assert decision.active and not decision.pacing_eligible and decision.suppressed_by==reason


@pytest.mark.parametrize("state,eligible",[("AVAILABLE",True),("ACTIVE",True),
    ("INTERMITTENT",True),("BUSY",False),("AWAY",False),("SLEEPING",False)])
def test_only_ordinary_available_states_are_eligible(state,eligible):
    assert PeakEngagementPolicy().evaluate(now=utc(2026,7,3,1,30),availability_state=state).pacing_eligible is eligible


class Repo:
    def __init__(self,state):self.state=state
    def current_or_transition(self,**kwargs):
        now=kwargs["now"]
        return SimpleNamespace(state=self.state,transition_at=now.replace(minute=now.minute+10),
            session_id="s",started_at=now,daypart="EVENING")


def test_availability_multiplier_composes_once_and_preserves_floor():
    now=utc(2026,7,3,1,30)
    service=AvaHumanAvailabilityService(now=lambda:now,uniform=lambda *_:20,
        repository=Repo(AvaAvailabilityState.AVAILABLE))
    result=service.calculate(peak_engagement_context={})
    assert result.delay_seconds==14 and result.peak_engagement["pacingAdjustment"]["eligible"]
    floor=AvaHumanAvailabilityService(now=lambda:now,uniform=lambda *_:8,
        repository=Repo(AvaAvailabilityState.AVAILABLE)).calculate(peak_engagement_context={})
    assert floor.delay_seconds==8


def test_diagnostics_are_bounded_and_warmup_is_projection_only():
    data=PeakEngagementPolicy().evaluate(now=utc(2026,7,3,1,30),availability_state="ACTIVE").diagnostics()
    assert data["investmentAdjustment"]=="ORDINARY_BALANCED_TO_ENGAGED"
    assert data["warmupOverrideApplied"] is True
    assert "warmup_depth" not in data and data["policy"]=="PEAK_ENGAGEMENT_V1"
