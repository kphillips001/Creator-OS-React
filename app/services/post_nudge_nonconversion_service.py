"""Record bounded nonconversion only at the canonical persisted-inbound boundary."""
from app.repositories.active_offer_follow_through_repository import ActiveOfferFollowThroughRepository
from app.repositories.purchase_intent_repository import PurchaseIntentRepository
from app.services.ava_attention_investment_service import AvaAttentionInvestmentService

class PostNudgeNonconversionService:
 def __init__(self,*,ledger=None,intents=None,attention=None):
  self.ledger=ledger or ActiveOfferFollowThroughRepository();self.intents=intents or PurchaseIntentRepository();self.attention=attention or AvaAttentionInvestmentService()
 def observe(self,operation,*,creator_profile_id,fanvue_account_id):
  text=str(operation.inbound_message_text or '').strip()
  state=getattr(operation.state,'value',operation.state)
  if state=='SUPPRESSED' or not text or self.attention._low_information(text):return ()
  intent=self.intents.get_active_for_buyer(creator_profile_id=creator_profile_id,fanvue_account_id=fanvue_account_id,telegram_user_id=operation.inbound_sender_telegram_user_id)
  if not intent or int(intent.telegram_chat_id)!=int(operation.telegram_chat_id):return ()
  return tuple(self.ledger.observe_customer_response(intent_id=intent.purchase_intent_id,observed_at=operation.inbound_received_at))
