import time
from datetime import datetime,timezone
from pathlib import Path
import pytest
from test_canonical_evergreen_unlock import canonical_db
from test_evergreen_checkout import database
from test_business_ingestion_repair import Session,event
from app.services.telegram_business_connection_worker import TelegramBusinessConnectionWorker
from app.services.telegram_business_connection_service import TelegramBusinessConnectionService
from app.repositories.telegram_business_connection_repository import TelegramBusinessConnectionRepository
from app.repositories.telegram_business_peer_observation_repository import TelegramBusinessPeerObservationRepository
from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.services.telegram_business_commercial_transport import TelegramBusinessCommercialTransport
from app.models.telegram_transport_contract import TelegramRequirements

@pytest.mark.parametrize('order',['telethon_first','business_first','business_only','telethon_only'])
def test_real_database_independent_idempotent_evidence(canonical_db,order):
 db=canonical_db
 with db() as c:
  c.execute('TRUNCATE telegram_business_peer_observations,telegram_business_connections CASCADE')
  c.execute('DELETE FROM telegram_private_inbound_messages WHERE telegram_chat_id=7857064998')
 lifecycle=TelegramBusinessConnectionService(repository=TelegramBusinessConnectionRepository(connection_factory=db),bot_telegram_user_id=8214690576)
 lifecycle.repository.reconcile(business_connection_id='bc',business_owner_telegram_user_id=6432023689,bot_telegram_user_id=8214690576,is_enabled=True,can_reply=True,rights={'can_reply':True},provider_updated_at=datetime.now(timezone.utc))
 peers=TelegramBusinessPeerObservationRepository(connection_factory=db);archive=TelegramPrivateInboundRepository(connection_factory=db)
 update=event();update['business_message']['date']=int(time.time())
 w=TelegramBusinessConnectionWorker(bot_token='test',session=Session([update]),lifecycle_service=lifecycle,peer_observation_service=peers,business_owner_user_id=6432023689)
 def capture():return archive.capture(account_scope='TEST',user_id=7857064998,chat_id=7857064998,message_id=7090,received_at=datetime.now(timezone.utc),customer_text='test')
 if order in ('telethon_first','telethon_only'): assert capture()[1]
 if order!='telethon_only':w.poll_once();w.poll_once()
 if order=='business_first':assert capture()[1]
 if order!='business_only':assert capture()[1] is False
 with db() as c:
  assert c.execute('SELECT count(*) n FROM telegram_business_peer_observations').fetchone()['n']==(order!='telethon_only')
  assert c.execute('SELECT count(*) n FROM telegram_private_inbound_messages WHERE telegram_chat_id=7857064998').fetchone()['n']==(order!='business_only')
 transport=TelegramBusinessCommercialTransport(enabled=True,owner_user_id=6432023689,bot_id=8214690576,connection_service=lifecycle,peer_observations=peers)
 if order!='telethon_only': assert transport.prepare_delivery(chat_id=7857064998,requirements=TelegramRequirements(photo=True,caption=True,url_action=True)).transport=='TELEGRAM_BUSINESS'
 else:
  with pytest.raises(Exception):transport.prepare_delivery(chat_id=7857064998,requirements=TelegramRequirements(photo=True,caption=True,url_action=True))
