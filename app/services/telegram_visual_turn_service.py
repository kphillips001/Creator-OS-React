"""Canonical association and short-lived continuity for new Telegram media."""
from __future__ import annotations

import os

from app.repositories.telegram_visual_turn_repository import TelegramVisualTurnRepository


class TelegramVisualTurnService:
    """Uses durable Telegram/burst identities; time is only a bounded eligibility gate."""

    def __init__(self, *, repository=None, continuity_minutes=None):
        self.repository = repository or TelegramVisualTurnRepository()
        self.continuity_minutes = int(
            continuity_minutes or os.getenv("TELEGRAM_VISUAL_CONTINUITY_MINUTES", "30")
        )
        self.association_seconds = int(os.getenv(
            "TELEGRAM_MEDIA_TEXT_ASSOCIATION_SECONDS", "30"))

    def establish(self, *, media_operation, inbound_members, burst=None,
                  authoritative_operation_id=None):
        members = tuple(inbound_members)
        roles = [{"inbound_id": str(x["inbound_id"]),
                  "telegram_message_id": int(x["telegram_message_id"]),
                  "role": "MEDIA" if x.get("has_media") else "TEXT"}
                 for x in members]
        return self.repository.establish(
            media_operation=media_operation,
            member_inbound_ids=[x["inbound_id"] for x in members],
            member_message_ids=[x["telegram_message_id"] for x in members],
            member_roles=roles,
            burst_id=(burst or {}).get("conversation_burst_id"),
            authoritative_operation_id=authoritative_operation_id,
        )

    def persist(self, *, media_turn, observations):
        return self.repository.save_summary(
            media_turn=media_turn, observations=observations,
            retention_minutes=self.continuity_minutes,
        )

    def persist_by_id(self, *, media_turn_id, observations):
        media_turn = self.repository.get(media_turn_id)
        if media_turn is None:
            raise ValueError("media turn is unavailable")
        return self.persist(media_turn=media_turn, observations=observations)

    def attach_adjacent_text(self, *, creator_profile_id, fanvue_account_id,
                             telegram_chat_id, inbound):
        if not str(getattr(inbound, "customer_text", "") or "").strip():
            return None
        return self.repository.attach_adjacent_text(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_chat_id=telegram_chat_id,
            inbound_id=inbound.inbound_id,
            telegram_message_id=inbound.telegram_message_id,
            window_seconds=self.association_seconds,
        )

    def associated_text(self, media_turn_id):
        rows = self.repository.member_text(media_turn_id)
        return "\n".join(str(row["customer_text"]).strip() for row in rows
                         if str(row.get("customer_text") or "").strip())

    def continuity(self, *, creator_profile_id, fanvue_account_id, telegram_chat_id):
        return self.repository.live_summaries(
            creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id,
            telegram_chat_id=telegram_chat_id,
        )
