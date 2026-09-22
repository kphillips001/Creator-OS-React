import random
from dataclasses import dataclass
from app.repositories.market_tier_resource_gate_repository import MarketTierResourceGateRepository
from app.repositories.relationship_market_tier_repository import RelationshipMarketTierRepository
from app.services.market_tier_reply_accounting_service import MarketTierReplyAccountingService

@dataclass(frozen=True)
class MarketTierResourceDecision:
 allowed:bool; operational_status:str; reason:str|None; evidence:dict

class MarketTierResourceGateService:
 def __init__(self,*,tiers=None,accounting=None,repository=None,sample=None,active_sales=None,follow_through=None,value_attention=None):
  self.tiers=tiers or RelationshipMarketTierRepository();self.accounting=accounting or MarketTierReplyAccountingService();self.repository=repository or MarketTierResourceGateRepository();self.sample=sample or (lambda:random.randint(5,10));self.active_sales=active_sales;self.follow_through=follow_through;self.value_attention=value_attention
 def evaluate(self,*,operation_id,commercial_decision,verified_buyer=False,high_value_prospect=False,**scope):
  row=self.tiers.active(**scope);tier=row.market_tier.value if row else 'UNCLASSIFIED'
  used=self.accounting.today(**scope);budget=None
  if tier=='MEDIUM':
   local=used['business_day_start'].astimezone(self.accounting.ZONE)
   assigned=self.repository.medium_budget(**scope,business_date=local.date(),business_day_start=used['business_day_start'],business_day_end=used['business_day_end'],sampled_budget=int(self.sample()))
   budget=int(assigned['daily_reply_budget'])
   if assigned.get('created'):self.repository.event(**scope,operation_id=operation_id,idempotency_key=f"{scope['creator_profile_id']}:{scope['fanvue_account_id']}:{scope['telegram_user_id']}:{scope['telegram_chat_id']}:{local.date()}:MEDIUM_DAILY_BUDGET_ASSIGNED",event_type='MEDIUM_DAILY_BUDGET_ASSIGNED',evidence={'daily_reply_budget':budget,'business_date':str(local.date())})
  elif tier=='LOW':budget=2
  bypass=bool(commercial_decision.commercial_bypass_eligible)
  if self.active_sales is None:
   from app.services.active_sales_opportunity_service import ActiveSalesOpportunityService
   self.active_sales=ActiveSalesOpportunityService()
  opportunity=self.active_sales.project(**scope)
  if self.follow_through is None:
   from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
   self.follow_through=ActiveOfferFollowThroughRepository()
  nonconversion=self.follow_through.relationship_nonconversion(**scope)
  if self.value_attention is None:
   from app.services.customer_value_attention_service import CustomerValueAttentionService
   self.value_attention=CustomerValueAttentionService()
  attention=self.value_attention.project(commerce_memory={'schemaVersion':'market-resource-gate','verifiedPurchaseCount':1 if verified_buyer else 0},behavior={'market_tier':tier,'confirmed_post_nudge_nonconversion_count':int(nonconversion.get('nonconversion_count') or 0),'fresh_direct_intent':bypass,'active_unresolved_opportunity':bool(opportunity['active'])})
  post_nudge_backoff=bool(int(nonconversion.get('nonconversion_count') or 0)>0
   and not bypass and not verified_buyer
   and not bool(getattr(commercial_decision,'mandatory_response_obligation',False)))
  sales_override=bool(opportunity['active'] and budget is not None and used['replies_used_today']>=budget and not verified_buyer and not post_nudge_backoff)
  evidence={'market_tier':tier,'replies_used_today':used['replies_used_today'],'daily_reply_budget':budget,'business_day_start':used['business_day_start'].isoformat(),'business_day_end':used['business_day_end'].isoformat(),'next_reset_at':used['next_reset_at'].isoformat(),'high_value_prospect':bool(high_value_prospect),'commercial_bypass_evaluated':True,'commercial_bypass_eligible':bypass,'active_sales_opportunity':opportunity,'sales_opportunity_override':sales_override,'post_nudge_nonconversion':nonconversion,'post_nudge_backoff':post_nudge_backoff,'verified_buyer_evaluated':True,'verified_buyer':bool(verified_buyer),'prospect_nurture_budget_status':'EXHAUSTED' if budget is not None and used['replies_used_today']>=budget else 'AVAILABLE'}
  limited=(budget is not None and used['replies_used_today']>=budget and not bypass and not sales_override and not verified_buyer)
  event_type=('VERIFIED_BUYER_BYPASS' if verified_buyer and budget is not None else 'SALES_OPPORTUNITY_OVERRIDE' if sales_override else 'COMMERCIAL_BYPASS' if bypass and budget is not None else f'{tier}_EXHAUSTED' if limited else 'BUDGET_CONSULTED')
  self.repository.event(**scope,operation_id=operation_id,idempotency_key=f'{operation_id}:{event_type}',event_type=event_type,evidence=evidence)
  if not limited:return MarketTierResourceDecision(True,'SALES_OVERRIDE' if sales_override else 'NONE',None,evidence)
  return MarketTierResourceDecision(False,f'{tier}_MARKET_LIMIT',f'{tier}_MARKET_DAILY_REPLY_BUDGET_EXHAUSTED',evidence)
 def reconsider_after_promotion(self,*,new_tier,high_value_prospect=False,verified_buyer=False,**scope):
  row=self.repository.latest_limited(**scope)
  if not row:return None
  if new_tier=='HIGH':allowed=True
  else:
   probe=SimpleCommercialDecision()
   allowed=self.evaluate(**scope,operation_id=row['operation_id'],commercial_decision=probe,verified_buyer=verified_buyer,high_value_prospect=high_value_prospect).allowed
  if not allowed:return None
  from app.services.ava_human_availability_service import AvaHumanAvailabilityService
  available=AvaHumanAvailabilityService().calculate(
   market_tier=new_tier,high_value_prospect=high_value_prospect).available_at
  released=self.repository.release(row['operation_id'],available)
  if released:self.repository.event(**scope,operation_id=row['operation_id'],idempotency_key=f"{row['operation_id']}:TIER_PROMOTION_RELEASE",event_type='TIER_PROMOTION_RELEASE',evidence={'new_market_tier':new_tier})
  return released

class SimpleCommercialDecision:
 commercial_bypass_eligible=False
