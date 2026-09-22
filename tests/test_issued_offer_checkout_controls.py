"""Sanitized real-7093 state: issued offer survives outbound control restoration."""
import json
from uuid import uuid4
from datetime import timedelta
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from test_canonical_evergreen_unlock import offer,canonical_db
from test_evergreen_checkout import database
from app.api import private_chat_unlock as api

@pytest.fixture
def restored_offer(offer,request):
 o=offer;mapped=request.param
 with o.db() as c:
  c.execute("INSERT INTO telegram_relationship_controls(relationship_control_id,changed_by,creator_profile_id,fanvue_account_id,telegram_user_id,telegram_chat_id,mode,communication_disposition,content_selling_enabled,session_selling_enabled) VALUES(gen_random_uuid(),'SYNTHETIC',901,901,99001,99001,'AVA_AUTO','IGNORED',false,false)")
  if mapped:
   buyer=uuid4();c.execute('DELETE FROM fanvue_fingerprint_reservations')
   c.execute('INSERT INTO fanvue_users(id,fanvue_user_uuid,fanvue_account_id) VALUES(901,%s,901)',(buyer,))
   c.execute("INSERT INTO telegram_identity_map(id,telegram_user_id,telegram_chat_id,fanvue_account_id,local_fanvue_user_id,external_fanvue_user_uuid,verification_status) VALUES(901,99001,99001,901,901,%s,'VERIFIED')",(buyer,))
   c.execute("UPDATE purchase_intents SET telegram_identity_mapping_id=901,external_fanvue_user_uuid=%s,identity_bootstrap_mode='NONE'",(buyer,))
 if mapped:o.provider.resources=[dict(uuid='product',url='https://www.fanvue.com/media-link/test',price=999,mediaUuids=['media-test'])]
 # Freeze the real canonical offer family before navigation, as issuance does.
 from app.services.canonical_evergreen_unlock import CanonicalUnlockAuthority,binding
 authority=CanonicalUnlockAuthority(o.gateway,o.alias)
 with o.db() as c:
  row=c.execute('SELECT * FROM purchase_intents WHERE purchase_intent_id=%s',(o.root,)).fetchone()
  grant=authority.authenticate(o.alias,binding(row),connection=c)
  authority.lock_scope(grant,connection=c)
 o.mapped=mapped
 return o

def browser(o,monkeypatch):
 monkeypatch.setenv('EVERGREEN_UNLOCK_ENABLED','true');monkeypatch.setenv('PRIVATE_CHAT_FINGERPRINT_IDENTITY_BOOTSTRAP_ENABLED','true')
 monkeypatch.setattr(api,'PrivateChatUnlockGatewayService',lambda:o.gateway)
 app=FastAPI();app.include_router(api.public_alias_router)
 return TestClient(app)

@pytest.mark.parametrize('restored_offer',[True,False],indirect=True)
@pytest.mark.parametrize('age',[1,25,73])
def test_issued_offer_checkout_ignores_outbound_sales_permission(restored_offer,monkeypatch,age):
 o=restored_offer;o.clock.now+=timedelta(hours=age)
 with o.db() as c:
  before=c.execute('select md5(to_jsonb(t)::text) digest from telegram_relationship_controls t').fetchone()['digest']
 with browser(o,monkeypatch) as client:
  preview=client.get('/u/'+o.alias,headers={'Purpose':'prefetch'});assert preview.status_code==204
  r=client.get('/u/'+o.alias,headers={'Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'},follow_redirects=False)
  assert r.status_code==302,r.text
  assert r.headers['location'].startswith('https://www.fanvue.com/')
  assert 'Continue to checkout' not in r.text
 with o.db() as c:
  assert c.execute('select md5(to_jsonb(t)::text) digest from telegram_relationship_controls t').fetchone()['digest']==before
  family=c.execute('select * from evergreen_offer_authorities').fetchone()
  assert family['configured_price_minor']==999 and family['final_price_minor']==(999 if o.mapped else 1001)
  assert c.execute('select count(*) n from fanvue_fingerprint_reservations').fetchone()['n']==(0 if o.mapped else 1)
  assert c.execute('select use_count from telegram_unlock_grants').fetchone()['use_count']==1
 assert o.provider.calls==(0 if o.mapped else 1)

@pytest.mark.parametrize('restored_offer',[True],indirect=True)
@pytest.mark.parametrize('mutation',[
 "UPDATE telegram_unlock_grants SET state='REVOKED'",
 "UPDATE runtime_control_records SET mode='OFFLINE'",
 "UPDATE commercial_publications SET status='ARCHIVED'",
 "UPDATE purchase_intents SET status='PURCHASED',purchased_at=NOW(),attribution_result='ATTRIBUTED'",
])
def test_restored_controls_do_not_bypass_real_checkout_authority(restored_offer,monkeypatch,mutation):
 o=restored_offer
 with o.db() as c:c.execute(mutation)
 with browser(o,monkeypatch) as client:r=client.get('/u/'+o.alias,follow_redirects=False)
 assert r.status_code==409 and 'location' not in r.headers
 assert o.provider.calls==0


class PaginatedSession:
 """Real client parser over a sanitized nine-page provider HTTP contract."""
 def __init__(self, resources):
  self.resources=resources; self.pages=[]; self.mutations=0
 def request(self,method,url,**kwargs):
  from types import SimpleNamespace
  assert method=='GET' and url=='https://api.fanvue.com/media-links'
  page=(kwargs.get('params') or {}).get('page',1);self.pages.append(page)
  data=[dict(uuid='unrelated-'+str(page)+'-'+str(n),price=300,mediaUuids=['other'],url='https://www.fanvue.com/media-link/other') for n in range(15)] if page<9 else self.resources
  return SimpleNamespace(status_code=200,json=lambda:{'data':data,'pagination':{'page':page,'size':len(data),'hasMore':page<9}})

@pytest.mark.parametrize('restored_offer',[True,False],indirect=True)
@pytest.mark.parametrize('age',[1,25,73])
def test_complete_checkout_with_real_paginated_client(restored_offer,monkeypatch,age):
 from app.services.fanvue_official_client import FanvueOfficialClient
 from types import SimpleNamespace
 o=restored_offer;o.clock.now+=timedelta(hours=age)
 resource=dict(uuid='product',url='https://www.fanvue.com/media-link/test',price=999 if o.mapped else 1001,mediaUuids=['media-test'])
 session=PaginatedSession([resource]);oauth=SimpleNamespace(require_scopes=lambda *a:None,get_valid_access_token=lambda:'synthetic')
 provider=FanvueOfficialClient(901,oauth=oauth,session=session)
 o.gateway.client_factory=lambda _:provider
 with browser(o,monkeypatch) as client:
  preview=client.get('/u/'+o.alias,headers={'Purpose':'prefetch'});assert preview.status_code==204
  assert session.pages==[]
  response=client.get('/u/'+o.alias,headers={'Sec-Fetch-Mode':'navigate','Sec-Fetch-Dest':'document'},follow_redirects=False)
  assert response.status_code==302,response.text
  assert response.headers['location']==resource['url']
 assert session.pages==list(range(1,10))
 with o.db() as c:
  grant=c.execute('select * from telegram_unlock_grants').fetchone();assert grant['use_count']==1
  op=c.execute('select * from evergreen_provider_operations').fetchone();assert op['state']=='READY' and op['attempt_count']==0
  control=c.execute('select * from telegram_relationship_controls').fetchone()
  assert control['communication_disposition']=='IGNORED' and not control['content_selling_enabled'] and not control['session_selling_enabled']
  family=c.execute('select * from evergreen_offer_authorities').fetchone();assert family['final_price_minor']==resource['price']
  assert c.execute('select count(*) n from evergreen_checkout_lineage').fetchone()['n']==(0 if age==1 else 1)


@pytest.mark.parametrize('restored_offer',[True],indirect=True)
@pytest.mark.parametrize('mutation',[
 "INSERT INTO customer_interaction_safety_states(safety_state_id,creator_profile_id,fanvue_account_id,fanvue_user_id,safety_status,reason,source) VALUES(gen_random_uuid(),901,901,901,'UNDERAGE_BLOCKED','synthetic restriction','OPERATOR')",
 "UPDATE fanvue_accounts SET is_active=false",
 "UPDATE creator_profiles SET is_active=false",
 "UPDATE commercial_offerings SET status='ARCHIVED'",
 "UPDATE telegram_unlock_grants SET telegram_chat_id=99002",
 "UPDATE purchase_intents SET expected_price_minor=1099",
 "UPDATE commercial_publications SET provider_resource_status='MISSING'",
])
def test_additional_redemption_blockers(restored_offer,monkeypatch,mutation):
 o=restored_offer
 with o.db() as c:c.execute(mutation)
 with browser(o,monkeypatch) as client:r=client.get('/u/'+o.alias,follow_redirects=False)
 assert r.status_code==409 and 'location' not in r.headers
 assert o.provider.calls==0

@pytest.mark.parametrize('restored_offer',[True],indirect=True)
@pytest.mark.parametrize('failure',['missing','price','media','destination','unsafe_destination','duplicate'])
def test_provider_evidence_failures_through_http(restored_offer,monkeypatch,failure):
 from app.services.fanvue_official_client import FanvueOfficialClient
 from types import SimpleNamespace
 o=restored_offer
 link=dict(uuid='product',url='https://www.fanvue.com/media-link/test',price=999,mediaUuids=['media-test'])
 if failure=='price':link['price']=1000
 if failure=='media':link['mediaUuids']=['different']
 if failure=='destination':link['url']='https://www.fanvue.com/media-link/different'
 if failure=='unsafe_destination':link['url']='https://untrusted.invalid/checkout'
 resources=[] if failure=='missing' else [link]
 if failure=='duplicate':resources.append(dict(link))
 session=PaginatedSession(resources)
 provider=FanvueOfficialClient(901,session=session,oauth=SimpleNamespace(require_scopes=lambda *a:None,get_valid_access_token=lambda:'synthetic'))
 o.gateway.client_factory=lambda _:provider
 with browser(o,monkeypatch) as client:r=client.get('/u/'+o.alias,follow_redirects=False)
 assert r.status_code==409 and 'location' not in r.headers
 with o.db() as c:
  assert c.execute('select use_count from telegram_unlock_grants').fetchone()['use_count']==0
