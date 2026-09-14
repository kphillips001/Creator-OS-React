"""Capture now; reconcile by conversation only under separate activation authority."""
from __future__ import annotations

from uuid import uuid4

from app.repositories.telegram_private_inbound_repository import TelegramPrivateInboundRepository
from app.services.ava_attention_investment_service import AvaAttentionInvestmentService


class TelegramPrivateInboundBacklogService:
    def __init__(self, *, repository=None, attention=None):
        self.repository = repository or TelegramPrivateInboundRepository()
        self.attention = attention or AvaAttentionInvestmentService()

    def capture(self, payload, *, account_scope, automation_state, creator_profile_id=None,
                fanvue_account_id=None, mapped_customer_id=None, prospect_id=None,
                provenance="TELETHON_NEW_MESSAGE"):
        media_types = tuple(sorted({str(item.media_kind) for item in payload.attachments}))
        return self.repository.capture(account_scope=account_scope, user_id=payload.telegram_user_id,
            chat_id=payload.telegram_chat_id, message_id=payload.message_id, received_at=payload.received_at,
            customer_text=payload.message_text, media_types=media_types, creator_profile_id=creator_profile_id,
            fanvue_account_id=fanvue_account_id, mapped_customer_id=mapped_customer_id,
            prospect_id=prospect_id, ingestion_provenance=provenance, automation_state=automation_state)

    def plan_chat(self, messages, *, verified_buyer=False):
        ordered = sorted(messages, key=lambda item: (item.received_at, item.telegram_message_id))
        decision = self.attention.evaluate([item.customer_text for item in ordered], verified_buyer=verified_buyer)
        if decision.outcome == "NO_RESPONSE_REQUIRED":
            return {"outcome": decision.outcome, "authoritative": None, "attention": decision}
        meaningful_questions = [m for m in ordered if self.attention.QUESTION.search(m.customer_text)
            and not self.attention.SUMMON.search(m.customer_text)]
        commercial = [m for m in ordered if self.attention.COMMERCIAL.search(m.customer_text)]
        meaningful = [m for m in ordered if m.customer_text.strip() and not self.attention._low_information(m.customer_text)]
        authoritative = (meaningful_questions or commercial or meaningful or ordered)[-1]
        return {"outcome": "RESPOND", "authoritative": authoritative, "attention": decision}

    def correlate(self, payload, *, account_scope, mapped_customer_id=None, prospect_id=None):
        self.repository.correlate(account_scope=account_scope, chat_id=payload.telegram_chat_id,
            message_id=payload.message_id, mapped_customer_id=mapped_customer_id, prospect_id=prospect_id)

    def reconcile_chat(self, *, account_scope, chat_id, verified_buyer=False):
        messages = self.repository.pending_for_chat(account_scope=account_scope, chat_id=chat_id)
        if not messages: return {"outcome": "ALREADY_RECONCILED", "messages": 0, "authoritative": None}
        plan = self.plan_chat(messages, verified_buyer=verified_buyer); reconciliation_id = uuid4()
        authoritative = plan["authoritative"]
        result = self.repository.reconcile(account_scope=account_scope, chat_id=chat_id,
            authoritative_message_id=(authoritative.telegram_message_id if authoritative else None),
            outcome=plan["outcome"], reconciliation_id=reconciliation_id,
            expected_message_ids=tuple(item.telegram_message_id for item in messages))
        if len(result) == 2:  # compact fake repositories used by deterministic tests
            updated, operation_id = result; stale = False
        else:
            updated, operation_id, stale = result
        if stale:
            return {"outcome": "STALE_RECONCILIATION_RETRY", "messages": 0,
                "authoritative": None, "response_operation_id": None}
        return {**plan, "reconciliation_id": reconciliation_id, "messages": len(updated),
            "response_operation_id": operation_id}
