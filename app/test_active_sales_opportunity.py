from datetime import datetime,timedelta,timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from app.models.purchase_intent import PurchaseIntentStatus
from app.services.active_sales_opportunity_service import ActiveSalesOpportunityService
NOW=datetime(2026,9,14,18,tzinfo=timezone.utc)
SCOPE=dict(creator_profile_id=2,fanvue_account_id=2,telegram_user_id=3,telegram_chat_id=3)
def intent(status,**changes):
 values=dict(purchase_intent_id=uuid4(),status=status,expires_at=NOW+timedelta(days=1),purchased_at=None,provider_transaction_order_id=None,provider_payment_id=None,provider_event_id=None,commercial_offering_id=uuid4(),configured_base_price_minor=999,expected_price_minor=999,expected_currency='USD',**SCOPE);values.update(changes);return SimpleNamespace(**values)
class Intents:
 def __init__(self,item):self.item=item
 def get_active_for_buyer(self,**_):return self.item
class Offerings:
 def get(self,*_,**__):return SimpleNamespace(title='Piano Muse Allure')
@pytest.mark.parametrize('status,expected',[(PurchaseIntentStatus.PRESENTED,True),(PurchaseIntentStatus.CLICKED,True),(PurchaseIntentStatus.CREATED,False),(PurchaseIntentStatus.EXPIRED,False),(PurchaseIntentStatus.ABANDONED,False),(PurchaseIntentStatus.SUPERSEDED,False),(PurchaseIntentStatus.PURCHASED,False)])
def test_only_current_presented_unsettled_intent_qualifies(status,expected):
 assert ActiveSalesOpportunityService(intents=Intents(intent(status)),offerings=Offerings(),clock=lambda:NOW).project(**SCOPE)['active'] is expected
def test_expired_scope_mismatch_and_settlement_fail_closed():
 for item in [intent(PurchaseIntentStatus.CLICKED,expires_at=NOW),intent(PurchaseIntentStatus.CLICKED,telegram_chat_id=99),intent(PurchaseIntentStatus.CLICKED,provider_payment_id='paid')]:
  assert not ActiveSalesOpportunityService(intents=Intents(item),offerings=Offerings(),clock=lambda:NOW).project(**SCOPE)['active']
def test_anthony_fixture_projects_existing_offer_without_mutation():
 result=ActiveSalesOpportunityService(intents=Intents(intent(PurchaseIntentStatus.CLICKED)),offerings=Offerings(),clock=lambda:NOW).project(**SCOPE)
 assert result['active'] and result['offer_title']=='Piano Muse Allure' and result['configured_price_minor']==999
