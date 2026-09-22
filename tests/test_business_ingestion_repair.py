from types import SimpleNamespace
import pytest
from app.services.telegram_business_connection_worker import TelegramBusinessConnectionWorker, BusinessIngestionError, BUSINESS_UPDATE_TYPES

class Session:
 def __init__(self, updates=(), webhook='', error=None): self.updates=list(updates); self.webhook=webhook; self.error=error; self.calls=[]
 def get(self,url,**kw):
  self.calls.append((url.rsplit('/',1)[-1],kw))
  if self.error: raise self.error
  return SimpleNamespace(status_code=200,json=lambda:{'ok':True,'result':{'url':self.webhook} if url.endswith('getWebhookInfo') else self.updates})
class Observer:
 def __init__(self): self.rows={};self.fail=False
 def capture(self,e):
  if self.fail: raise RuntimeError('db failed')
  return self.rows.setdefault((e.update_id,e.telegram_message_id),{'id':e.update_id})
def event(n=1,connection='bc'):
 return {'update_id':n,'business_message':{'business_connection_id':connection,'message_id':7090,'date':1790006229,'from':{'id':7857064998},'chat':{'id':7857064998,'type':'private'}}}
def worker(session,observer=None):
 return TelegramBusinessConnectionWorker(bot_token='secret',session=session,lifecycle_service=SimpleNamespace(current=lambda **kw:SimpleNamespace(business_connection_id='bc')),peer_observation_service=observer or Observer(),business_owner_user_id=6432023689)
def test_polling_no_webhook_healthy_and_narrow_subscription():
 s=Session();w=worker(s);assert w.poll_once()==();assert w.health['status']=='HEALTHY';assert w.health['last_poll_success'];assert len(BUSINESS_UPDATE_TYPES)==4
 assert 'business_message' in s.calls[-1][1]['params']['allowed_updates']
def test_webhook_conflict_prevents_poll_and_is_separate_health():
 s=Session(webhook='https://other');w=worker(s)
 with pytest.raises(BusinessIngestionError,match='CONFLICT'):w.poll_once()
 assert [x[0] for x in s.calls]==['getWebhookInfo'];assert w.health['conflict'];assert 'connected' not in w.health;assert 'customer' not in w.health
 s.webhook='';w.poll_once();assert w.health['status']=='HEALTHY'
@pytest.mark.parametrize('order',['business_only','telethon_first','business_first','ignored','ava_auto','mapped','unmapped'])
def test_metadata_independent_of_conversation_controls_and_order(order):
 s=Session([event()]);o=Observer();w=worker(s,o);archive=set();replies=[]
 def telethon(): archive.add(7090)
 if order=='telethon_first':telethon()
 w.poll_once()
 if order!='business_only':telethon();telethon()
 assert len(o.rows)==1;assert len(archive)==(0 if order=='business_only' else 1);assert replies==[]
 assert w.health['last_business_update_received'];assert w.health['last_observation_persisted']
def test_duplicate_restart_is_idempotent_without_conversation():
 s=Session([event()]);o=Observer();worker(s,o).poll_once();worker(s,o).poll_once();assert len(o.rows)==1
@pytest.mark.parametrize('connection',['wrong','superseded'])
def test_wrong_or_stale_connection_rejected(connection):
 o=Observer();w=worker(Session([event(connection=connection)]),o);w.poll_once();assert not o.rows;assert w.health['rejected_updates']==1

def test_persistence_failure_does_not_advance_offset_and_recovers():
 o=Observer();o.fail=True;w=worker(Session([event()]),o)
 with pytest.raises(RuntimeError):w.poll_once()
 assert w.offset is None;assert w.health['status']=='ERROR'
 o.fail=False;w.poll_once();assert w.offset==2

def test_sensitive_request_error_is_redacted():
 w=worker(Session(error=RuntimeError('https://botSECRET')))
 with pytest.raises(BusinessIngestionError) as e:w.poll_once()
 assert 'SECRET' not in str(e.value);assert 'SECRET' not in str(w.health)

def test_409_is_ingestion_conflict():
 s=Session();s.get=lambda *a,**kw:SimpleNamespace(status_code=409);w=worker(s)
 with pytest.raises(BusinessIngestionError):w.poll_once()
 assert w.health['conflicts']==1

def test_malformed_update_does_not_acknowledge():
 w=worker(Session([{'update_id':2,'business_message':{}}]))
 with pytest.raises(BusinessIngestionError):w.poll_once()
 assert w.offset is None
