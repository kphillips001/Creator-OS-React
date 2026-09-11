from datetime import datetime,timezone
from uuid import UUID
from app.services.customer_workspace_service import CustomerWorkspaceService

PROFILE=UUID("00000000-0000-0000-0000-000000000042")
class Repository:
    def customers(self,**_): return [{"customer_commerce_profile_id":PROFILE,"fanvue_account_id":7,"external_fanvue_user_uuid":UUID("00000000-0000-0000-0000-000000000099"),"resolved_display_name":"Organic payer","resolved_handle":"payer","lifetime_gross_minor":5000,"profile_state":"FIRST_PURCHASE","last_purchase_at":datetime(2026,9,1,tzinfo=timezone.utc),"local_fanvue_user_id":None,"relationship_key":None,"active_sales_session":False,"active_purchase_intent":False,"buyer_tier":None,"is_top_spender":False,"is_whale":False}]
    def transactions(self,**_): return [{"customer_commerce_transaction_id":PROFILE,"purchase_source":"mediaLink","gross_minor":5000,"net_minor":4000,"payment_timestamp":datetime(2026,9,1,tzinfo=timezone.utc)}]
    def subscription_events(self,**_): return []

def test_commerce_payer_without_fanvue_user_is_a_customer_and_buyer():
    service=CustomerWorkspaceService(repository=Repository(),creator_profile_resolver=lambda _:{"id":1})
    result=service.list_customers(fanvue_account_id=7)
    assert len(result)==1 and result[0]["isBuyer"] is True and result[0]["localFanvueUserId"] is None

def test_summary_uses_verified_customer_semantics():
    summary=CustomerWorkspaceService.summarize([{"isBuyer":True,"subscriptionStatus":"ACTIVE","isHighValue":False,"activeSalesSession":False},{"isBuyer":False,"subscriptionStatus":"CANCELED_ACCESS_REMAINING","isHighValue":False,"activeSalesSession":True},{"isBuyer":False,"subscriptionStatus":"FORMER_EXPIRED","isHighValue":False,"activeSalesSession":False}])
    assert summary=={"total":3,"buyers":1,"activeSubscribers":2,"formerSubscribers":1,"highValue":0,"activeSessions":1}

def test_population_query_uses_durable_snapshot_test_provenance():
    source=open("app/repositories/verified_customer_repository.py",encoding="utf-8").read()
    assert all(value in source for value in ("controlled_smoke_test","CONTROLLED_TEST","test_specific","EXISTS (SELECT 1 FROM qualifying_transactions"))
