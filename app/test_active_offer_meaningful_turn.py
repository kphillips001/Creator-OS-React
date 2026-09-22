from datetime import datetime, timezone
from types import SimpleNamespace
from app.services.active_offer_meaningful_turn_service import ActiveOfferMeaningfulTurnService

NOW=datetime(2026,9,14,tzinfo=timezone.utc)
class Ops:
 def post_presentation_turn_candidates(self,**_):
  return [dict(operation_id=str(i),inbound_telegram_message_id=i,
    inbound_message_text=text,inbound_received_at=NOW,state='SENT_CONFIRMED',last_error=None)
    for i,text in enumerate(('hello there','how was your day?','tell me more','that sounds lovely','😘'),1)]
class Attention:
 @staticmethod
 def _low_information(text): return text=='😘'

def test_projection_uses_persisted_window_and_canonical_low_information():
 result=ActiveOfferMeaningfulTurnService(operations=Ops(),attention=Attention()).project(
  intent=SimpleNamespace(presented_at=NOW,telegram_chat_id=2,telegram_user_id=3))
 assert result['meaningful_turns_since_presentation']==4
 assert result['included_message_ids']==(1,2,3,4)
 assert result['excluded'][0]['reason']=='CANONICAL_LOW_INFORMATION'

def test_requery_is_restart_stable():
 intent=SimpleNamespace(presented_at=NOW,telegram_chat_id=2,telegram_user_id=3)
 assert ActiveOfferMeaningfulTurnService(operations=Ops(),attention=Attention()).project(intent=intent)==ActiveOfferMeaningfulTurnService(operations=Ops(),attention=Attention()).project(intent=intent)
