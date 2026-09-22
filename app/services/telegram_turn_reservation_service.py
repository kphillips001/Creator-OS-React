"""Durable pre-generation reservation shared by text and media ingestion."""
from __future__ import annotations
import os
from app.repositories.telegram_turn_reservation_repository import TelegramTurnReservationRepository

class TelegramTurnReservationService:
    # Four album-finalization windows: enough for update dispatch reordering while
    # adding at most three seconds to a text-only operation's generation eligibility.
    DEFAULT_TEXT_FIRST_WINDOW_MS=3000
    def __init__(self,*,repository=None,window_ms=None):
        self.repository=repository or TelegramTurnReservationRepository()
        self.window_ms=max(750,min(5000,int(window_ms or os.getenv('TELEGRAM_TEXT_FIRST_MEDIA_JOIN_MS',self.DEFAULT_TEXT_FIRST_WINDOW_MS))))
    def reserve_text(self,**values): return self.repository.open_text(window_ms=self.window_ms,**values)
    def bind_owner(self,reservation_id,operation_id): return self.repository.bind_owner(reservation_id,operation_id)
    def bind_captured_owner(self,reservation_id,inbound_id): return self.repository.bind_captured_owner(reservation_id,inbound_id)
    def join_media(self,**values): return self.repository.join_media(**values)
    def close_expired(self): return self.repository.close_expired()
