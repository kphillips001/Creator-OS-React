"""Explicit, bounded Telegram broadcast discovery and local observation."""
from __future__ import annotations
from dataclasses import dataclass
from telethon import utils
from app.repositories.telegram_identity_repository import TelegramIdentityRepository

@dataclass(frozen=True)
class BroadcastCandidate:
    telegram_user_id:int; username:str|None; first_name:str|None; last_name:str|None
    display_name:str; participant_status:str

class TelegramBroadcastMemberLookupService:
    def __init__(self,client=None): self.client=client
    async def lookup(self,*,channel_id:int,search:str,limit:int=20):
        term=str(search or '').strip()
        if len(term)<2: raise ValueError('Subscriber search requires at least two characters.')
        bounded=max(1,min(int(limit),25)); result=[]
        async for user in self.client.iter_participants(channel_id,search=term,limit=bounded):
            participant=getattr(user,'participant',None)
            display=(utils.get_display_name(user) or
                     ' '.join(filter(None,(getattr(user,'first_name',None),getattr(user,'last_name',None)))) or
                     getattr(user,'username',None) or 'Telegram member')
            result.append(BroadcastCandidate(int(user.id),getattr(user,'username',None),
                getattr(user,'first_name',None),getattr(user,'last_name',None),
                display,type(participant).__name__ if participant else 'Member'))
        return result

class TelegramBroadcastObservationService:
    def __init__(self,repository=None):self.repository=repository or TelegramIdentityRepository()
    def persist(self,*,telegram_user_id:int,source_channel_id:int,username=None,
                display_name=None,participant_status=None):
        if not isinstance(telegram_user_id,int) or telegram_user_id<=0:raise ValueError('Stable numeric Telegram user ID is required.')
        if not isinstance(source_channel_id,int) or source_channel_id==0:raise ValueError('Broadcast channel ID is required.')
        return self.repository.observe_broadcast_member(telegram_user_id=telegram_user_id,
            source_channel_id=source_channel_id,username=username,display_name=display_name,
            participant_status=participant_status)
