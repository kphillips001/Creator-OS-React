from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from app.services.market_tier_resource_gate_service import MarketTierResourceGateService
from app.services.relationships_service import RelationshipsService

SCOPE=dict(creator_profile_id=1,fanvue_account_id=2,telegram_user_id=3,telegram_chat_id=4)
class Tiers:
 def __init__(self,tier):self.tier=tier
 def active(self,**_):return None if self.tier=='UNCLASSIFIED' else SimpleNamespace(market_tier=SimpleNamespace(value=self.tier))
class Accounting:
 ZONE=__import__('zoneinfo').ZoneInfo('America/Chicago')
 def __init__(self,used):self.used=used;self.calls=0
 def today(self,**_):
  self.calls+=1;start=datetime(2026,9,13,5,tzinfo=timezone.utc);end=datetime(2026,9,14,5,tzinfo=timezone.utc)
  return {'replies_used_today':self.used,'business_day_start':start,'business_day_end':end,'next_reset_at':end}
class Repo:
 def __init__(self):self.budget=None;self.events=[]
 def medium_budget(self,**values):
  if self.budget is None:self.budget=values['sampled_budget']
  return {'daily_reply_budget':self.budget}
 def event(self,**values):self.events.append(values)
def decision(value=False):return SimpleNamespace(commercial_bypass_eligible=value)
def gate(tier,used,sample=lambda:7):
 repo=Repo();accounting=Accounting(used)
 return MarketTierResourceGateService(tiers=Tiers(tier),accounting=accounting,repository=repo,sample=sample),repo,accounting

def test_medium_budget_stable_and_range_owned_by_repository():
 service,repo,_=gate('MEDIUM',0,lambda:6)
 assert service.evaluate(**SCOPE,operation_id='a',commercial_decision=decision()).evidence['daily_reply_budget']==6
 service.sample=lambda:10
 assert service.evaluate(**SCOPE,operation_id='b',commercial_decision=decision()).evidence['daily_reply_budget']==6

@pytest.mark.parametrize('tier,used,allowed,status',[
 ('HIGH',99,True,'NONE'),('UNCLASSIFIED',99,True,'NONE'),
 ('MEDIUM',6,True,'NONE'),('MEDIUM',7,False,'MEDIUM_MARKET_LIMIT'),
 ('LOW',1,True,'NONE'),('LOW',2,False,'LOW_MARKET_LIMIT')])
def test_limits(tier,used,allowed,status):
 service,_,accounting=gate(tier,used)
 result=service.evaluate(**SCOPE,operation_id='x',commercial_decision=decision())
 assert result.allowed is allowed and result.operational_status==status and accounting.calls==1

@pytest.mark.parametrize('tier',["MEDIUM","LOW"])
def test_commercial_and_buyer_bypass_but_hvp_does_not(tier):
 used=10
 assert gate(tier,used)[0].evaluate(**SCOPE,operation_id='c',commercial_decision=decision(True)).allowed
 assert gate(tier,used)[0].evaluate(**SCOPE,operation_id='b',commercial_decision=decision(),verified_buyer=True).allowed
 assert not gate(tier,used)[0].evaluate(**SCOPE,operation_id='h',commercial_decision=decision(),high_value_prospect=True).allowed

def test_market_limits_are_intentional_operational_states():
 inbox={'control_mode':'AVA_AUTO','last_customer_inbound_at':datetime.now(timezone.utc),
  'last_visible_outbound_at':None,'operation_state':'SUPPRESSED',
  'operation_last_error':'LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED',
  'delivery_payload':{'marketResourcePolicy':{'market_tier':'LOW','replies_used_today':2,'daily_reply_budget':2,'next_reset_at':'tomorrow'}}}
 result=RelationshipsService._operational_projection(inbox)
 assert result['operationalStatus']=='LOW_MARKET_LIMIT'
 assert result['repliesUsedToday']==2 and result['dailyReplyBudget']==2
