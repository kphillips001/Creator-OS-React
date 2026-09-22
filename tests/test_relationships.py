from datetime import datetime,timezone,timedelta

import pytest
from fastapi import HTTPException
from unittest.mock import patch
from app.api import relationships as relationships_api
from app.services.relationships_service import RelationshipsService

BASE=datetime(2026,9,6,12,tzinfo=timezone.utc)

class PeopleRepo:
 def people(self,**_): return [
  {"telegram_user_id":1,"username":"NewName","display_name":"Alex","mapping_id":None,"verification_status":None,"mapping_active":None,"relationship_state":{}},
  {"telegram_user_id":2,"username":None,"display_name":None,"mapping_id":2,"verification_status":"VERIFIED","mapping_active":True,"local_fanvue_user_id":4,"external_fanvue_user_uuid":"buyer","customer_commerce_profile_id":"profile","profile_state":"REPEAT_BUYER","lifetime_gross_minor":5000,"purchase_count":2},
  {"telegram_user_id":3,"username":"maybe","display_name":None,"mapping_id":3,"verification_status":"PENDING","mapping_active":True,"profile_state":"HIGH_VALUE","lifetime_gross_minor":99999,"purchase_count":9}]
 def inbound_events(self,**_): return [
  {"telegram_user_id":1,"event_key":"in-1","occurred_at":BASE,"source":"ordinary"},
  {"telegram_user_id":1,"event_key":"in-1","occurred_at":BASE,"source":"chat"},
  {"telegram_user_id":2,"event_key":"in-2","occurred_at":BASE+timedelta(hours=1),"source":"chat"},
  {"telegram_user_id":3,"event_key":"in-3","occurred_at":BASE-timedelta(hours=1),"source":"chat"}]
 def ava_events(self,**_): return []
 def current_customer_state(self,**_): return {2:{"active_purchase_intent":True,"active_sales_session":True}}

class MessageRepo:
 def latest_messages(self,**_):
  return {user:self.messages(telegram_user_id=user)[-1] for user in (1,2,3)}
 def messages(self,telegram_user_id,**_):
  offset={1:0,2:1,3:-1}[telegram_user_id]
  return [{"event_key":f"{telegram_user_id}-{i}","direction":"CUSTOMER" if i%2==0 else "AVA","content":f"message {i}","occurred_at":BASE+timedelta(hours=offset,seconds=i),"telegram_message_id":i,"message_type":"ORDINARY_CHAT","purchase_intent_id":None} for i in range(6)]

def service(): return RelationshipsService(people_repository=PeopleRepo(),messages_repository=MessageRepo())

def test_inventory_includes_mapped_unmapped_no_username_and_orders_latest():
 result=service().list(creator_profile_id=7,fanvue_account_id=8)
 assert [row["telegramUserId"] for row in result["items"]]==[2,1,3]
 assert result["items"][0]["buyerStatus"]=="REPEAT_BUYER"
 assert result["items"][1]["identityStatus"]=="UNMAPPED"
 assert result["items"][2]["buyerStatus"] is None

def test_inventory_search_is_case_insensitive_and_supports_numeric_id():
 assert [r["telegramUserId"] for r in service().list(creator_profile_id=7,fanvue_account_id=8,search="alex")["items"]]==[1]
 assert [r["telegramUserId"] for r in service().list(creator_profile_id=7,fanvue_account_id=8,search="2")["items"]]==[2]

def test_inventory_cursor_paginates_without_duplicate_people():
 first=service().list(creator_profile_id=7,fanvue_account_id=8,limit=2)
 second=service().list(creator_profile_id=7,fanvue_account_id=8,limit=2,cursor=first["nextCursor"])
 assert len(first["items"])==2 and len(second["items"])==1
 assert {r["personKey"] for r in first["items"]}.isdisjoint({r["personKey"] for r in second["items"]})

def test_explicit_latest_activity_matches_default():
 default=service().list(creator_profile_id=7,fanvue_account_id=8)
 explicit=service().list(creator_profile_id=7,fanvue_account_id=8,sort="LATEST_ACTIVITY")
 assert [r["personKey"] for r in default["items"]]==[r["personKey"] for r in explicit["items"]]

def test_lifetime_spend_uses_verified_value_then_activity_and_stable_identity():
 result=service().list(creator_profile_id=7,fanvue_account_id=8,sort="LIFETIME_SPEND")
 assert [r["telegramUserId"] for r in result["items"]]==[2,1,3]
 assert result["items"][1]["lifetimeVerifiedRevenueMinor"] is None
 assert result["items"][2]["lifetimeVerifiedRevenueMinor"] is None

def test_search_sort_and_pagination_compose_deterministically():
 first=service().list(creator_profile_id=7,fanvue_account_id=8,search="2",
                      sort="LIFETIME_SPEND",limit=1)
 assert [r["telegramUserId"] for r in first["items"]]==[2]
 assert first["sort"]=="LIFETIME_SPEND"

class InboxRepo(MessageRepo):
 def inbox_state(self,**_): return {
  1:{"control_mode":"HUMAN_OPERATOR","last_customer_inbound_at":BASE+timedelta(minutes=2),"last_visible_outbound_at":BASE},
  2:{"control_mode":"AVA_AUTO","last_customer_inbound_at":BASE,"last_visible_outbound_at":BASE+timedelta(minutes=1)},
  3:{"control_mode":"AVA_AUTO","last_customer_inbound_at":BASE,"last_visible_outbound_at":None,"latest_inbound_text":"Hey","operation_state":"SUPPRESSED"}}

def inbox_service(): return RelationshipsService(people_repository=PeopleRepo(),messages_repository=InboxRepo())

def test_inbox_summary_and_deterministic_attention_use_confirmed_timestamps():
 result=inbox_service().list(creator_profile_id=7,fanvue_account_id=8)
 assert result["summary"]=={"total":3,"needsAttention":1,"buyers":1,"prospects":2,"manual":1,
                            "highValueProspects":0,"replyScheduled":0,"ignored":0,
                            "operationalCategories":{"HUMAN_ATTENTION_REQUIRED":1,"SYSTEM_INCIDENT":0,"DELIVERY_UNCERTAIN":0,"RECOVERY_PENDING":0,"NO_REPLY_REQUIRED":1}}
 assert next(row for row in result["items"] if row["telegramUserId"]==1)["needsAttention"] is False
 assert next(row for row in result["items"] if row["telegramUserId"]==2)["needsAttention"] is False
 assert next(row for row in result["items"] if row["telegramUserId"]==3)["needsAttention"] is True

class TimeWasterInboxRepo(InboxRepo):
 def commercial_attention_by_person(self,**_): return {
  1:{"failed_presentation_count":8,"verified_purchase_count":0},
  2:{"failed_presentation_count":12,"verified_purchase_count":2},
  3:{"failed_presentation_count":7,"verified_purchase_count":0},
 }

def test_time_waster_projection_uses_distinct_failure_threshold_and_purchase_override():
 result=RelationshipsService(people_repository=PeopleRepo(),messages_repository=TimeWasterInboxRepo()).list(
  creator_profile_id=7,fanvue_account_id=8)
 rows={row["telegramUserId"]:row for row in result["items"]}
 assert rows[1]["timeWaster"] is True
 assert rows[1]["failedPresentationCount"]==8
 assert rows[2]["timeWaster"] is False
 assert rows[2]["verifiedPurchaseCount"]==2
 assert rows[3]["timeWaster"] is False

@pytest.mark.parametrize("selected,expected",[
 ("NEEDS_ATTENTION",{3}),("BUYERS",{2}),("PROSPECTS",{1,3}),
 ("MANUAL",{1}),("ACTIVE_SESSION",{2}),("ACTIVE_INTENT",{2})])
def test_inbox_filters_compose_with_canonical_projection(selected,expected):
 result=inbox_service().list(creator_profile_id=7,fanvue_account_id=8,filter=selected)
 assert {row["telegramUserId"] for row in result["items"]}==expected

def test_search_sort_and_filter_compose():
 result=inbox_service().list(creator_profile_id=7,fanvue_account_id=8,
  search="alex",sort="LIFETIME_SPEND",filter="MANUAL")
 assert [row["telegramUserId"] for row in result["items"]]==[1]


class CountryTierPeopleRepo:
 def people(self,**_): return [
  {"telegram_user_id":user,"username":f"user{user}","display_name":name,
   "mapping_id":user if buyer else None,"verification_status":"VERIFIED" if buyer else None,
   "mapping_active":buyer,"local_fanvue_user_id":user if buyer else None,
   "customer_commerce_profile_id":f"profile-{user}" if buyer else None,
   "profile_state":"BUYER" if buyer else None,"lifetime_gross_minor":100 if buyer else None,
   "purchase_count":1 if buyer else None,"relationship_state":{}}
  for user,name,buyer in ((11,"High older",False),(12,"High newest",False),
                          (13,"Medium",False),(14,"Low buyer",True),(15,"Unclassified",False))]
 def inbound_events(self,**_): return [
  {"telegram_user_id":user,"event_key":f"in-{user}","occurred_at":BASE+timedelta(minutes=minute),"source":"chat"}
  for user,minute in ((11,1),(12,5),(13,4),(14,3),(15,6))]
 def ava_events(self,**_): return []
 def current_customer_state(self,**_): return {}

class CountryTierMessageRepo(MessageRepo):
 def latest_messages(self,**_): return {
  user:{"event_key":f"in-{user}","direction":"CUSTOMER","content":f"message {user}",
        "occurred_at":BASE+timedelta(minutes=minute),"telegram_message_id":user,
        "message_type":"ORDINARY_CHAT","purchase_intent_id":None}
  for user,minute in ((11,1),(12,5),(13,4),(14,3),(15,6))}
 def inbox_state(self,**_): return {
  11:{"telegram_chat_id":11,"market_tier":"HIGH"},
  12:{"telegram_chat_id":12,"market_tier":"HIGH"},
  13:{"telegram_chat_id":13,"market_tier":"MEDIUM",
      "last_customer_inbound_at":BASE+timedelta(minutes=4),"last_visible_outbound_at":None,"latest_inbound_text":"Hey","operation_state":"SUPPRESSED"},
  14:{"telegram_chat_id":14,"market_tier":"LOW","control_mode":"HUMAN_OPERATOR"},
  15:{"telegram_chat_id":15}}

def country_tier_service():
 return RelationshipsService(people_repository=CountryTierPeopleRepo(),messages_repository=CountryTierMessageRepo())

@pytest.mark.parametrize("selected_sort,expected",[
 ("COUNTRY_TIER_HIGH_TO_LOW",[12,11,13,14,15]),
 ("COUNTRY_TIER_LOW_TO_HIGH",[14,13,12,11,15])])
def test_country_tier_sort_is_global_stable_and_unclassified_last(selected_sort,expected):
 result=country_tier_service().list(creator_profile_id=7,fanvue_account_id=8,
                                    sort=selected_sort,limit=2)
 second=country_tier_service().list(creator_profile_id=7,fanvue_account_id=8,
   sort=selected_sort,limit=10,cursor=result["nextCursor"])
 assert [row["telegramUserId"] for row in result["items"]+second["items"]]==expected

@pytest.mark.parametrize("tiers,expected",[
 (["HIGH"],{11,12}),(["MEDIUM"],{13}),(["LOW"],{14}),
 (["UNCLASSIFIED"],{15}),(["HIGH","MEDIUM"],{11,12,13})])
def test_country_tier_filter_accepts_single_multiple_and_unclassified(tiers,expected):
 result=country_tier_service().list(creator_profile_id=7,fanvue_account_id=8,
                                    country_tiers=tiers)
 assert {row["telegramUserId"] for row in result["items"]}==expected

def test_country_tier_composes_with_search_buyer_prospect_and_manual_filters():
 service=country_tier_service()
 assert [r["telegramUserId"] for r in service.list(creator_profile_id=7,fanvue_account_id=8,
  search="newest",filter="PROSPECTS",country_tiers=["HIGH"])["items"]]==[12]
 assert [r["telegramUserId"] for r in service.list(creator_profile_id=7,fanvue_account_id=8,
  filter="BUYERS",country_tiers=["LOW"])["items"]]==[14]
 assert [r["telegramUserId"] for r in service.list(creator_profile_id=7,fanvue_account_id=8,
  filter="MANUAL",country_tiers=["LOW"])["items"]]==[14]
 assert [r["telegramUserId"] for r in service.list(creator_profile_id=7,fanvue_account_id=8,
  filter="NEEDS_ATTENTION",country_tiers=["MEDIUM"])["items"]]==[13]

def test_country_tier_filter_rejects_unknown_values():
 with pytest.raises(ValueError,match="Country Tier"):
  country_tier_service().list(creator_profile_id=7,fanvue_account_id=8,
                              country_tiers=["PREMIUM"])


class IgnoredInboxRepo(InboxRepo):
 def inbox_state(self,**kwargs):
  state=super().inbox_state(**kwargs)
  state[3]={**state[3],"communication_disposition":"IGNORED",
            "operator_classification":"HIGH_VALUE_PROSPECT","market_tier":"HIGH"}
  return state

def ignored_inbox_service():
 return RelationshipsService(people_repository=PeopleRepo(),messages_repository=IgnoredInboxRepo())

def test_ignored_relationship_is_excluded_from_every_active_filter_and_counter():
 service=ignored_inbox_service()
 assert {row["telegramUserId"] for row in service.list(
  creator_profile_id=7,fanvue_account_id=8)["items"]}=={1,2}
 for selected in ("PROSPECTS","BUYERS","NEEDS_ATTENTION","MANUAL",
                  "ACTIVE_SESSION","ACTIVE_INTENT","HIGH_VALUE_PROSPECT"):
  assert all(not row["ignored"] for row in service.list(
   creator_profile_id=7,fanvue_account_id=8,filter=selected)["items"])
 summary=service.list(creator_profile_id=7,fanvue_account_id=8)["summary"]
 assert summary["total"]==2 and summary["ignored"]==1
 assert summary["prospects"]==1 and summary["needsAttention"]==0

def test_ignored_filter_search_sort_and_pagination_are_scoped_to_ignored_only():
 service=ignored_inbox_service()
 result=service.list(creator_profile_id=7,fanvue_account_id=8,filter="IGNORED",
                     search="maybe",sort="LATEST_ACTIVITY",limit=1)
 assert [row["telegramUserId"] for row in result["items"]]==[3]
 assert result["items"][0]["marketTier"]=="HIGH"
 assert result["items"][0]["highValueProspect"] is True
 assert service.list(creator_profile_id=7,fanvue_account_id=8,
                     filter="IGNORED",search="alex")["items"]==[]


def test_transcript_loads_latest_then_eventually_reaches_first_in_order():
 latest=service().messages(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=1,limit=2)
 older=service().messages(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=1,limit=2,cursor=latest["olderCursor"])
 first=service().messages(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=1,limit=2,cursor=older["olderCursor"])
 combined=first["items"]+older["items"]+latest["items"]
 assert [m["content"] for m in combined]==[f"message {i}" for i in range(6)]
 assert first["hasMoreOlder"] is False


def test_keyset_transcript_pages_are_stable_without_duplicates_or_gaps():
 class KeysetRepo(MessageRepo):
  def relationship_exists(self,**_): return True
  def messages(self,telegram_user_id,before_occurred_at=None,before_event_key=None,
               limit=None,**_):
   rows=super().messages(telegram_user_id)
   rows[2]["occurred_at"]=rows[3]["occurred_at"]
   rows=sorted(rows,key=lambda row:(row["occurred_at"],row["event_key"]))
   if before_occurred_at is not None:
    rows=[row for row in rows if (row["occurred_at"],row["event_key"])<
          (before_occurred_at,before_event_key)]
   rows=list(reversed(rows))[:limit]
   return list(reversed(rows))
 keyset=RelationshipsService(people_repository=PeopleRepo(),messages_repository=KeysetRepo())
 pages=[]; cursor=None
 while True:
  page=keyset.messages(creator_profile_id=7,fanvue_account_id=8,
                       telegram_user_id=1,limit=2,cursor=cursor,
                       include_person=False)
  pages.insert(0,page["items"]);cursor=page["olderCursor"]
  if not cursor: break
 combined=[item for page in pages for item in page]
 assert len(combined)==6
 assert len({item["eventKey"] for item in combined})==6
 assert {item["content"] for item in combined}=={f"message {i}" for i in range(6)}
 assert all("person" not in page for page in [keyset.messages(
  creator_profile_id=7,fanvue_account_id=8,telegram_user_id=1,
  include_person=False)])

def test_unknown_account_scoped_person_is_rejected():
 with pytest.raises(LookupError): service().messages(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=99)

def test_verified_mapped_buyer_without_prospect_resolves_control_context():
 class MappedBuyerRepo(MessageRepo):
  def control_context(self,telegram_user_id,**_):
   assert telegram_user_id==2
   return {"telegram_chat_id":2,"telegram_identity_mapping_id":2,
           "local_fanvue_user_id":4,"external_fanvue_user_uuid":"buyer",
           "conversation_thread_id":None,"latest_inbound_telegram_message_id":5,
           "active_purchase_intent":False,"active_sales_session":False}
 mapped=RelationshipsService(people_repository=PeopleRepo(),messages_repository=MappedBuyerRepo())
 context=mapped.control_context(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=2)
 assert context["telegram_identity_mapping_id"]==2
 assert context["telegram_chat_id"]==2

class IntelligenceRepo(MessageRepo):
 def control_context(self,telegram_user_id,**_):
  return {"telegram_chat_id":telegram_user_id,
          "telegram_identity_mapping_id":2 if telegram_user_id==2 else None,
          "local_fanvue_user_id":4 if telegram_user_id==2 else None,
          "external_fanvue_user_uuid":"buyer" if telegram_user_id==2 else None,
          "conversation_thread_id":None,
          "latest_inbound_telegram_message_id":5,
          "active_purchase_intent":telegram_user_id==2,
          "active_sales_session":telegram_user_id==2}
 def intelligence(self,telegram_user_id,**_):
  if telegram_user_id==1:
   return {"intents":[],"purchases":[],"active_session":None,
           "prospect":{"preference_state":{"records":[
            {"status":"current","category":"fact","key":"location","value":"Austin"},
            {"status":"current","category":"pet","key":"pet_name","value":"Milo"}]}}}
  return {"intents":[
   {"status":"PURCHASED","presented_at":BASE,"confirmed_delivery":True,"expected_price_minor":2500,"title":"Gold Set","offering_type":"PHOTOSET"},
   {"status":"EXPIRED","presented_at":BASE-timedelta(days=1),"confirmed_delivery":True,"expected_price_minor":1800,"title":"Night Set","offering_type":"BUNDLE"},
   {"status":"PURCHASED","presented_at":BASE-timedelta(hours=1),"confirmed_delivery":False,"expected_price_minor":2200,"title":"Unconfirmed Send","offering_type":"PHOTOSET"},
   {"status":"PURCHASED","presented_at":None,"confirmed_delivery":False,"expected_price_minor":900,"title":"Undelivered","offering_type":"VIDEO"}],
   "purchases":[
    {"payment_timestamp":BASE,"gross_minor":2500,"title":"Gold Set","offering_type":"PHOTOSET","ownership_confirmed":True},
    {"payment_timestamp":BASE-timedelta(days=2),"gross_minor":2500,"title":None,"offering_type":None}],
   "active_session":{"state":"CONTINUING","progression_stage":"CORE","commercial_foundation_type":"PHOTOSHOOT"},
   "prospect":{"preference_state":{"records":[]},"relationship_state":{}}}

def intelligence_service():
 return RelationshipsService(people_repository=PeopleRepo(),messages_repository=IntelligenceRepo())

@patch("app.services.relationship_value_override_service.RelationshipValueOverrideService.active",return_value=None)
def test_verified_intelligence_uses_canonical_value_and_strict_offer_lifecycle(_active):
 result=intelligence_service().intelligence(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=2)
 assert result["customerValue"]["valueTier"]=="REPEAT_BUYER"
 assert result["customerValue"]["purchaseCount"]==2
 assert result["salesPerformance"]=={
  "offersPresented":2,"offersPurchased":1,"offersNotPurchased":1,
  "conversionRate":.5,"lastOffer":result["salesPerformance"]["lastOffer"],
  "lastPurchase":result["salesPerformance"]["lastPurchase"]}
 assert result["salesPerformance"]["lastOffer"]["title"]=="Gold Set"
 assert len(result["purchaseHistory"])==2
 assert result["purchaseHistory"][0]["ownershipStatus"]=="OWNED"
 assert result["purchaseHistory"][1]["ownershipStatus"] is None
 assert result["commercialState"]["activeSalesSession"]["state"]=="CONTINUING"

@patch("app.services.relationship_value_override_service.RelationshipValueOverrideService.active",return_value=None)
def test_historical_purchase_without_presented_intent_is_not_conversion_numerator(_active):
 result=intelligence_service().intelligence(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=2)
 assert len(result["purchaseHistory"])==2
 assert result["salesPerformance"]["offersPurchased"]==1

@patch("app.services.relationship_value_override_service.RelationshipValueOverrideService.active",return_value=None)
def test_unmapped_prospect_returns_partial_memory_and_no_invented_value(_active):
 result=intelligence_service().intelligence(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=1)
 assert result["partial"] is True
 assert result["customerValue"]["valueTier"] is None
 assert result["customerValue"]["lifetimeSpendMinor"] is None
 assert result["salesPerformance"]["conversionRate"] is None
 assert result["relationshipIntelligence"]["location"]=="Austin"
 assert result["relationshipIntelligence"]["pets"]==["Milo"]

def test_unknown_scoped_person_cannot_load_intelligence():
 with pytest.raises(LookupError):
  intelligence_service().intelligence(creator_profile_id=7,fanvue_account_id=8,telegram_user_id=99)

def test_intelligence_endpoint_rejects_projection_key_outside_active_scope(monkeypatch):
 monkeypatch.setattr(relationships_api,"_snapshot_scope",lambda:(7,8))
 with pytest.raises(HTTPException) as error:
  relationships_api.relationship_intelligence("telegram:99:8:1")
 assert error.value.status_code==404

def test_intelligence_endpoint_passes_only_validated_scope(monkeypatch):
 calls=[]
 class ScopedService:
  def intelligence(self,**values):
   calls.append(values);return {"partial":True}
 monkeypatch.setattr(relationships_api,"_snapshot_scope",lambda:(7,8))
 monkeypatch.setattr(relationships_api,"RelationshipsService",ScopedService)
 assert relationships_api.relationship_intelligence("telegram:7:8:1")=={"partial":True}
 assert calls==[{"creator_profile_id":7,"fanvue_account_id":8,"telegram_user_id":1}]
