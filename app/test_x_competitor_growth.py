from datetime import datetime,timezone,timedelta
from unittest.mock import Mock

from app.providers.x_twitterapi_io import TwitterApiIoError
from app.services.x_competitor_growth_service import growth_for_window
from app.services.x_competitor_profile_refresh_service import XCompetitorProfileRefreshService

NOW=datetime(2026,8,16,12,tzinfo=timezone.utc)
def snapshot(days:int,followers:int,identifier:str="x"):return {"id":identifier,"observed_at":NOW-timedelta(days=days),"followers_count":followers}

def test_growth_exact_positive_negative_zero_and_zero_denominator():
    assert growth_for_window([snapshot(7,100),snapshot(0,120)],7,2)["percent"]==20
    assert growth_for_window([snapshot(30,100),snapshot(0,80)],30,4)["raw"]==-20
    assert growth_for_window([snapshot(7,100),snapshot(0,100)],7,2)["percent"]==0
    assert growth_for_window([snapshot(7,0),snapshot(0,100)],7,2) is None

def test_nearest_tolerance_and_deterministic_earlier_tie():
    result=growth_for_window([snapshot(9,90,"early"),snapshot(5,95,"late"),snapshot(0,100)],7,2)
    assert result["raw"]==10 and result["baseline_observed_at"]==NOW-timedelta(days=9)
    assert growth_for_window([snapshot(10,90),snapshot(0,100)],7,2) is None
    assert growth_for_window([snapshot(34,90),snapshot(0,100)],30,4) is not None
    assert growth_for_window([snapshot(35,90),snapshot(0,100)],30,4) is None

def test_profile_refresh_is_one_profile_call_per_tracked_competitor_and_partial_safe():
    repository=Mock();repository.begin_global_refresh.return_value={"id":"run"};repository.list_tracked_competitors.return_value=[{"id":"1","username":"one"},{"id":"2","username":"two"}]
    provider=Mock();profile=Mock();provider.get_user_by_username.side_effect=[profile,TwitterApiIoError("failed")]
    result=XCompetitorProfileRefreshService(provider=provider,repository=repository,clock=lambda:NOW).refresh()
    assert result["considered"]==2 and result["refreshed"]==1 and result["failed"]==1
    assert provider.get_user_by_username.call_count==2 and repository.persist_profile_refresh.call_count==1
    repository.persist_profile_refresh.assert_called_once_with("1",profile,observed_at=NOW)
    repository.finish_global_refresh.assert_called_once_with("run",status="PARTIAL",completed_at=NOW,considered=2,succeeded=1,failed=1)
