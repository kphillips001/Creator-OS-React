from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from unittest.mock import MagicMock
import json
import pytest
from app.services.market_tier_resource_gate_service import MarketTierResourceGateService
from app.services.relationships_service import RelationshipsService
from app.repositories.market_tier_resource_gate_repository import (
 MarketTierResourceGateRepository,durable_resource_gate_evidence)

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
class ActiveSales:
 def __init__(self,active=False,status='CLICKED'):self.active=active;self.status=status
 def project(self,**_):return {'active':self.active,'offer_status':self.status}
class FollowThrough:
 def __init__(self,count=0):self.count=count
 def relationship_nonconversion(self,**_):return {'nonconversion_count':self.count,'last_confirmed_nudge_at':None}
def decision(value=False):return SimpleNamespace(commercial_bypass_eligible=value)
def gate(tier,used,sample=lambda:7,active=False,nonconversion=0):
 repo=Repo();accounting=Accounting(used)
 return MarketTierResourceGateService(tiers=Tiers(tier),accounting=accounting,repository=repo,sample=sample,active_sales=ActiveSales(active),follow_through=FollowThrough(nonconversion)),repo,accounting

def test_resource_gate_evidence_normalizes_nested_aware_datetime_only():
 stamp=datetime(2026,9,16,19,44,4,961387,tzinfo=timezone(timedelta(hours=-5)))
 original={'post_nudge_nonconversion':{'last_confirmed_nudge_at':stamp},
  'items':[None,'2026-09-16T19:44:04-05:00',{'at':stamp}],
  'market_tier':'MEDIUM'}
 assert durable_resource_gate_evidence(original)=={
  'post_nudge_nonconversion':{
   'last_confirmed_nudge_at':'2026-09-16T19:44:04.961387-05:00'},
  'items':[None,'2026-09-16T19:44:04-05:00',
   {'at':'2026-09-16T19:44:04.961387-05:00'}],
  'market_tier':'MEDIUM'}

def test_resource_gate_evidence_rejects_naive_datetime_and_unknown_objects():
 with pytest.raises(ValueError,match='timezone-aware'):
  durable_resource_gate_evidence({'at':datetime(2026,9,16,19,44)})
 with pytest.raises(TypeError,match='Unsupported market-tier'):
  durable_resource_gate_evidence({'value':object()})

def test_resource_gate_repository_persists_exact_production_datetime_shape():
 stamp=datetime(2026,9,16,19,44,4,961387,
  tzinfo=timezone(timedelta(hours=-5)))
 cursor=MagicMock();cursor.fetchone.return_value=None
 connection=MagicMock();connection.__enter__.return_value=connection
 connection.cursor.return_value.__enter__.return_value=cursor
 repository=MarketTierResourceGateRepository(lambda:connection)
 repository.event(**SCOPE,operation_id=None,idempotency_key='datetime-shape',
  event_type='BUDGET_CONSULTED',evidence={
   'post_nudge_nonconversion':{'nonconversion_count':1,
    'last_confirmed_nudge_at':stamp}})
 encoded=cursor.execute.call_args.args[1][-1]
 assert json.loads(encoded)['post_nudge_nonconversion']=={
  'nonconversion_count':1,
  'last_confirmed_nudge_at':'2026-09-16T19:44:04.961387-05:00'}

def test_resource_gate_decision_semantics_remain_unmodified_by_normalization():
 service,repo,_=gate('LOW',2,nonconversion=1)
 result=service.evaluate(**SCOPE,operation_id='unchanged',commercial_decision=decision())
 persisted=durable_resource_gate_evidence(repo.events[-1]['evidence'])
 assert result.allowed is False
 assert result.operational_status=='LOW_MARKET_LIMIT'
 assert result.reason=='LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED'
 assert persisted==result.evidence

def test_medium_post_nudge_nonconversion_ends_ordinary_sales_override():
 service,_,_=gate('MEDIUM',0,active=True,nonconversion=1)
 result=service.evaluate(**SCOPE,operation_id='ordinary',commercial_decision=decision())
 assert result.allowed and result.operational_status=='NONE'
 assert result.evidence['post_nudge_backoff'] is True
 assert service.evaluate(**SCOPE,operation_id='direct',commercial_decision=decision(True)).allowed

def test_post_nudge_backoff_applies_before_daily_budget_is_exhausted():
 service,_,_=gate('MEDIUM',0,active=True,nonconversion=1)
 result=service.evaluate(**SCOPE,operation_id='ordinary-early',commercial_decision=decision())
 assert result.allowed and result.evidence['post_nudge_backoff'] is True

def test_buyer_and_hvp_are_not_subject_to_zero_purchase_medium_backoff():
 service,_,_=gate('MEDIUM',0,active=True,nonconversion=1)
 assert service.evaluate(**SCOPE,operation_id='buyer',commercial_decision=decision(),verified_buyer=True).allowed
 assert service.evaluate(**SCOPE,operation_id='hvp',commercial_decision=decision(),high_value_prospect=True).allowed

@pytest.mark.parametrize('tier',['HIGH','MEDIUM','LOW','UNCLASSIFIED'])
def test_durable_post_nudge_backoff_precedes_tier_budget_and_active_intent(tier):
 service,_,_=gate(tier,0,active=False,nonconversion=1)
 result=service.evaluate(**SCOPE,operation_id=f'backoff-{tier}',commercial_decision=decision())
 assert result.allowed and result.evidence['post_nudge_backoff'] is True

def test_hvp_zero_purchase_is_backed_off_but_hvp_buyer_is_protected():
 service,_,_=gate('HIGH',0,active=False,nonconversion=1)
 assert service.evaluate(**SCOPE,operation_id='hvp-prospect',commercial_decision=decision(),high_value_prospect=True).allowed
 assert service.evaluate(**SCOPE,operation_id='hvp-buyer',commercial_decision=decision(),high_value_prospect=True,verified_buyer=True).allowed

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

@pytest.mark.parametrize('tier,status',[('MEDIUM','PRESENTED'),('MEDIUM','CLICKED'),('LOW','PRESENTED')])
def test_active_sales_opportunity_overrides_exhausted_nurture_only(tier,status):
 service,repo,_=gate(tier,10,active=True);service.active_sales.status=status
 result=service.evaluate(**SCOPE,operation_id='sale',commercial_decision=decision())
 assert result.allowed and result.operational_status=='SALES_OVERRIDE'
 assert result.evidence['replies_used_today']==10
 assert result.evidence['prospect_nurture_budget_status']=='EXHAUSTED'
 assert repo.events[-1]['event_type']=='SALES_OPPORTUNITY_OVERRIDE'

def test_market_limits_are_intentional_operational_states():
 inbox={'control_mode':'AVA_AUTO','last_customer_inbound_at':datetime.now(timezone.utc),
  'last_visible_outbound_at':None,'operation_state':'SUPPRESSED',
  'operation_last_error':'LOW_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED',
  'delivery_payload':{'marketResourcePolicy':{'market_tier':'LOW','replies_used_today':2,'daily_reply_budget':2,'next_reset_at':'tomorrow'}}}
 result=RelationshipsService._operational_projection(inbox)
 assert result['operationalStatus']=='LOW_MARKET_LIMIT'
 assert result['repliesUsedToday']==2 and result['dailyReplyBudget']==2
