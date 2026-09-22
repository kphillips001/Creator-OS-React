from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from uuid import uuid4
import pytest
from test_ordinary_generation_budget import connection
from app.models.telegram_inbound import TelegramInboundPayload, TelegramInboundAttachment
from app.repositories.ordinary_chat_reply_repository import OrdinaryChatReplyRepository
from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.repositories.telegram_inbound_media_repository import TelegramInboundMediaRepository
from app.repositories.telegram_visual_turn_repository import TelegramVisualTurnRepository
from app.services.ordinary_chat_reply_service import OrdinaryChatReplyService
from app.services.telegram_inbound_adapter import TelegramInboundAdapter


@pytest.fixture
def turn():
    chat=uuid4().int%10**12
    now=datetime.now(timezone.utc);scope='BUILD3_'+str(chat)
    inbound=TelegramPrivateInboundRepository(connection_factory=connection)
    def capture(mid,text='',media=()):
        return inbound.capture(account_scope=scope,user_id=chat,chat_id=chat,message_id=mid,
            received_at=now,customer_text=text,media_types=media,creator_profile_id=2,
            fanvue_account_id=2,ingestion_provenance='CERTIFICATION',automation_state='ON')[0]
    first=capture(chat,'',('PHOTO',))
    attachment=TelegramInboundAttachment(str(uuid4()),chat,chat,chat,'PHOTO','fixture')
    payload=TelegramInboundPayload(chat,chat,'',chat,attachments=(attachment,),received_at=now)
    media=TelegramInboundMediaRepository(connection).receive(creator_profile_id=2,fanvue_account_id=2,payload=payload)
    ordinary=OrdinaryChatReplyRepository(connection)
    op,_=ordinary.get_or_create(account_scope=scope,chat_id=chat,inbound_message_id=chat,
        sender_user_id=chat,correlation_id=scope,inbound_message_text='',
        turn_obligations=['ACKNOWLEDGE_SELF_PHOTO'])
    repo=TelegramVisualTurnRepository(connection)
    row=repo.establish(media_operation=media,member_inbound_ids=[first.inbound_id],member_message_ids=[chat])
    visual=dict(media_turn_id=str(row['media_turn_id']),operation_id=str(media['operation_id']),
        response_policy='SELFIE_COMPLIMENT_ELIGIBLE',attachment_ids=[attachment.attachment_id],
        attachment_paths=['fixture.jpg'])
    return chat,capture,ordinary,op,repo,row,visual


def bind(ctx):
    _,_,_,op,repo,row,visual=ctx
    return repo.bind_response_owner(media_turn_id=row['media_turn_id'],operation_id=op.operation_id,visual_context=visual)


@pytest.mark.parametrize('before',[True,False])
def test_associated_text_same_owner_and_durable_payload(turn,before):
    chat,capture,ordinary,op,repo,row,visual=turn
    if not before: bind(turn)
    for offset,text in [(1,"that's me"),(2,'Putting a face to the name')]:
        incoming=capture(chat+offset,text)
        assert repo.attach_adjacent_text(creator_profile_id=2,fanvue_account_id=2,
            telegram_chat_id=chat,inbound_id=incoming.inbound_id,telegram_message_id=chat+offset)
    if before: bind(turn)
    saved=ordinary.get(op.operation_id)
    payload=OrdinaryChatReplyService.retry_payload(None,saved)
    TelegramInboundAdapter._validate_payload(payload)
    assert payload.message_text==''
    assert payload.media_turn_input.associated_text=="that's me\nPutting a face to the name"
    assert saved.burst_freshness_telegram_message_id==chat+2
    assert 'ACKNOWLEDGE_SELF_PHOTO' in saved.burst_obligations
    assert str(repo.get(row['media_turn_id'])['authoritative_response_operation_id'])==str(op.operation_id)
    assert ordinary.claim_generation(op.operation_id,owner='one')
    assert ordinary.claim_generation(op.operation_id,owner='two') is None


def test_concurrent_repeated_binding_and_restart_same_owner(turn):
    with ThreadPoolExecutor(max_workers=2) as pool:
        values=list(pool.map(lambda _:bind(turn),range(2)))
    assert values[0]['authoritative_response_operation_id']==values[1]['authoritative_response_operation_id']
    assert bind(turn)['authoritative_response_operation_id']==values[0]['authoritative_response_operation_id']


def test_conflicting_owner_cannot_replace_bound_owner(turn):
    chat,_,ordinary,op,repo,row,visual=turn
    bind(turn)
    other,_=ordinary.get_or_create(account_scope=op.telegram_account_scope,chat_id=chat,
        sender_user_id=chat,inbound_message_id=chat+10,correlation_id=str(uuid4()),inbound_message_text='new')
    with pytest.raises(ValueError,match='MEDIA_OWNER_CONFLICT'):
        repo.bind_response_owner(media_turn_id=row['media_turn_id'],operation_id=other.operation_id,visual_context=visual)
    assert repo.get(row['media_turn_id'])['authoritative_response_operation_id']==op.operation_id


def test_started_owner_does_not_swallow_new_text(turn):
    chat,capture,ordinary,op,repo,_,_=turn
    bind(turn);assert ordinary.claim_generation(op.operation_id,owner='generation')
    incoming=capture(chat+1,'A new question')
    assert repo.attach_adjacent_text(creator_profile_id=2,fanvue_account_id=2,telegram_chat_id=chat,
        inbound_id=incoming.inbound_id,telegram_message_id=chat+1) is None
