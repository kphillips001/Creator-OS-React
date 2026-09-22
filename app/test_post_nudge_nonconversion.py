from datetime import datetime,timezone
from types import SimpleNamespace
from app.services.post_nudge_nonconversion_service import PostNudgeNonconversionService

NOW=datetime.now(timezone.utc)
class Ledger:
 def __init__(self):self.calls=[]
 def observe_customer_response(self,**values):self.calls.append(values);return [{'event_id':'one'}]
class Intents:
 def __init__(self,item):self.item=item
 def get_active_for_buyer(self,**_):return self.item
class Attention:
 @staticmethod
 def _low_information(text):return text in {'😘','ok'}
def op(text,state='PENDING_GENERATION'):
 return SimpleNamespace(inbound_message_text=text,state=SimpleNamespace(value=state),inbound_sender_telegram_user_id=3,telegram_chat_id=4,inbound_received_at=NOW)
def service(item=None):
 ledger=Ledger();return PostNudgeNonconversionService(ledger=ledger,intents=Intents(item or SimpleNamespace(purchase_intent_id='p',telegram_chat_id=4)),attention=Attention()),ledger
def test_meaningful_scoped_inbound_records_observation_once_per_ledger_authority():
 subject,ledger=service();assert subject.observe(op('I wanted to keep talking about my day'),creator_profile_id=1,fanvue_account_id=2)
 assert len(ledger.calls)==1
def test_low_information_suppressed_and_wrong_chat_do_not_observe():
 subject,ledger=service();assert not subject.observe(op('😘'),creator_profile_id=1,fanvue_account_id=2)
 assert not subject.observe(op('meaningful words here','SUPPRESSED'),creator_profile_id=1,fanvue_account_id=2)
 subject2,ledger2=service(SimpleNamespace(purchase_intent_id='p',telegram_chat_id=99));assert not subject2.observe(op('meaningful words here'),creator_profile_id=1,fanvue_account_id=2)
 assert not ledger.calls and not ledger2.calls
