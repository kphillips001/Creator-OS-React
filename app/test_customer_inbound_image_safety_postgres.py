import asyncio
import os
from datetime import datetime,timezone
from contextlib import contextmanager
from uuid import uuid4

import pytest
from psycopg import connect
from psycopg.rows import dict_row

from app.repositories.customer_inbound_image_safety_repository import CustomerInboundImageSafetyRepository
from app.repositories.telegram_inbound_media_repository import TelegramInboundMediaRepository
from app.services.customer_inbound_image_safety_service import CustomerInboundImageSafetyService
from app.services.telegram_inbound_media_service import TelegramInboundMediaService
from app.services.schema_manager_service import SchemaManagerService
from app.testing.postgres_safety import require_current_telegram_test_schema


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_safety_persistence_is_idempotent_and_restart_safe():
    url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as c:yield c
    SchemaManagerService(connection_factory=factory).reconcile_one('20260912_118_customer_inbound_image_safety.sql')
    operation_id,attachment_id=uuid4(),uuid4();calls=[]
    with factory() as c:
        c.execute("""INSERT INTO telegram_inbound_media_operations(operation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,telegram_user_id,logical_turn_key,state)
          VALUES(%s,1,2,3,3,%s,'READY_FOR_ANALYSIS')""",(operation_id,f'test:{operation_id}'))
        c.execute("""INSERT INTO telegram_inbound_media_attachments(attachment_id,operation_id,telegram_message_id,telegram_media_id,media_kind,position,normalized_path,state)
          VALUES(%s,%s,1,'synthetic','PHOTO',0,'synthetic.jpg','READY_FOR_ANALYSIS')""",(attachment_id,operation_id))
    repo=CustomerInboundImageSafetyRepository(factory)
    svc=CustomerInboundImageSafetyService(repository=repo,runner=lambda _:(calls.append(1) or [{'class':'MALE_GENITALIA_EXPOSED','score':.91}]))
    operation={'operation_id':operation_id,'creator_profile_id':1,'fanvue_account_id':2,'telegram_user_id':3,'grouped_id':None}
    first=asyncio.run(svc.process_operation(operation));second=asyncio.run(svc.process_operation(operation))
    with factory() as c:
        row=c.execute("SELECT state,safety_state,response_policy FROM telegram_inbound_media_operations WHERE operation_id=%s",(operation_id,)).fetchone()
        count=c.execute("SELECT count(*) n FROM telegram_inbound_media_safety_results WHERE operation_id=%s",(operation_id,)).fetchone()['n']
        c.execute("DELETE FROM telegram_inbound_media_operations WHERE operation_id=%s",(operation_id,))
    assert first.policy.value=='POLITE_EXPLICIT_BOUNDARY'
    assert second.policy.value=='POLITE_EXPLICIT_BOUNDARY'
    assert row=={'state':'SAFETY_CLASSIFIED','safety_state':'EXPLICIT_GENITAL','response_policy':'POLITE_EXPLICIT_BOUNDARY'}
    assert count==1 and len(calls)==1


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_confirmed_boundary_event_insert_is_exactly_once():
    url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as c:yield c
    SchemaManagerService(connection_factory=factory).reconcile_one('20260912_118_customer_inbound_image_safety.sql')
    operation_id=uuid4()
    with factory() as c:
        c.execute("""INSERT INTO telegram_inbound_media_operations(operation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,telegram_user_id,logical_turn_key,state)
          VALUES(%s,1,2,3,3,%s,'SAFETY_CLASSIFIED')""",(operation_id,f'boundary:{operation_id}'))
    repo=CustomerInboundImageSafetyRepository(factory);now=datetime.now(timezone.utc)
    values=dict(operation_id=operation_id,creator_profile_id=1,fanvue_account_id=2,
      telegram_user_id=3,policy='POLITE_EXPLICIT_BOUNDARY',delivered_at=now)
    first=repo.record_boundary_delivered(**values);second=repo.record_boundary_delivered(**values)
    with factory() as c:
        count=c.execute('SELECT count(*) n FROM telegram_explicit_boundary_events WHERE operation_id=%s',(operation_id,)).fetchone()['n']
        c.execute('DELETE FROM telegram_inbound_media_operations WHERE operation_id=%s',(operation_id,))
    assert first is not None and second is None and count==1


@pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='TEST_DATABASE_URL is required')
def test_cleanup_removes_only_expired_terminal_artifact(tmp_path):
    url=require_current_telegram_test_schema(os.getenv('TEST_DATABASE_URL'),os.getenv('DATABASE_URL'))
    @contextmanager
    def factory():
        with connect(url,row_factory=dict_row) as c:yield c
    SchemaManagerService(connection_factory=factory).reconcile_one('20260912_118_customer_inbound_image_safety.sql')
    expired_operation,active_operation=uuid4(),uuid4()
    expired_attachment,active_attachment=uuid4(),uuid4()
    expired_path=tmp_path/f'{expired_attachment}.jpg';expired_path.write_bytes(b'expired')
    active_path=tmp_path/f'{active_attachment}.jpg';active_path.write_bytes(b'active')
    with factory() as c:
        for operation_id,state,expiry in (
            (expired_operation,'SAFETY_CLASSIFIED','NOW()-INTERVAL \'1 hour\''),
            (active_operation,'SAFETY_ANALYZING','NOW()-INTERVAL \'1 hour\''),
        ):
            c.execute(f"""INSERT INTO telegram_inbound_media_operations(
              operation_id,creator_profile_id,fanvue_account_id,telegram_chat_id,
              telegram_user_id,logical_turn_key,state,retention_expires_at)
              VALUES(%s,1,2,3,3,%s,%s,{expiry})""",
              (operation_id,f'cleanup:{operation_id}',state))
        for attachment_id,operation_id,path in (
            (expired_attachment,expired_operation,expired_path),
            (active_attachment,active_operation,active_path),
        ):
            c.execute("""INSERT INTO telegram_inbound_media_attachments(
              attachment_id,operation_id,telegram_message_id,telegram_media_id,
              media_kind,position,normalized_path,state)
              VALUES(%s,%s,1,%s,'PHOTO',0,%s,'READY_FOR_ANALYSIS')""",
              (attachment_id,operation_id,str(attachment_id),str(path)))
    service=TelegramInboundMediaService(
        repository=TelegramInboundMediaRepository(factory),storage_root=tmp_path)
    assert service.cleanup_expired()==1
    with factory() as c:
        expired_value=c.execute("SELECT normalized_path FROM telegram_inbound_media_attachments WHERE attachment_id=%s",(expired_attachment,)).fetchone()['normalized_path']
        active_value=c.execute("SELECT normalized_path FROM telegram_inbound_media_attachments WHERE attachment_id=%s",(active_attachment,)).fetchone()['normalized_path']
        c.execute("DELETE FROM telegram_inbound_media_operations WHERE operation_id IN (%s,%s)",(expired_operation,active_operation))
    assert expired_value is None and not expired_path.exists()
    assert active_value==str(active_path) and active_path.exists()
