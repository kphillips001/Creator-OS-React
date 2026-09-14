import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services.telegram_broadcast_observation_service import (
    TelegramBroadcastMemberLookupService, TelegramBroadcastObservationService)
from app.services.telegram_identity_service import TelegramIdentityService
from app.services.customer_controls_inventory_service import CustomerControlsInventoryService

class AsyncParticipants:
    def __init__(self,rows):self.rows=rows;self.calls=[]
    def iter_participants(self,*args,**kwargs):
        self.calls.append((args,kwargs))
        async def values():
            for row in self.rows:yield row
        return values()

def test_lookup_is_bounded_and_read_only():
    client=AsyncParticipants([SimpleNamespace(id=123,username='wm',first_name='Wally',last_name='McClung',participant=SimpleNamespace())])
    result=asyncio.run(TelegramBroadcastMemberLookupService(client).lookup(channel_id=-1001,search='Wally',limit=500))
    assert result[0].telegram_user_id==123 and result[0].display_name=='Wally McClung'
    assert client.calls==[((-1001,),{'search':'Wally','limit':25})]

class ObservationRepository:
    def __init__(self):self.calls=[]
    def observe_broadcast_member(self,**values):self.calls.append(values);return {**values,'observation_sources':['BROADCAST_MEMBER'],'private_chat_id':None}

def test_explicit_persistence_creates_observation_only_and_requires_numeric_id():
    repo=ObservationRepository();service=TelegramBroadcastObservationService(repo)
    result=service.persist(telegram_user_id=123,source_channel_id=-1001,display_name='Wally')
    assert result['private_chat_id'] is None and len(repo.calls)==1
    assert set(repo.calls[0])=={'telegram_user_id','source_channel_id','username','display_name','participant_status'}
    with pytest.raises(ValueError,match='numeric'):service.persist(telegram_user_id='Wally',source_channel_id=-1001)

class IdentityRepository:
    def readiness(self,**_):return ({},[{'telegram_user_id':123,'observation_sources':['BROADCAST_MEMBER'],'private_chat_id':None,'display_name':'Wally','mapping_id':None}])
    def list_fanvue_candidates(self,**_):return [{'id':7245}]

def test_mapping_preview_does_not_claim_private_chat_for_broadcast_identity():
    result=TelegramIdentityService(IdentityRepository()).preview_operator_mapping(telegram_user_id=123,fanvue_account_id=2,local_fanvue_user_id=7245)
    assert result['privateChatEvidence']=='NOT_ESTABLISHED'
    assert result['privateChatEstablished'] is False
    assert result['source']=='BROADCAST_SUBSCRIBER'
    assert result['existingMapping']=='NONE' and result['conflict']=='NONE'

def test_inventory_keeps_verified_broadcast_customer_identity_only():
    row={'row_kind':'CANONICAL_CUSTOMER','row_key':'customer:2:2:7245','local_fanvue_user_id':7245,
      'display_name':'Wally','best_username':'papi80','canonical_username':'papi80','canonical_display_name':'Wally','canonical_source':'provider',
      'purchase_count':5,'telegram_status':'VERIFIED','x_status':'NOT_OBSERVED','control_availability':'UNAVAILABLE','relationship_key':None,
      'telegram_user_id':123,'observation_sources':['BROADCAST_MEMBER'],'source_channel_id':-1001,'private_chat_id':None,'participant_status':'ChannelParticipant',
      'lifetime_gross_minor':11996,'operational_eligibility_reason':'VERIFIED_EXTERNAL_MAPPING'}
    repo=SimpleNamespace(rows=lambda **_: [row]);item=CustomerControlsInventoryService(repo).list(creator_profile_id=2,fanvue_account_id=2)['items'][0]
    assert item['platforms']['telegram']=='VERIFIED'
    assert item['telegramObservation']['privateChatEstablished'] is False
    assert item['controls'] is None and item['hasConversation'] is False

def test_migration_backfills_private_history_and_rollback_fails_closed():
    root=Path(__file__).resolve().parents[2]
    forward=(root/'migrations/forward/20260912_116_telegram_observation_sources.sql').read_text()
    rollback=(root/'migrations/rollback/20260912_116_telegram_observation_sources.sql').read_text()
    assert 'private_chat_id=telegram_chat_id' in forward
    assert "ARRAY['PRIVATE_CHAT']" in forward and 'DROP NOT NULL' in forward
    assert 'broadcast-only Telegram observations exist' in rollback
